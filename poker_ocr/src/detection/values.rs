use regex::Regex;

/// Parse blinds from a window title like "Spin & Gold $0.25 - Blinds 15 | 30"
pub fn parse_blinds_from_title(title: &str) -> (f64, f64) {
    // Try "Blinds X | Y" pattern
    let re = Regex::new(r"Blinds\s+(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)").unwrap();
    if let Some(caps) = re.captures(title) {
        let sb = caps[1].parse::<f64>().unwrap_or(0.0);
        let bb = caps[2].parse::<f64>().unwrap_or(0.0);
        return (sb, bb);
    }

    // Try "$X/$Y" pattern
    let re2 = Regex::new(r"\$(\d+(?:\.\d+)?)\s*/\s*\$(\d+(?:\.\d+)?)").unwrap();
    if let Some(caps) = re2.captures(title) {
        let sb = caps[1].parse::<f64>().unwrap_or(0.0);
        let bb = caps[2].parse::<f64>().unwrap_or(0.0);
        return (sb, bb);
    }

    (0.0, 0.0)
}

/// Parse a numeric value from OCR text.
/// Handles: "$1,234", "1.5K", "2M", "150", "$0.25"
pub fn parse_poker_number(text: &str) -> Option<f64> {
    let cleaned = text
        .trim()
        .replace('$', "")
        .replace(',', "")
        .replace(' ', "");

    if cleaned.is_empty() {
        return None;
    }

    // Handle K/M suffixes
    if let Some(num_str) = cleaned.strip_suffix('K').or(cleaned.strip_suffix('k')) {
        return num_str.parse::<f64>().ok().map(|v| v * 1000.0);
    }
    if let Some(num_str) = cleaned.strip_suffix('M').or(cleaned.strip_suffix('m')) {
        return num_str.parse::<f64>().ok().map(|v| v * 1_000_000.0);
    }

    cleaned.parse::<f64>().ok()
}

/// Determine street from number of board cards.
pub fn street_from_board_count(n: usize) -> &'static str {
    match n {
        0 => "Preflop",
        3 => "Flop",
        4 => "Turn",
        5 => "River",
        _ => "Unknown",
    }
}

/// Parse button text to extract action type and amount.
/// Examples: "Call 30" -> ("call", Some(30.0))
///           "Raise to 120" -> ("raise", Some(120.0))
///           "Check" -> ("check", None)
///           "Fold" -> ("fold", None)
///           "All-In" -> ("all_in", None)
pub fn parse_button_text(text: &str) -> (String, Option<f64>) {
    let lower = text.to_lowercase();
    let lower = lower.trim();

    if lower.starts_with("call") {
        let amount = parse_poker_number(&lower[4..]);
        ("call".into(), amount)
    } else if lower.starts_with("raise") {
        // "Raise to 120" or "Raise 120"
        let rest = lower.strip_prefix("raise").unwrap_or("");
        let rest = rest.strip_prefix(" to").unwrap_or(rest);
        let amount = parse_poker_number(rest);
        ("raise".into(), amount)
    } else if lower.starts_with("bet") {
        let amount = parse_poker_number(&lower[3..]);
        ("bet".into(), amount)
    } else if lower.starts_with("check") {
        ("check".into(), None)
    } else if lower.starts_with("fold") {
        ("fold".into(), None)
    } else if lower.contains("all") && lower.contains("in") {
        // Try to extract amount from "All-In 500"
        let re = Regex::new(r"(\d+(?:\.\d+)?)").unwrap();
        let amount = re.find(&lower).and_then(|m| m.as_str().parse::<f64>().ok());
        ("all_in".into(), amount)
    } else {
        (lower.to_string(), None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_blinds() {
        assert_eq!(parse_blinds_from_title("Spin & Gold $0.25 - Blinds 15 | 30"), (15.0, 30.0));
        assert_eq!(parse_blinds_from_title("NL Hold'em - $0.05/$0.10"), (0.05, 0.10));
        assert_eq!(parse_blinds_from_title("Some random title"), (0.0, 0.0));
    }

    #[test]
    fn test_parse_poker_number() {
        assert_eq!(parse_poker_number("$1,234"), Some(1234.0));
        assert_eq!(parse_poker_number("1.5K"), Some(1500.0));
        assert_eq!(parse_poker_number("2M"), Some(2_000_000.0));
        assert_eq!(parse_poker_number("150"), Some(150.0));
        assert_eq!(parse_poker_number("$0.25"), Some(0.25));
        assert_eq!(parse_poker_number(""), None);
    }

    #[test]
    fn test_parse_button_text() {
        assert_eq!(parse_button_text("Call 30"), ("call".into(), Some(30.0)));
        assert_eq!(parse_button_text("Raise to 120"), ("raise".into(), Some(120.0)));
        assert_eq!(parse_button_text("Check"), ("check".into(), None));
        assert_eq!(parse_button_text("Fold"), ("fold".into(), None));
        assert_eq!(parse_button_text("All-In 500"), ("all_in".into(), Some(500.0)));
    }
}
