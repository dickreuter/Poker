use std::path::PathBuf;
use std::time::Instant;

use anyhow::Result;
use clap::Parser;
use tracing::{debug, error};

use poker_ocr::capture;
use poker_ocr::config::Thresholds;
use poker_ocr::detection::{buttons, cards, values};
use poker_ocr::output::game_state::GameState;
use poker_ocr::regions::TableLayout;

#[derive(Parser, Debug)]
#[command(name = "poker_ocr", about = "Fast poker table OCR for GGSystem on macOS")]
struct Args {
    /// Window ID (CGWindowID) to capture
    #[arg(long)]
    window_id: Option<u32>,

    /// Scan mode: 'full' or 'buttons_only'
    #[arg(long, default_value = "full")]
    mode: String,

    /// Comma-separated window IDs for parallel multi-table scan
    #[arg(long)]
    multi: Option<String>,

    /// Process a saved screenshot instead of live capture
    #[arg(long)]
    screenshot: Option<String>,

    /// List all GGSystem windows and exit
    #[arg(long)]
    list_windows: bool,

    /// Save debug images to this directory
    #[arg(long)]
    debug_dir: Option<String>,

    /// Path to thresholds.json for custom thresholds
    #[arg(long)]
    thresholds: Option<String>,

    /// Path to card template directory
    #[arg(long)]
    templates: Option<String>,
}

fn main() -> Result<()> {
    // Initialize tracing (logs go to stderr, JSON output to stdout)
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn")),
        )
        .with_writer(std::io::stderr)
        .init();

    let args = Args::parse();

    // Handle --list-windows
    if args.list_windows {
        return list_windows();
    }

    // Load thresholds
    let thresholds = if let Some(ref path) = args.thresholds {
        Thresholds::load_from_file(path).unwrap_or_else(|e| {
            eprintln!("Warning: failed to load thresholds from {}: {}", path, e);
            Thresholds::default()
        })
    } else {
        // Try default location relative to binary
        let default_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap_or(&PathBuf::from("."))
            .join("data/learning/thresholds.json");
        if default_path.exists() {
            Thresholds::load_from_file(default_path.to_str().unwrap())
                .unwrap_or_default()
        } else {
            Thresholds::default()
        }
    };

    // Load card templates
    let template_dir = args
        .templates
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("assets/card_templates")
        });
    let card_detector = cards::CardDetector::new(&template_dir);

    // Handle --multi
    if let Some(ref multi_ids) = args.multi {
        let window_ids: Vec<u32> = multi_ids
            .split(',')
            .filter_map(|s| s.trim().parse().ok())
            .collect();
        return process_multi(&window_ids, &args.mode, &thresholds, &card_detector, args.debug_dir.as_deref());
    }

    // Handle --screenshot
    if let Some(ref path) = args.screenshot {
        let state = process_screenshot(path, &args.mode, &thresholds, &card_detector, args.debug_dir.as_deref())?;
        println!("{}", serde_json::to_string(&state)?);
        return Ok(());
    }

    // Handle --window-id
    if let Some(window_id) = args.window_id {
        let state = process_window(window_id, &args.mode, &thresholds, &card_detector, args.debug_dir.as_deref())?;
        println!("{}", serde_json::to_string(&state)?);
        return Ok(());
    }

    eprintln!("Error: specify --window-id, --screenshot, --multi, or --list-windows");
    std::process::exit(1);
}

fn list_windows() -> Result<()> {
    let windows = capture::window::list_ggpoker_windows()?;
    let json = serde_json::to_string_pretty(&windows)?;
    println!("{}", json);
    Ok(())
}

fn process_window(
    window_id: u32,
    mode: &str,
    thresholds: &Thresholds,
    card_detector: &cards::CardDetector,
    debug_dir: Option<&str>,
) -> Result<GameState> {
    let start = Instant::now();

    let (img, win_info) = capture::capture_window(window_id)?;
    let capture_ms = start.elapsed().as_secs_f64() * 1000.0;
    debug!("Capture took {:.1}ms", capture_ms);

    let mut state = analyze_image(
        &img,
        mode,
        thresholds,
        card_detector,
        win_info.window_id,
        &win_info.name,
        win_info.x_pt,
        win_info.y_pt,
        win_info.w_pt,
        win_info.h_pt,
    );

    state.ocr_latency_ms = start.elapsed().as_secs_f64() * 1000.0;

    if let Some(dir) = debug_dir {
        save_debug_images(&img, &state, dir)?;
    }

    Ok(state)
}

fn process_screenshot(
    path: &str,
    mode: &str,
    thresholds: &Thresholds,
    card_detector: &cards::CardDetector,
    debug_dir: Option<&str>,
) -> Result<GameState> {
    let start = Instant::now();

    let img = capture::load_screenshot(path)?;
    let (w, h) = img.dimensions();

    let mut state = analyze_image(
        &img,
        mode,
        thresholds,
        card_detector,
        0,
        path,
        0,
        0,
        (w / thresholds.retina_scale) as i32,
        (h / thresholds.retina_scale) as i32,
    );

    state.ocr_latency_ms = start.elapsed().as_secs_f64() * 1000.0;

    if let Some(dir) = debug_dir {
        save_debug_images(&img, &state, dir)?;
    }

    Ok(state)
}

fn process_multi(
    window_ids: &[u32],
    mode: &str,
    thresholds: &Thresholds,
    card_detector: &cards::CardDetector,
    debug_dir: Option<&str>,
) -> Result<()> {
    use rayon::prelude::*;

    let states: Vec<GameState> = window_ids
        .par_iter()
        .filter_map(|&wid| {
            process_window(wid, mode, thresholds, card_detector, debug_dir)
                .map_err(|e| {
                    error!("Failed to process window {}: {}", wid, e);
                    e
                })
                .ok()
        })
        .collect();

    println!("{}", serde_json::to_string(&states)?);
    Ok(())
}

fn analyze_image(
    img: &image::RgbaImage,
    mode: &str,
    thresholds: &Thresholds,
    card_detector: &cards::CardDetector,
    window_id: u32,
    window_name: &str,
    x_pt: i32,
    y_pt: i32,
    w_pt: i32,
    h_pt: i32,
) -> GameState {
    let (img_w, img_h) = img.dimensions();
    let layout = TableLayout::new(img_w, img_h);

    let mut state = GameState::empty(window_id);
    state.window_name = window_name.to_string();
    state.table_x_pt = x_pt;
    state.table_y_pt = y_pt;
    state.table_w_pt = w_pt;
    state.table_h_pt = h_pt;

    // Parse blinds from window title
    let (sb, bb) = values::parse_blinds_from_title(window_name);
    state.small_blind = sb;
    state.big_blind = bb;

    // Step 1: Button detection (always run)
    let button_region = layout.button_region(thresholds);
    state.available_actions = buttons::detect_buttons(
        img,
        &button_region,
        thresholds,
        x_pt,
        y_pt,
        thresholds.retina_scale,
    );
    state.is_my_turn = !state.available_actions.is_empty();

    if mode == "buttons_only" {
        return state;
    }

    // Step 2: Card detection
    let hero_region = layout.hero_cards_region(thresholds);

    if cards::CardDetector::detect_card_backs(img, &hero_region) {
        state.cards_face_down = true;
        debug!("Cards are face-down");
    } else {
        let hero_cards = card_detector.detect_cards(img, &hero_region, thresholds);
        state.my_cards = hero_cards.iter().map(|c| c.code.clone()).collect();
    }

    // Step 3: Board cards
    let board_region = layout.board_cards_region(thresholds);
    let board_cards = card_detector.detect_cards(img, &board_region, thresholds);
    state.board_cards = board_cards.iter().map(|c| c.code.clone()).collect();

    // Step 4: Determine street
    state.street = values::street_from_board_count(state.board_cards.len()).to_string();

    state
}

fn save_debug_images(
    img: &image::RgbaImage,
    state: &GameState,
    dir: &str,
) -> Result<()> {
    std::fs::create_dir_all(dir)?;

    let path = format!("{}/capture_{}.png", dir, state.window_id);
    img.save(&path)?;
    debug!("Saved debug image to {}", path);

    let json_path = format!("{}/state_{}.json", dir, state.window_id);
    let json = serde_json::to_string_pretty(state)?;
    std::fs::write(&json_path, json)?;

    Ok(())
}
