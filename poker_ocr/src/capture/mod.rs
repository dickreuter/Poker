pub mod window;

use anyhow::Result;
use image::RgbaImage;

/// Capture a specific window by CGWindowID using Core Graphics.
/// Returns an RGBA image at physical (Retina) resolution.
pub fn capture_window(window_id: u32) -> Result<(RgbaImage, WindowInfo)> {
    let info = window::get_window_info(window_id)?;
    let img = capture_window_cg(window_id, &info)?;
    Ok((img, info))
}

#[derive(Debug, Clone)]
pub struct WindowInfo {
    pub window_id: u32,
    pub name: String,
    pub x_pt: i32,
    pub y_pt: i32,
    pub w_pt: i32,
    pub h_pt: i32,
}

/// Capture window using CGWindowListCreateImage (Core Graphics).
fn capture_window_cg(window_id: u32, info: &WindowInfo) -> Result<RgbaImage> {
    use core_graphics::display::*;
    use core_graphics::geometry::{CGPoint, CGRect, CGSize};

    let bounds = CGRect::new(
        &CGPoint::new(info.x_pt as f64, info.y_pt as f64),
        &CGSize::new(info.w_pt as f64, info.h_pt as f64),
    );

    // Capture the specific window
    let cg_image = CGDisplay::screenshot(
        bounds,
        kCGWindowListOptionIncludingWindow,
        window_id,
        kCGWindowImageBoundsIgnoreFraming,
    )
    .ok_or_else(|| anyhow::anyhow!("Failed to capture window {}", window_id))?;

    let width = cg_image.width();
    let height = cg_image.height();
    let bytes_per_row = cg_image.bytes_per_row();
    let data = cg_image.data();
    let raw_bytes: &[u8] = &data;

    // CG images are BGRA, convert to RGBA
    let mut rgba_buf = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        let row_start = y * bytes_per_row;
        for x in 0..width {
            let offset = row_start + x * 4;
            if offset + 3 < raw_bytes.len() {
                rgba_buf.push(raw_bytes[offset + 2]); // R (from B)
                rgba_buf.push(raw_bytes[offset + 1]); // G
                rgba_buf.push(raw_bytes[offset]);     // B (from R)
                rgba_buf.push(raw_bytes[offset + 3]); // A
            } else {
                rgba_buf.extend_from_slice(&[0, 0, 0, 255]);
            }
        }
    }

    RgbaImage::from_raw(width as u32, height as u32, rgba_buf)
        .ok_or_else(|| anyhow::anyhow!("Failed to create image from captured data"))
}

/// Load a screenshot from a file path.
pub fn load_screenshot(path: &str) -> Result<RgbaImage> {
    let img = image::open(path)?;
    Ok(img.to_rgba8())
}
