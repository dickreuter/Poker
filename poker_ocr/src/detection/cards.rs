use image::{GrayImage, RgbaImage};
use std::path::Path;
use tracing::{debug, warn};

use crate::config::Thresholds;
use crate::image::color;
use crate::image::preprocess;
use crate::image::template;
use crate::regions::Rect;

/// A detected card.
#[derive(Debug, Clone)]
pub struct DetectedCard {
    pub code: String, // e.g. "AH", "KS", "10D"
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
    pub confidence: f32,
}

/// Card template for matching.
struct CardTemplate {
    code: String,
    gray: GrayImage,
}

/// Card detector using white region detection + template matching.
pub struct CardDetector {
    templates: Vec<CardTemplate>,
}

impl CardDetector {
    /// Load templates from a directory of PNG files named like "AH.png", "KS.png", etc.
    pub fn new(template_dir: &Path) -> Self {
        let mut templates = Vec::new();

        if template_dir.exists() {
            for entry in std::fs::read_dir(template_dir).unwrap_or_else(|_| {
                warn!("Could not read template dir: {:?}", template_dir);
                std::fs::read_dir(".").unwrap() // empty fallback
            }) {
                if let Ok(entry) = entry {
                    let path = entry.path();
                    if path.extension().map(|e| e == "png").unwrap_or(false) {
                        if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                            if let Ok(img) = image::open(&path) {
                                let code = stem.to_uppercase();
                                templates.push(CardTemplate {
                                    code,
                                    gray: img.to_luma8(),
                                });
                            }
                        }
                    }
                }
            }
        }

        debug!("Loaded {} card templates", templates.len());
        Self { templates }
    }

    /// Create a detector with no templates (for testing or when templates not available).
    pub fn empty() -> Self {
        Self {
            templates: Vec::new(),
        }
    }

    /// Detect cards in a region of the table image.
    ///
    /// 1. Find white card-shaped rectangles via contour detection
    /// 2. Extract top-left corner of each card
    /// 3. Template match corner against all 52 templates
    /// 4. Verify suit color (red vs black) for disambiguation
    pub fn detect_cards(
        &self,
        img: &RgbaImage,
        region: &Rect,
        thresholds: &Thresholds,
    ) -> Vec<DetectedCard> {
        let cropped = preprocess::crop_rgba(img, region.x, region.y, region.w, region.h);
        let (cw, ch) = cropped.dimensions();
        if cw == 0 || ch == 0 {
            return Vec::new();
        }

        // Step 1: Find white rectangles (cards)
        let white_rects = find_white_card_regions(&cropped, thresholds);
        debug!("Found {} white card regions", white_rects.len());

        if self.templates.is_empty() {
            // No templates - just return detected regions without identification
            return white_rects
                .iter()
                .map(|r| DetectedCard {
                    code: "??".into(),
                    x: region.x + r.x,
                    y: region.y + r.y,
                    w: r.w,
                    h: r.h,
                    confidence: 0.0,
                })
                .collect();
        }

        // Step 2-3: For each white rectangle, extract corner and match templates
        let gray = preprocess::to_grayscale(&cropped);
        let mut detected = Vec::new();

        for rect in &white_rects {
            if let Some(card) = self.identify_card(&gray, &cropped, rect, thresholds) {
                detected.push(DetectedCard {
                    code: card.0,
                    x: region.x + rect.x,
                    y: region.y + rect.y,
                    w: rect.w,
                    h: rect.h,
                    confidence: card.1,
                });
            }
        }

        // Deduplicate: keep best match per position (within 30px)
        deduplicate_cards(&mut detected);

        detected
    }

    /// Detect if cards are face-down (card backs visible).
    pub fn detect_card_backs(img: &RgbaImage, region: &Rect) -> bool {
        let cropped = preprocess::crop_rgba(img, region.x, region.y, region.w, region.h);
        let (cw, ch) = cropped.dimensions();
        if cw == 0 || ch == 0 {
            return false;
        }

        // Card backs on GGSystem are red-patterned
        // Count red-ish pixels in the region
        let mut red_count = 0u32;
        let total = cw * ch;

        for y in 0..ch {
            for x in 0..cw {
                let p = cropped.get_pixel(x, y);
                let (h, s, v) = color::rgb_to_hsv(p[0], p[1], p[2]);
                // Red hue range (0-10 or 170-180) with decent saturation
                if (h <= 10 || h >= 170) && s > 60 && v > 60 {
                    red_count += 1;
                }
            }
        }

        let red_pct = red_count as f32 / total as f32;
        debug!("Card back detection: {:.1}% red pixels", red_pct * 100.0);
        red_pct > 0.15 // >15% red pixels suggests card backs
    }

    /// Identify a single card by template matching its corner.
    fn identify_card(
        &self,
        gray: &GrayImage,
        rgba: &RgbaImage,
        rect: &Rect,
        thresholds: &Thresholds,
    ) -> Option<(String, f32)> {
        // Extract top-left corner (rank + suit area)
        let corner_w = (rect.w * 45 / 100).min(50).max(20);
        let corner_h = (rect.h * 55 / 100).min(70).max(30);
        let corner = image::imageops::crop_imm(
            gray,
            rect.x,
            rect.y,
            corner_w.min(gray.width().saturating_sub(rect.x)),
            corner_h.min(gray.height().saturating_sub(rect.y)),
        )
        .to_image();

        if corner.width() < 10 || corner.height() < 10 {
            return None;
        }

        // Match against all templates
        let mut best_code = String::new();
        let mut best_score = f32::MAX;

        for t in &self.templates {
            let (score, _, _, _) = template::match_template_multiscale(
                &corner,
                &t.gray,
                &thresholds.template_scales,
            );
            if score < best_score {
                best_score = score;
                best_code = t.code.clone();
            }
        }

        if best_score > thresholds.template_match_threshold {
            debug!(
                "No template match for card at ({},{}): best={} score={:.3}",
                rect.x, rect.y, best_code, best_score
            );
            return None;
        }

        // Step 4: Suit verification via color
        // GGPoker uses 2-color deck: Hearts/Diamonds=Red, Spades/Clubs=Black
        let verified_code = verify_suit_by_color(rgba, rect, &best_code);
        let confidence = 1.0 - best_score / thresholds.template_match_threshold;

        debug!(
            "Card detected: {} (score={:.3}, conf={:.2}) at ({},{})",
            verified_code, best_score, confidence, rect.x, rect.y
        );

        Some((verified_code, confidence))
    }
}

/// Find white card-shaped rectangles using connected components.
fn find_white_card_regions(img: &RgbaImage, thresholds: &Thresholds) -> Vec<Rect> {
    let (w, h) = img.dimensions();
    let mask = color::white_mask(img.as_raw(), w, h, thresholds.white_pixel_min);

    // Simple connected-component labeling using flood fill
    let mut labels = vec![0u32; (w * h) as usize];
    let mut next_label = 1u32;
    let mut rects: Vec<(u32, u32, u32, u32, u32)> = Vec::new(); // (min_x, min_y, max_x, max_y, area)

    for y in 0..h {
        for x in 0..w {
            let idx = (y * w + x) as usize;
            if mask[idx] && labels[idx] == 0 {
                // Flood fill
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

                    if cx > 0 {
                        stack.push((cx - 1, cy));
                    }
                    if cx + 1 < w {
                        stack.push((cx + 1, cy));
                    }
                    if cy > 0 {
                        stack.push((cx, cy - 1));
                    }
                    if cy + 1 < h {
                        stack.push((cx, cy + 1));
                    }
                }

                rects.push((min_x, min_y, max_x, max_y, area));
            }
        }
    }

    // Filter for card-shaped rectangles
    rects
        .into_iter()
        .filter_map(|(min_x, min_y, max_x, max_y, area)| {
            let rw = max_x - min_x + 1;
            let rh = max_y - min_y + 1;
            let aspect = rw as f32 / rh as f32;

            if area >= thresholds.card_area_min
                && area <= thresholds.card_area_max
                && aspect >= thresholds.card_aspect_min
                && aspect <= thresholds.card_aspect_max
            {
                Some(Rect::new(min_x, min_y, rw, rh))
            } else {
                None
            }
        })
        .collect()
}

/// Verify/correct suit based on color analysis.
/// Uses the 2-color deck convention: H/D = Red, S/C = Black.
fn verify_suit_by_color(img: &RgbaImage, rect: &Rect, code: &str) -> String {
    if code.len() < 2 {
        return code.to_string();
    }

    let rank = &code[..code.len() - 1];
    let suit = &code[code.len() - 1..];

    // Sample the suit area (lower portion of the top-left corner)
    let suit_x = rect.x + 5;
    let suit_y = rect.y + rect.h * 35 / 100;
    let suit_w = rect.w * 30 / 100;
    let suit_h = rect.h * 25 / 100;

    let mut red_count = 0u32;
    let mut black_count = 0u32;
    let (iw, ih) = img.dimensions();

    for y in suit_y..((suit_y + suit_h).min(ih)) {
        for x in suit_x..((suit_x + suit_w).min(iw)) {
            let p = img.get_pixel(x, y);
            let (h, s, v) = color::rgb_to_hsv(p[0], p[1], p[2]);

            if s > 80 && v > 80 {
                if h <= 15 || h >= 165 {
                    red_count += 1;
                }
            }
            if v < 80 && s < 60 {
                black_count += 1;
            }
        }
    }

    let is_red_suit = red_count > black_count * 2;
    let current_is_red = suit == "H" || suit == "D";

    if is_red_suit == current_is_red {
        // Color matches template's suit type, keep as-is
        code.to_string()
    } else if is_red_suit {
        // Template said black suit but color is red
        // Keep the rank, change to most likely red suit (H is more common in matches)
        if suit == "S" {
            format!("{}H", rank)
        } else {
            format!("{}D", rank)
        }
    } else {
        // Template said red suit but color is black
        if suit == "H" {
            format!("{}S", rank)
        } else {
            format!("{}C", rank)
        }
    }
}

/// Remove duplicate detections at similar positions, keeping highest confidence.
fn deduplicate_cards(cards: &mut Vec<DetectedCard>) {
    cards.sort_by(|a, b| b.confidence.partial_cmp(&a.confidence).unwrap());

    let mut keep = vec![true; cards.len()];
    for i in 0..cards.len() {
        if !keep[i] {
            continue;
        }
        for j in (i + 1)..cards.len() {
            if !keep[j] {
                continue;
            }
            let dx = (cards[i].x as i32 - cards[j].x as i32).unsigned_abs();
            let dy = (cards[i].y as i32 - cards[j].y as i32).unsigned_abs();
            if dx < 30 && dy < 30 {
                keep[j] = false;
            }
        }
    }

    let mut i = 0;
    cards.retain(|_| {
        let k = keep[i];
        i += 1;
        k
    });
}
