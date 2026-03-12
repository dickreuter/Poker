use image::RgbaImage;
use tracing::debug;

use crate::config::Thresholds;
use crate::image::color;
use crate::image::preprocess;
use crate::output::game_state::AvailableAction;
use crate::regions::Rect;

/// A detected button before OCR verification.
#[derive(Debug, Clone)]
struct RawButton {
    button_type: String,
    rect: Rect,
    confidence: f32,
}

/// Detect action buttons in the button region of the table.
///
/// Strategy:
/// 1. HSV color detection for green (call/check), orange (raise/bet), gray (fold), red (deal_me_in)
/// 2. Connected component analysis to find button-shaped regions
/// 3. Return buttons with screen coordinates for clicking
pub fn detect_buttons(
    img: &RgbaImage,
    button_region: &Rect,
    thresholds: &Thresholds,
    table_x_pt: i32,
    table_y_pt: i32,
    retina_scale: u32,
) -> Vec<AvailableAction> {
    let cropped = preprocess::crop_rgba(img, button_region.x, button_region.y, button_region.w, button_region.h);
    let (cw, ch) = cropped.dimensions();
    if cw == 0 || ch == 0 {
        return Vec::new();
    }

    let mut buttons = Vec::new();

    // Check each button color
    let color_configs = [
        ("call", thresholds.hsv_green_lower, thresholds.hsv_green_upper),
        ("raise", thresholds.hsv_orange_lower, thresholds.hsv_orange_upper),
        ("fold", thresholds.hsv_gray_lower, thresholds.hsv_gray_upper),
        ("deal_me_in", thresholds.hsv_red_lower, thresholds.hsv_red_upper),
    ];

    for (btn_type, lower, upper) in &color_configs {
        let mask = color::hsv_mask(cropped.as_raw(), cw, ch, *lower, *upper);
        let rects = find_connected_regions(&mask, cw, ch, thresholds);

        for rect in rects {
            buttons.push(RawButton {
                button_type: btn_type.to_string(),
                rect,
                confidence: 0.9,
            });
        }
    }

    debug!("Found {} raw buttons", buttons.len());

    // Filter overlapping buttons (keep larger one)
    deduplicate_buttons(&mut buttons);

    // Convert to AvailableAction with screen coordinates
    buttons
        .into_iter()
        .map(|b| {
            let center = b.rect.center();
            // Convert from cropped-region pixel coords to screen points
            let px_x = (button_region.x + center.0) as i32;
            let px_y = (button_region.y + center.1) as i32;
            let screen_x = table_x_pt + px_x / retina_scale as i32;
            let screen_y = table_y_pt + px_y / retina_scale as i32;

            AvailableAction {
                action_type: b.button_type,
                amount: None, // Will be filled by OCR/value detection
                screen_x_pt: screen_x,
                screen_y_pt: screen_y,
                confidence: b.confidence as f64,
            }
        })
        .collect()
}

/// Find connected regions in a binary mask that match button size constraints.
fn find_connected_regions(mask: &[bool], w: u32, h: u32, thresholds: &Thresholds) -> Vec<Rect> {
    let mut labels = vec![0u32; (w * h) as usize];
    let mut next_label = 1u32;
    let mut results = Vec::new();

    for y in 0..h {
        for x in 0..w {
            let idx = (y * w + x) as usize;
            if mask[idx] && labels[idx] == 0 {
                let label = next_label;
                next_label += 1;
                let mut min_x = x;
                let mut min_y = y;
                let mut max_x = x;
                let mut max_y = y;
                let mut area = 0u32;
                let mut stack = vec![(x, y)];

                while let Some((cx, cy)) = stack.pop() {
                    let cidx = (cy * w + cx) as usize;
                    if cidx >= labels.len() || !mask[cidx] || labels[cidx] != 0 {
                        continue;
                    }
                    labels[cidx] = label;
                    area += 1;
                    min_x = min_x.min(cx);
                    min_y = min_y.min(cy);
                    max_x = max_x.max(cx);
                    max_y = max_y.max(cy);

                    if cx > 0 { stack.push((cx - 1, cy)); }
                    if cx + 1 < w { stack.push((cx + 1, cy)); }
                    if cy > 0 { stack.push((cx, cy - 1)); }
                    if cy + 1 < h { stack.push((cx, cy + 1)); }
                }

                let rw = max_x - min_x + 1;
                let rh = max_y - min_y + 1;

                let bounding_area = rw * rh;
                let fill_ratio = if bounding_area > 0 { area as f32 / bounding_area as f32 } else { 0.0 };

                // Filter by button size constraints
                if area >= thresholds.button_area_min
                    && rw >= thresholds.button_min_width
                    && rh >= thresholds.button_min_height
                    // Buttons are wider than tall
                    && rw > rh
                    // Real buttons have dense fill (>30% of bounding box)
                    && fill_ratio > 0.3
                    // Buttons shouldn't be too wide (max 5:1 aspect)
                    && rw < rh * 5
                {
                    results.push(Rect::new(min_x, min_y, rw, rh));
                }
            }
        }
    }

    results
}

/// Remove overlapping button detections, keeping the larger one.
fn deduplicate_buttons(buttons: &mut Vec<RawButton>) {
    buttons.sort_by(|a, b| b.rect.area().cmp(&a.rect.area()));

    let mut keep = vec![true; buttons.len()];
    for i in 0..buttons.len() {
        if !keep[i] { continue; }
        for j in (i + 1)..buttons.len() {
            if !keep[j] { continue; }
            // Check overlap
            let (cx1, cy1) = buttons[i].rect.center();
            let (cx2, cy2) = buttons[j].rect.center();
            let dx = (cx1 as i32 - cx2 as i32).unsigned_abs();
            let dy = (cy1 as i32 - cy2 as i32).unsigned_abs();
            if dx < 40 && dy < 20 {
                keep[j] = false;
            }
        }
    }

    let mut idx = 0;
    buttons.retain(|_| {
        let k = keep[idx];
        idx += 1;
        k
    });
}
