use image::GrayImage;

/// Template matching using Sum of Squared Differences (Normalized).
/// Lower score = better match. Equivalent to OpenCV TM_SQDIFF_NORMED.
///
/// Returns (best_score, best_x, best_y) where (x,y) is the top-left of best match.
pub fn match_template_sqdiff(image: &GrayImage, template: &GrayImage) -> (f32, u32, u32) {
    let (iw, ih) = image.dimensions();
    let (tw, th) = template.dimensions();

    if tw > iw || th > ih {
        return (f32::MAX, 0, 0);
    }

    let mut best_score = f32::MAX;
    let mut best_x = 0u32;
    let mut best_y = 0u32;

    // Precompute template sum of squares
    let template_sq_sum: f64 = template
        .pixels()
        .map(|p| (p[0] as f64) * (p[0] as f64))
        .sum();

    if template_sq_sum == 0.0 {
        return (f32::MAX, 0, 0);
    }

    for y in 0..=(ih - th) {
        for x in 0..=(iw - tw) {
            let mut ssd: f64 = 0.0;
            let mut img_sq_sum: f64 = 0.0;

            for ty in 0..th {
                for tx in 0..tw {
                    let ip = image.get_pixel(x + tx, y + ty)[0] as f64;
                    let tp = template.get_pixel(tx, ty)[0] as f64;
                    let diff = ip - tp;
                    ssd += diff * diff;
                    img_sq_sum += ip * ip;
                }
            }

            let denominator = (img_sq_sum * template_sq_sum).sqrt();
            let score = if denominator > 0.0 {
                ssd / denominator
            } else {
                f32::MAX as f64
            };

            if (score as f32) < best_score {
                best_score = score as f32;
                best_x = x;
                best_y = y;
            }
        }
    }

    (best_score, best_x, best_y)
}

/// Multi-scale template matching. Tries multiple scales and returns the best match.
pub fn match_template_multiscale(
    image: &GrayImage,
    template: &GrayImage,
    scales: &[f32],
) -> (f32, u32, u32, f32) {
    let mut best_score = f32::MAX;
    let mut best_x = 0u32;
    let mut best_y = 0u32;
    let mut best_scale = 1.0f32;

    for &scale in scales {
        let scaled = if (scale - 1.0).abs() < 0.001 {
            template.clone()
        } else {
            let new_w = ((template.width() as f32) * scale) as u32;
            let new_h = ((template.height() as f32) * scale) as u32;
            if new_w == 0 || new_h == 0 {
                continue;
            }
            image::imageops::resize(template, new_w, new_h, image::imageops::FilterType::Nearest)
        };

        let (score, x, y) = match_template_sqdiff(image, &scaled);
        if score < best_score {
            best_score = score;
            best_x = x;
            best_y = y;
            best_scale = scale;
        }
    }

    (best_score, best_x, best_y, best_scale)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exact_match() {
        let img = GrayImage::from_raw(4, 4, vec![
            0, 0, 0, 0,
            0, 100, 200, 0,
            0, 150, 250, 0,
            0, 0, 0, 0,
        ]).unwrap();

        let tmpl = GrayImage::from_raw(2, 2, vec![
            100, 200,
            150, 250,
        ]).unwrap();

        let (score, x, y) = match_template_sqdiff(&img, &tmpl);
        assert!(score < 0.01, "Exact match should have near-zero score, got {}", score);
        assert_eq!(x, 1);
        assert_eq!(y, 1);
    }

    #[test]
    fn test_no_match() {
        let img = GrayImage::from_raw(4, 4, vec![
            0, 0, 0, 0,
            0, 0, 0, 0,
            0, 0, 0, 0,
            0, 0, 0, 0,
        ]).unwrap();

        let tmpl = GrayImage::from_raw(2, 2, vec![
            200, 200,
            200, 200,
        ]).unwrap();

        let (score, _, _) = match_template_sqdiff(&img, &tmpl);
        // Dark image vs bright template should have high score
        assert!(score > 0.5, "No match should have high score, got {}", score);
    }
}
