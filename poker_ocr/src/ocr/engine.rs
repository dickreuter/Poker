use image::GrayImage;
use tracing::debug;

use crate::image::preprocess;

/// OCR engine for reading text from preprocessed images.
///
/// For now, this uses a simple digit recognition heuristic.
/// Phase 2 will add ONNX Runtime PaddleOCR models for full text recognition.
pub struct OCREngine {
    // ONNX runtime session will go here in Phase 2
}

impl OCREngine {
    pub fn new() -> Self {
        debug!("OCR Engine initialized (heuristic mode - ONNX models not yet loaded)");
        Self {}
    }

    /// Read text from a preprocessed grayscale image.
    /// Currently returns empty string - will be replaced with ONNX inference.
    pub fn read_text(&self, _img: &GrayImage) -> String {
        // Phase 2: ONNX PaddleOCR inference
        // For now, return empty - the value parsing functions handle blinds from title
        String::new()
    }

    /// Preprocess an image region for OCR.
    /// Upscales 2x, applies adaptive threshold, inverts for dark-on-light text.
    pub fn preprocess_for_ocr(img: &GrayImage) -> GrayImage {
        let upscaled = preprocess::upscale(img, 2);
        let thresh = preprocess::adaptive_threshold(&upscaled, 15, 5);
        preprocess::invert(&thresh)
    }
}
