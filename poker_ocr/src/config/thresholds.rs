use serde::{Deserialize, Serialize};

/// All configurable thresholds for detection.
/// Can be loaded from a JSON file for runtime tuning.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Thresholds {
    // Card detection
    pub white_pixel_min: u8,
    pub card_area_min: u32,
    pub card_area_max: u32,
    pub card_aspect_min: f32,
    pub card_aspect_max: f32,
    pub template_match_threshold: f32,
    pub template_scales: Vec<f32>,

    // Button detection (HSV ranges)
    pub hsv_green_lower: [u8; 3],
    pub hsv_green_upper: [u8; 3],
    pub hsv_orange_lower: [u8; 3],
    pub hsv_orange_upper: [u8; 3],
    pub hsv_gray_lower: [u8; 3],
    pub hsv_gray_upper: [u8; 3],
    pub hsv_red_lower: [u8; 3],
    pub hsv_red_upper: [u8; 3],
    pub button_area_min: u32,
    pub button_min_width: u32,
    pub button_min_height: u32,

    // Regions (percentage of table dimensions)
    pub card_region_y_start: f32,
    pub card_region_y_end: f32,
    pub card_region_x_start: f32,
    pub card_region_x_end: f32,
    pub board_region_y_start: f32,
    pub board_region_y_end: f32,
    pub board_region_x_start: f32,
    pub board_region_x_end: f32,
    pub button_region_y_start: f32,
    pub pot_region_y_start: f32,
    pub pot_region_y_end: f32,
    pub pot_region_x_start: f32,
    pub pot_region_x_end: f32,

    // Retina
    pub retina_scale: u32,
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            // Card detection
            white_pixel_min: 180,
            card_area_min: 1500,
            card_area_max: 50000,
            card_aspect_min: 0.5,
            card_aspect_max: 0.9,
            template_match_threshold: 0.35,
            template_scales: vec![0.5, 0.75, 1.0, 1.25, 1.5],

            // Button HSV ranges (matching Python constants.py)
            hsv_green_lower: [35, 50, 100],
            hsv_green_upper: [85, 255, 255],
            hsv_orange_lower: [8, 80, 80],
            hsv_orange_upper: [25, 255, 255],
            hsv_gray_lower: [0, 0, 60],
            hsv_gray_upper: [180, 40, 140],
            hsv_red_lower: [0, 100, 100],
            hsv_red_upper: [15, 255, 255],
            button_area_min: 1500,
            button_min_width: 50,
            button_min_height: 25,

            // Regions
            card_region_y_start: 0.55,
            card_region_y_end: 0.90,
            card_region_x_start: 0.20,
            card_region_x_end: 0.80,
            board_region_y_start: 0.30,
            board_region_y_end: 0.55,
            board_region_x_start: 0.20,
            board_region_x_end: 0.80,
            button_region_y_start: 0.60,
            pot_region_y_start: 0.20,
            pot_region_y_end: 0.35,
            pot_region_x_start: 0.30,
            pot_region_x_end: 0.70,

            // Retina
            retina_scale: 2,
        }
    }
}

impl Thresholds {
    pub fn load_from_file(path: &str) -> anyhow::Result<Self> {
        let contents = std::fs::read_to_string(path)?;
        let val: serde_json::Value = serde_json::from_str(&contents)?;

        let mut t = Self::default();

        // Override fields that exist in the JSON
        if let Some(v) = val.get("white_pixel_min").and_then(|v| v.as_u64()) {
            t.white_pixel_min = v as u8;
        }
        if let Some(v) = val.get("card_area_min").and_then(|v| v.as_u64()) {
            t.card_area_min = v as u32;
        }
        if let Some(v) = val.get("match_score_max").and_then(|v| v.as_f64()) {
            t.template_match_threshold = v as f32;
        }
        if let Some(arr) = val.get("hsv_green_lower").and_then(|v| v.as_array()) {
            if arr.len() == 3 {
                t.hsv_green_lower = [
                    arr[0].as_u64().unwrap_or(35) as u8,
                    arr[1].as_u64().unwrap_or(50) as u8,
                    arr[2].as_u64().unwrap_or(50) as u8,
                ];
                // Sanity check: green hue must be in green range
                if t.hsv_green_lower[0] < 20 || t.hsv_green_lower[1] < 20 {
                    tracing::warn!("HSV green lower drifted to nonsense, resetting");
                    t.hsv_green_lower = [35, 50, 50];
                }
            }
        }
        if let Some(arr) = val.get("hsv_green_upper").and_then(|v| v.as_array()) {
            if arr.len() == 3 {
                t.hsv_green_upper = [
                    arr[0].as_u64().unwrap_or(85) as u8,
                    arr[1].as_u64().unwrap_or(255) as u8,
                    arr[2].as_u64().unwrap_or(255) as u8,
                ];
            }
        }
        if let Some(arr) = val.get("hsv_orange_lower").and_then(|v| v.as_array()) {
            if arr.len() == 3 {
                t.hsv_orange_lower = [
                    arr[0].as_u64().unwrap_or(8) as u8,
                    arr[1].as_u64().unwrap_or(80) as u8,
                    arr[2].as_u64().unwrap_or(80) as u8,
                ];
            }
        }
        if let Some(arr) = val.get("hsv_orange_upper").and_then(|v| v.as_array()) {
            if arr.len() == 3 {
                t.hsv_orange_upper = [
                    arr[0].as_u64().unwrap_or(25) as u8,
                    arr[1].as_u64().unwrap_or(255) as u8,
                    arr[2].as_u64().unwrap_or(255) as u8,
                ];
            }
        }
        if let Some(v) = val.get("button_area_min").and_then(|v| v.as_u64()) {
            t.button_area_min = v as u32;
        }
        if let Some(v) = val.get("button_region_y_start").and_then(|v| v.as_f64()) {
            t.button_region_y_start = v as f32;
        }

        Ok(t)
    }
}
