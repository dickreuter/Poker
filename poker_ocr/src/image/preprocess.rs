use image::{GrayImage, RgbaImage, Luma};

/// Convert RGBA to grayscale.
pub fn to_grayscale(img: &RgbaImage) -> GrayImage {
    let (w, h) = img.dimensions();
    let mut gray = GrayImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let p = img.get_pixel(x, y);
            // Standard luminance formula
            let lum = (0.299 * p[0] as f32 + 0.587 * p[1] as f32 + 0.114 * p[2] as f32) as u8;
            gray.put_pixel(x, y, Luma([lum]));
        }
    }
    gray
}

/// Binary threshold: pixels >= threshold become 255, else 0.
pub fn threshold(img: &GrayImage, thresh: u8) -> GrayImage {
    let (w, h) = img.dimensions();
    let mut out = GrayImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let v = img.get_pixel(x, y)[0];
            out.put_pixel(x, y, Luma([if v >= thresh { 255 } else { 0 }]));
        }
    }
    out
}

/// Invert a grayscale image.
pub fn invert(img: &GrayImage) -> GrayImage {
    let (w, h) = img.dimensions();
    let mut out = GrayImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            out.put_pixel(x, y, Luma([255 - img.get_pixel(x, y)[0]]));
        }
    }
    out
}

/// Upscale image by integer factor using nearest-neighbor.
pub fn upscale(img: &GrayImage, factor: u32) -> GrayImage {
    if factor <= 1 {
        return img.clone();
    }
    let (w, h) = img.dimensions();
    image::imageops::resize(img, w * factor, h * factor, image::imageops::FilterType::Nearest)
}

/// Crop a sub-region from an RGBA image.
pub fn crop_rgba(img: &RgbaImage, x: u32, y: u32, w: u32, h: u32) -> RgbaImage {
    let (iw, ih) = img.dimensions();
    let x = x.min(iw.saturating_sub(1));
    let y = y.min(ih.saturating_sub(1));
    let w = w.min(iw.saturating_sub(x));
    let h = h.min(ih.saturating_sub(y));
    image::imageops::crop_imm(img, x, y, w, h).to_image()
}

/// Adaptive threshold using local mean (simplified Gaussian adaptive).
/// Window size should be odd.
pub fn adaptive_threshold(img: &GrayImage, block_size: u32, c: i32) -> GrayImage {
    let (w, h) = img.dimensions();
    let half = (block_size / 2) as i32;
    let mut out = GrayImage::new(w, h);

    for y in 0..h {
        for x in 0..w {
            // Compute local mean
            let mut sum = 0u32;
            let mut count = 0u32;
            for dy in -half..=half {
                for dx in -half..=half {
                    let nx = x as i32 + dx;
                    let ny = y as i32 + dy;
                    if nx >= 0 && nx < w as i32 && ny >= 0 && ny < h as i32 {
                        sum += img.get_pixel(nx as u32, ny as u32)[0] as u32;
                        count += 1;
                    }
                }
            }
            let mean = (sum / count.max(1)) as i32;
            let val = img.get_pixel(x, y)[0] as i32;
            out.put_pixel(x, y, Luma([if val > mean - c { 255 } else { 0 }]));
        }
    }
    out
}

/// Simple morphological erosion with a square kernel.
pub fn erode(img: &GrayImage, kernel_size: u32) -> GrayImage {
    let (w, h) = img.dimensions();
    let half = (kernel_size / 2) as i32;
    let mut out = GrayImage::new(w, h);

    for y in 0..h {
        for x in 0..w {
            let mut min_val = 255u8;
            for dy in -half..=half {
                for dx in -half..=half {
                    let nx = x as i32 + dx;
                    let ny = y as i32 + dy;
                    if nx >= 0 && nx < w as i32 && ny >= 0 && ny < h as i32 {
                        min_val = min_val.min(img.get_pixel(nx as u32, ny as u32)[0]);
                    }
                }
            }
            out.put_pixel(x, y, Luma([min_val]));
        }
    }
    out
}

/// Simple morphological dilation with a square kernel.
pub fn dilate(img: &GrayImage, kernel_size: u32) -> GrayImage {
    let (w, h) = img.dimensions();
    let half = (kernel_size / 2) as i32;
    let mut out = GrayImage::new(w, h);

    for y in 0..h {
        for x in 0..w {
            let mut max_val = 0u8;
            for dy in -half..=half {
                for dx in -half..=half {
                    let nx = x as i32 + dx;
                    let ny = y as i32 + dy;
                    if nx >= 0 && nx < w as i32 && ny >= 0 && ny < h as i32 {
                        max_val = max_val.max(img.get_pixel(nx as u32, ny as u32)[0]);
                    }
                }
            }
            out.put_pixel(x, y, Luma([max_val]));
        }
    }
    out
}
