use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct GameState {
    pub window_id: u32,
    pub window_name: String,
    pub table_x_pt: i32,
    pub table_y_pt: i32,
    pub table_w_pt: i32,
    pub table_h_pt: i32,

    pub my_cards: Vec<String>,
    pub board_cards: Vec<String>,
    pub cards_face_down: bool,

    pub pot: f64,
    pub current_street_pot: f64,
    pub call_amount: f64,
    pub min_raise_amount: f64,
    pub small_blind: f64,
    pub big_blind: f64,

    pub players: Vec<PlayerInfo>,
    pub hero_seat: i32,
    pub dealer_seat: i32,

    pub available_actions: Vec<AvailableAction>,

    pub street: String,
    pub is_my_turn: bool,
    pub ocr_latency_ms: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlayerInfo {
    pub seat: i32,
    pub name: String,
    pub stack: f64,
    pub current_bet: f64,
    pub is_active: bool,
    pub is_hero: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct AvailableAction {
    pub action_type: String,
    pub amount: Option<f64>,
    pub screen_x_pt: i32,
    pub screen_y_pt: i32,
    pub confidence: f64,
}

impl GameState {
    pub fn empty(window_id: u32) -> Self {
        Self {
            window_id,
            window_name: String::new(),
            table_x_pt: 0,
            table_y_pt: 0,
            table_w_pt: 0,
            table_h_pt: 0,
            my_cards: Vec::new(),
            board_cards: Vec::new(),
            cards_face_down: false,
            pot: 0.0,
            current_street_pot: 0.0,
            call_amount: 0.0,
            min_raise_amount: 0.0,
            small_blind: 0.0,
            big_blind: 0.0,
            players: Vec::new(),
            hero_seat: -1,
            dealer_seat: -1,
            available_actions: Vec::new(),
            street: "Unknown".into(),
            is_my_turn: false,
            ocr_latency_ms: 0.0,
        }
    }
}
