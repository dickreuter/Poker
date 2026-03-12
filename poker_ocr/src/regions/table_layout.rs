use crate::config::Thresholds;

/// A rectangle region in pixel coordinates.
#[derive(Debug, Clone, Copy)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

impl Rect {
    pub fn new(x: u32, y: u32, w: u32, h: u32) -> Self {
        Self { x, y, w, h }
    }

    pub fn center(&self) -> (u32, u32) {
        (self.x + self.w / 2, self.y + self.h / 2)
    }

    pub fn area(&self) -> u32 {
        self.w * self.h
    }
}

/// Computes ROI regions from table dimensions using percentage-based layout.
pub struct TableLayout {
    pub table_w: u32,
    pub table_h: u32,
}

impl TableLayout {
    pub fn new(table_w: u32, table_h: u32) -> Self {
        Self { table_w, table_h }
    }

    /// Region where hero's cards are expected.
    pub fn hero_cards_region(&self, t: &Thresholds) -> Rect {
        let x = (self.table_w as f32 * t.card_region_x_start) as u32;
        let y = (self.table_h as f32 * t.card_region_y_start) as u32;
        let w = (self.table_w as f32 * (t.card_region_x_end - t.card_region_x_start)) as u32;
        let h = (self.table_h as f32 * (t.card_region_y_end - t.card_region_y_start)) as u32;
        Rect::new(x, y, w, h)
    }

    /// Region where community cards (board) are expected.
    pub fn board_cards_region(&self, t: &Thresholds) -> Rect {
        let x = (self.table_w as f32 * t.board_region_x_start) as u32;
        let y = (self.table_h as f32 * t.board_region_y_start) as u32;
        let w = (self.table_w as f32 * (t.board_region_x_end - t.board_region_x_start)) as u32;
        let h = (self.table_h as f32 * (t.board_region_y_end - t.board_region_y_start)) as u32;
        Rect::new(x, y, w, h)
    }

    /// Region where action buttons are expected.
    pub fn button_region(&self, t: &Thresholds) -> Rect {
        let y = (self.table_h as f32 * t.button_region_y_start) as u32;
        let h = self.table_h - y;
        Rect::new(0, y, self.table_w, h)
    }

    /// Region where pot display is expected.
    pub fn pot_region(&self, t: &Thresholds) -> Rect {
        let x = (self.table_w as f32 * t.pot_region_x_start) as u32;
        let y = (self.table_h as f32 * t.pot_region_y_start) as u32;
        let w = (self.table_w as f32 * (t.pot_region_x_end - t.pot_region_x_start)) as u32;
        let h = (self.table_h as f32 * (t.pot_region_y_end - t.pot_region_y_start)) as u32;
        Rect::new(x, y, w, h)
    }

    /// Player seat positions for a 3-max table.
    /// Returns (seat_index, name_region, stack_region, bet_region, card_region).
    pub fn player_seats_3max(&self) -> Vec<(usize, Rect)> {
        let w = self.table_w;
        let h = self.table_h;
        vec![
            // Seat 0: Hero (bottom center)
            (0, Rect::new(w * 30 / 100, h * 75 / 100, w * 40 / 100, h * 15 / 100)),
            // Seat 1: Villain left (top left)
            (1, Rect::new(w * 5 / 100, h * 15 / 100, w * 30 / 100, h * 15 / 100)),
            // Seat 2: Villain right (top right)
            (2, Rect::new(w * 65 / 100, h * 15 / 100, w * 30 / 100, h * 15 / 100)),
        ]
    }

    /// Player seat positions for a 6-max table.
    pub fn player_seats_6max(&self) -> Vec<(usize, Rect)> {
        let w = self.table_w;
        let h = self.table_h;
        vec![
            // Seat 0: Hero (bottom center)
            (0, Rect::new(w * 30 / 100, h * 75 / 100, w * 40 / 100, h * 15 / 100)),
            // Seat 1: Bottom left
            (1, Rect::new(w * 2 / 100, h * 55 / 100, w * 25 / 100, h * 15 / 100)),
            // Seat 2: Top left
            (2, Rect::new(w * 5 / 100, h * 15 / 100, w * 25 / 100, h * 15 / 100)),
            // Seat 3: Top center
            (3, Rect::new(w * 35 / 100, h * 5 / 100, w * 30 / 100, h * 15 / 100)),
            // Seat 4: Top right
            (4, Rect::new(w * 70 / 100, h * 15 / 100, w * 25 / 100, h * 15 / 100)),
            // Seat 5: Bottom right
            (5, Rect::new(w * 73 / 100, h * 55 / 100, w * 25 / 100, h * 15 / 100)),
        ]
    }
}
