/// RGB to HSV conversion (pure Rust, no OpenCV dependency).
/// H: 0-180 (matching OpenCV convention), S: 0-255, V: 0-255
pub fn rgb_to_hsv(r: u8, g: u8, b: u8) -> (u8, u8, u8) {
    let rf = r as f32 / 255.0;
    let gf = g as f32 / 255.0;
    let bf = b as f32 / 255.0;

    let max = rf.max(gf).max(bf);
    let min = rf.min(gf).min(bf);
    let delta = max - min;

    // Value
    let v = max;

    // Saturation
    let s = if max == 0.0 { 0.0 } else { delta / max };

    // Hue
    let h = if delta == 0.0 {
        0.0
    } else if max == rf {
        60.0 * (((gf - bf) / delta) % 6.0)
    } else if max == gf {
        60.0 * (((bf - rf) / delta) + 2.0)
    } else {
        60.0 * (((rf - gf) / delta) + 4.0)
    };

    let h = if h < 0.0 { h + 360.0 } else { h };

    // Convert to OpenCV convention: H=0-180, S=0-255, V=0-255
    ((h / 2.0) as u8, (s * 255.0) as u8, (v * 255.0) as u8)
}

/// Check if HSV value is within a range (inclusive).
#[inline]
pub fn hsv_in_range(h: u8, s: u8, v: u8, lower: [u8; 3], upper: [u8; 3]) -> bool {
    h >= lower[0] && h <= upper[0]
        && s >= lower[1] && s <= upper[1]
        && v >= lower[2] && v <= upper[2]
}

/// Create a binary mask from an RGBA image where pixels match the HSV range.
/// Returns a Vec<bool> with dimensions (width * height).
pub fn hsv_mask(
    rgba_data: &[u8],
    width: u32,
    height: u32,
    lower: [u8; 3],
    upper: [u8; 3],
) -> Vec<bool> {
    let len = (width * height) as usize;
    let mut mask = vec![false; len];

    for i in 0..len {
        let offset = i * 4;
        if offset + 2 < rgba_data.len() {
            let r = rgba_data[offset];
            let g = rgba_data[offset + 1];
            let b = rgba_data[offset + 2];
            let (h, s, v) = rgb_to_hsv(r, g, b);
            mask[i] = hsv_in_range(h, s, v, lower, upper);
        }
    }
    mask
}

/// Check if a pixel is "white" (all channels above threshold).
#[inline]
pub fn is_white(r: u8, g: u8, b: u8, threshold: u8) -> bool {
    r >= threshold && g >= threshold && b >= threshold
}

/// Create a binary mask of white pixels from RGBA data.
pub fn white_mask(rgba_data: &[u8], width: u32, height: u32, threshold: u8) -> Vec<bool> {
    let len = (width * height) as usize;
    let mut mask = vec![false; len];

    for i in 0..len {
        let offset = i * 4;
        if offset + 2 < rgba_data.len() {
            mask[i] = is_white(rgba_data[offset], rgba_data[offset + 1], rgba_data[offset + 2], threshold);
        }
    }
    mask
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rgb_to_hsv_red() {
        let (h, s, v) = rgb_to_hsv(255, 0, 0);
        assert_eq!(h, 0);
        assert_eq!(s, 255);
        assert_eq!(v, 255);
    }

    #[test]
    fn test_rgb_to_hsv_green() {
        let (h, s, v) = rgb_to_hsv(0, 255, 0);
        assert_eq!(h, 60); // 120/2 = 60
        assert_eq!(s, 255);
        assert_eq!(v, 255);
    }

    #[test]
    fn test_rgb_to_hsv_white() {
        let (h, s, v) = rgb_to_hsv(255, 255, 255);
        assert_eq!(s, 0); // White has no saturation
        assert_eq!(v, 255);
    }

    #[test]
    fn test_hsv_in_range() {
        // Green button: H=45, S=200, V=180
        assert!(hsv_in_range(45, 200, 180, [35, 50, 50], [85, 255, 255]));
        // White pixel should NOT match green
        assert!(!hsv_in_range(0, 0, 255, [35, 50, 50], [85, 255, 255]));
    }

    #[test]
    fn test_white_mask() {
        let data = vec![
            200, 200, 200, 255, // white-ish
            100, 100, 100, 255, // dark
            255, 255, 255, 255, // pure white
            180, 180, 180, 255, // exactly threshold
        ];
        let mask = white_mask(&data, 2, 2, 180);
        assert_eq!(mask, vec![true, false, true, true]);
    }
}
