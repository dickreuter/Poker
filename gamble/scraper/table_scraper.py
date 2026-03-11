"""Recognize table"""
import logging
import cv2
import numpy as np

from gamble.scraper.table_scraper_nn import predict
from gamble.scraper.table_setup_actions_and_signals import CARD_SUITES, CARD_VALUES
from gamble.tools.helper import get_dir
from gamble.tools.screen_operations import take_screenshot, crop_screenshot_with_topleft_corner, \
    is_template_in_search_area, binary_pil_to_cv2, ocr, pil_to_cv2

# Import dynamic reader for fallback detection when templates fail
try:
    from gamble.tools.dynamic_table_reader import DynamicTableReader
    DYNAMIC_READER_AVAILABLE = True
except ImportError:
    DYNAMIC_READER_AVAILABLE = False

log = logging.getLogger(__name__)


class TableScraper:
    def __init__(self, table_dict):
        self.table_dict = table_dict
        self.screenshot = None

        self.total_players = 6 if not 'max_players' in self.table_dict else self.table_dict['max_players']['value']
        self.my_cards = None
        self.table_cards = None
        self.current_round_pot = None
        self.total_pot = None
        self.dealer_position = None
        self.players_in_game = None
        self.player_funds = None
        self.player_pots = None
        self.call_value = None
        self.raise_value = None
        self.call_button = None
        self.raise_button = None
        self.tlc = None

    def take_screenshot2(self):
        """Take a screenshot"""
        self.screenshot = take_screenshot()

    def crop_from_top_left_corner(self):
        """Crop top left corner based on the current selected table dict and replace self.screenshot with it.

        Uses template matching first, falls back to smart table finder (green felt detection) if that fails.
        """
        # Try template matching first
        self.screenshot, self.tlc = crop_screenshot_with_topleft_corner(self.screenshot,
                                                                        binary_pil_to_cv2(
                                                                            self.table_dict['topleft_corner']))

        # If template matching failed, try smart table finder
        if self.screenshot is None:
            log.info("Template matching failed, trying smart table finder...")
            try:
                from gamble.tools.smart_table_finder import SmartTableFinder
                from gamble.tools import constants as const

                finder = SmartTableFinder()
                table = finder.find_active_table(self.entireScreenPIL if hasattr(self, 'entireScreenPIL') else None)

                if table:
                    log.info(f"Smart finder found table at ({table.x}, {table.y}) {table.width}x{table.height}")
                    self.tlc = (table.x, table.y)

                    # Crop the table region
                    full_screenshot = self.entireScreenPIL if hasattr(self, 'entireScreenPIL') else take_screenshot()
                    self.screenshot = full_screenshot.crop((
                        table.x, table.y,
                        table.x + min(table.width, const.CROP_WIDTH),
                        table.y + min(table.height, const.CROP_HEIGHT)
                    ))
                    log.info(f"Smart table finder succeeded, tlc={self.tlc}")
                else:
                    log.warning("Smart table finder also failed to find table")
            except Exception as e:
                log.warning(f"Smart table finder error: {e}")

        return self.screenshot

    def lost_everything(self):
        """Check if lost everything has occurred"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'lost_everything', 'lost_everything_search_area')

    def im_back(self):
        """Check if I'm back button is visible using both templates and color detection."""
        # Try template matching first
        if is_template_in_search_area(self.table_dict, self.screenshot,
                                      'im_back', 'buttons_search_area'):
            log.info("Imback found via template matching")
            return True

        # Fallback to color detection (red button)
        try:
            from gamble.core.button_detector import ButtonDetector
            detector = ButtonDetector()
            # Convert PIL to BGR for CV2 if needed
            if self.screenshot:
                deal_me_in = detector.detect_deal_me_in(self.screenshot)
                if deal_me_in:
                    log.info(f"Imback found via color detection at ({deal_me_in['x']}, {deal_me_in['y']})")
                    # Store for mouse action if needed
                    self.last_deal_me_in_pos = (deal_me_in['x'], deal_me_in['y'])
                    return True
        except Exception as e:
            log.debug(f"Color-based im_back detection failed: {e}")

        return False

    def resume_hand(self):
        """Check if I'm back button is visible"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'resume_hand', 'buttons_search_area')

    def get_my_cards2(self):
        """Get my cards using multiple detection methods."""
        self.my_cards = []

        # Try smart card detection first if we have TLC from smart finder
        if hasattr(self, 'tlc') and self.tlc and hasattr(self, 'entireScreenPIL'):
            try:
                from gamble.tools.smart_card_detector import SmartCardDetector
                detector = SmartCardDetector(self.table_dict)

                # Build table region from TLC
                from gamble.tools import constants as const
                table_region = (self.tlc[0], self.tlc[1], const.CROP_WIDTH, const.CROP_HEIGHT)

                cards = detector.detect_cards(self.entireScreenPIL, table_region)
                if len(cards) == 2:
                    self.my_cards = cards
                    log.info(f"Smart card detection found: {cards}")
                    return
                else:
                    log.debug(f"Smart detection found {len(cards)} cards, trying fallback methods")
            except Exception as e:
                log.debug(f"Smart card detection error: {e}")

        if 'use_neural_network' in self.table_dict and (self.table_dict['use_neural_network'] == '2' or self.table_dict['use_neural_network'] == 'CheckState.Checked'):
            self.get_my_cards_nn()
        else:
            # Standard template matching
            for value in CARD_VALUES:
                for suit in CARD_SUITES:
                    if is_template_in_search_area(self.table_dict, self.screenshot,
                                                value.lower() + suit.lower(), 'my_cards_area', extended=True):
                        self.my_cards.append(value + suit)

            # Fallback to position-based detection if standard method fails
            if len(self.my_cards) != 2:
                log.debug(f"Standard detection found {len(self.my_cards)} cards, trying position-based")
                if self.get_my_cards_positioned():
                    log.info(f"Position-based detection succeeded: {self.my_cards}")
                    return

        # OCR-based card reading fallback (bypasses broken templates)
        if len(self.my_cards) != 2:
            try:
                from gamble.ocr.card_reader import read_player_cards
                screenshot_for_ocr = self.screenshot if self.screenshot else self.entireScreenPIL
                if screenshot_for_ocr:
                    ocr_cards = read_player_cards(screenshot_for_ocr)
                    if len(ocr_cards) == 2:
                        self.my_cards = ocr_cards
                        log.info(f"OCR card reader found: {ocr_cards}")
                        return
                    else:
                        log.debug(f"OCR card reader found {len(ocr_cards)} cards")
            except Exception as e:
                log.debug(f"OCR card reader error: {e}")

        if len(self.my_cards) != 2:
            log.warning("My cards not recognized")

            # SELF-LEARNING: When card detection fails, use vision analyzer to fix thresholds
            log.info("SELF-LEARNING: Entering auto-fix code path...")
            try:
                from gamble.tools.vision_analyzer import auto_fix_cards
                log.info("SELF-LEARNING: Import successful, analyzing image to find actual card positions...")

                fix_result = auto_fix_cards(self.screenshot)
                log.info(f"SELF-LEARNING: auto_fix_cards returned: {fix_result}")

                if fix_result and fix_result.get('fixed'):
                    log.info(f"SELF-LEARNING: Fixed card threshold -> {fix_result.get('new_threshold')}")
                    # Retry with new threshold
                    if self.get_my_cards_positioned():
                        log.info(f"SELF-LEARNING SUCCESS: Found cards after auto-fix: {self.my_cards}")
                else:
                    log.info("SELF-LEARNING: auto_fix_cards did not fix the issue")
            except Exception as e:
                log.warning(f"SELF-LEARNING FAILED: Vision analyzer error: {e}")
                import traceback
                log.warning(f"SELF-LEARNING TRACEBACK: {traceback.format_exc()}")

        log.info(f"My cards: {self.my_cards}")

    def get_my_cards_nn(self):
        left_card_area = self.table_dict['left_card_area']
        right_card_area = self.table_dict['right_card_area']
        left_card = self.screenshot.crop(
            (left_card_area['x1'], left_card_area['y1'], left_card_area['x2'], left_card_area['y2']))
        right_card = self.screenshot.crop(
            (right_card_area['x1'], right_card_area['y1'], right_card_area['x2'], right_card_area['y2']))
        self.my_cards = []

        card1 = predict(left_card, self.nn_model, self.table_dict['_class_mapping'])
        card2 = predict(right_card, self.nn_model, self.table_dict['_class_mapping'])
        self.my_cards.append(card1)
        self.my_cards.append(card2)

        try:
            left_card.save(get_dir('log') + '/pics/' + card1 + '.png')
        except:
            pass
        try:
            right_card.save(get_dir('log') + '/pics/' + card2 + '.png')
        except:
            pass

        for i in range(2):
            if 'empty_card' in self.my_cards:
                self.my_cards.remove('empty_card')

        if len(self.my_cards) == 2:
            log.info("My cards: " + str(self.my_cards))
            return True
        else:
            log.debug("Did not find two player cards: " + str(self.my_cards))
            return False

    def get_my_cards_positioned(self):
        """
        Position-based card detection with ranking.
        Extracts cards from exact known positions, matches against ALL templates,
        and returns the best 2 unique matches.
        """
        self.my_cards = []

        # Get card areas from table dict
        left_area = self.table_dict.get('left_card_area')
        right_area = self.table_dict.get('right_card_area')

        if not left_area or not right_area:
            log.warning("Card areas not defined in table dict")
            return False

        # Extract card regions from screenshot
        left_card = self.screenshot.crop((
            left_area['x1'], left_area['y1'],
            left_area['x2'], left_area['y2']
        ))
        right_card = self.screenshot.crop((
            right_area['x1'], right_area['y1'],
            right_area['x2'], right_area['y2']
        ))

        # Convert to CV2 format
        left_cv = pil_to_cv2(left_card)
        right_cv = pil_to_cv2(right_card)

        # Match against all card templates
        all_cards = [v.lower() + s.lower() for v in CARD_VALUES for s in CARD_SUITES]

        left_scores = []
        right_scores = []

        # Standard template size for normalization (most common size in database)
        STANDARD_TEMPLATE_SIZE = (35, 50)  # width, height

        def normalize_for_matching(img, template):
            """Resize template OR image to enable matching regardless of size differences"""
            ih, iw = img.shape[:2]
            th, tw = template.shape[:2]

            # If template is larger than image in any dimension, resize template down
            if th > ih or tw > iw:
                scale = min(ih / th, iw / tw) * 0.9  # 0.9 to ensure it fits
                new_h, new_w = int(th * scale), int(tw * scale)
                return img, cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

            return img, template

        for card_key in all_cards:
            if card_key not in self.table_dict or not self.table_dict[card_key]:
                continue

            try:
                template = binary_pil_to_cv2(self.table_dict[card_key])

                # Normalize sizes for matching
                left_img, left_template = normalize_for_matching(left_cv, template)
                right_img, right_template = normalize_for_matching(right_cv, template)

                # Match left card
                if left_template.shape[0] <= left_img.shape[0] and left_template.shape[1] <= left_img.shape[1]:
                    res_left = cv2.matchTemplate(left_img, left_template, cv2.TM_SQDIFF_NORMED)
                    min_val_left, _, _, _ = cv2.minMaxLoc(res_left)
                    left_scores.append((card_key, min_val_left))

                # Match right card
                if right_template.shape[0] <= right_img.shape[0] and right_template.shape[1] <= right_img.shape[1]:
                    res_right = cv2.matchTemplate(right_img, right_template, cv2.TM_SQDIFF_NORMED)
                    min_val_right, _, _, _ = cv2.minMaxLoc(res_right)
                    right_scores.append((card_key, min_val_right))
            except Exception as e:
                log.debug(f"Error matching {card_key}: {e}")
                continue

        # Sort by score (lowest = best match)
        left_scores.sort(key=lambda x: x[1])
        right_scores.sort(key=lambda x: x[1])

        # Log top matches for debugging
        if left_scores:
            log.debug(f"Left card top matches: {left_scores[:5]}")
        if right_scores:
            log.debug(f"Right card top matches: {right_scores[:5]}")

        # Pick best matches with validation
        left_card_result = None
        right_card_result = None

        # Adaptive threshold - try stricter first, then relax if needed
        # Card templates vary in size (23 different sizes in database: 42x22 to 49x27)
        # so we need a more permissive threshold
        CARD_THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35]

        for threshold in CARD_THRESHOLDS:
            # Best left card
            if not left_card_result and left_scores and left_scores[0][1] < threshold:
                left_card_result = left_scores[0][0].upper()
                log.info(f"Left card detected: {left_card_result} (score: {left_scores[0][1]:.4f}, threshold: {threshold})")

            # Best right card (must be different from left)
            if not right_card_result:
                for card_key, score in right_scores:
                    if score < threshold:
                        card_upper = card_key.upper()
                        if card_upper != left_card_result:
                            right_card_result = card_upper
                            log.info(f"Right card detected: {right_card_result} (score: {score:.4f}, threshold: {threshold})")
                            break

            # If we found both cards, stop trying higher thresholds
            if left_card_result and right_card_result:
                break

        # Build result
        if left_card_result:
            self.my_cards.append(left_card_result)
        if right_card_result:
            self.my_cards.append(right_card_result)

        if len(self.my_cards) == 2:
            log.info(f"My cards (positioned): {self.my_cards}")
            return True
        else:
            log.debug(f"Position-based detection found {len(self.my_cards)} cards")
            return False

    def get_table_cards2(self):
        """Get the cards on the table"""
        self.table_cards = []
        for value in CARD_VALUES:
            for suit in CARD_SUITES:
                if is_template_in_search_area(self.table_dict, self.screenshot,
                                              value.lower() + suit.lower(), 'table_cards_area'):
                    self.table_cards.append(value + suit)
        log.info(f"Table cards: {self.table_cards}")
        if len(self.table_cards) <= 2:
            if len(self.table_cards) > 0:
                log.warning(f"Only recognized {len(self.table_cards)} cards on the table. "
                            f"This can happen if cards are sliding in or if some of the templates are wrong")
            return False
        return True

    def get_dealer_position2(self):  # pylint: disable=inconsistent-return-statements
        """Determines position of dealer, where 0=myself, continous counter clockwise"""
        for i in range(self.total_players):
            if is_template_in_search_area(self.table_dict, self.screenshot,
                                          'dealer_button', 'button_search_area', str(i)):
                self.dealer_position = i
                log.info(f"Dealer found at position {i}")
                return True
        log.warning("No dealer found.")
        self.dealer_position = 0

    def fast_fold(self):
        """Find out if fast fold button is present"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'fast_fold_button', 'my_turn_search_area')

    def is_my_turn(self):
        """Check if it's my turn"""
        my_turn = is_template_in_search_area(self.table_dict, self.screenshot,
                                          'my_turn', 'my_turn_search_area')
        log.info(f"Is it my turn? {my_turn}")
        return my_turn

    def get_players_in_game(self):
        """
        Get players in the game by checking for covered cards.

        Return: list of ints
        """
        self.players_in_game = [0]  # assume myself in game
        for i in range(1, self.total_players):
            if is_template_in_search_area(self.table_dict, self.screenshot,
                                          'covered_card', 'covered_card_area', str(i)):
                self.players_in_game.append(i)
        log.info(f"Players in game: {self.players_in_game}")
        return True

    def get_my_funds2(self):
        self.get_players_funds(my_funds_only=True)

    def get_players_funds(self, my_funds_only=False, skip=[]):  # pylint: disable=dangerous-default-value
        """
        Get funds of players

        Returns: list of floats

        """
        if my_funds_only:
            counter = 1
        else:
            counter = self.total_players

        self.player_funds = []
        for i in range(counter):
            if i in skip:
                funds = 0
            else:
                funds = ocr(self.screenshot, 'player_funds_area', self.table_dict, str(i))
            self.player_funds.append(funds)
        log.info(f"Player funds: {self.player_funds}")
        return True

    def other_players_names(self):
        """Read other player names"""

    def get_pots(self):
        """Get current and total pot - with dynamic OCR fallback."""
        # Try template-based OCR first
        self.current_round_pot = ocr(self.screenshot, 'current_round_pot', self.table_dict, fast=True)
        self.total_pot = ocr(self.screenshot, 'total_pot_area', self.table_dict)

        # Fallback to dynamic OCR if template-based failed
        if (not self.total_pot or self.total_pot == 0) and DYNAMIC_READER_AVAILABLE:
            try:
                reader = DynamicTableReader(self.screenshot)
                dynamic_pot = reader.get_pot()
                if dynamic_pot and dynamic_pot > 0:
                    self.total_pot = dynamic_pot
                    log.info(f"Using dynamic pot: {self.total_pot}")
            except Exception as e:
                log.debug(f"Dynamic pot reading failed: {e}")

        log.info(f"Current round pot {self.current_round_pot}")
        log.info(f"Total pot {self.total_pot}")

    def get_player_pots(self, skip=[]):  # pylint: disable=dangerous-default-value
        """Get pots of the players"""
        self.player_pots = []
        for i in range(self.total_players):
            if i in skip:
                funds = 0
            else:
                funds = ocr(self.screenshot, 'player_pot_area', self.table_dict, str(i))
            self.player_pots.append(funds)
        log.info(f"Player pots: {self.player_pots}")

        return True

    def has_call_button(self):
        """Check if call button is visible using template matching + color fallback"""
        self.call_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                      'call_button', 'buttons_search_area')
        # Fallback to color detection if template matching fails
        if not self.call_button:
            self.call_button = self._detect_button_by_color('call')
        log.info(f"Call button found: {self.call_button}")
        return self.call_button

    def has_raise_button(self):
        """Check if raise button is present using template matching + color fallback"""
        self.raise_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                       'raise_button', 'buttons_search_area')
        if not self.raise_button:
            self.raise_button = self._detect_button_by_color('raise')
        log.info(f"Raise button found: {self.raise_button}")
        return self.raise_button

    def has_bet_button(self):
        """Check if bet button is present using template matching + color fallback"""
        self.bet_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                     'bet_button', 'buttons_search_area')
        if not self.bet_button:
            self.bet_button = self._detect_button_by_color('raise')  # Bet is same color as raise
        log.info(f"Bet button found: {self.bet_button}")
        return self.bet_button

    def has_check_button(self):
        """Check if check button is present using template matching + color fallback"""
        self.check_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                       'check_button', 'buttons_search_area')
        if not self.check_button:
            self.check_button = self._detect_button_by_color('call')  # Check is same color as call
        log.info(f"Check button found: {self.check_button}")
        return self.check_button

    def _detect_button_by_color(self, button_type: str) -> bool:
        """
        Fallback button detection using HSV color matching.
        Uses LEARNED thresholds from adaptive_learner if available.

        GGPoker button colors:
        - Fold: Gray (low saturation, medium value)
        - Call/Check: Green
        - Raise/Bet: Orange/gold
        """
        if self.screenshot is None:
            return False

        try:
            import cv2
            import numpy as np

            # Try to get learned thresholds
            try:
                from gamble.tools.adaptive_learner import get_threshold
                USE_LEARNED = True
            except ImportError:
                USE_LEARNED = False

            img = cv2.cvtColor(np.array(self.screenshot), cv2.COLOR_RGB2BGR)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            h_img, w_img = img.shape[:2]

            # Search bottom 40% of table
            y_start = int(h_img * 0.60)
            search_region = hsv[y_start:, :]

            # Color ranges - USE LEARNED THRESHOLDS if available
            if button_type == 'fold':
                if USE_LEARNED:
                    lower = np.array(get_threshold('hsv_gray_lower', [0, 0, 30]))
                    upper = np.array(get_threshold('hsv_gray_upper', [180, 60, 120]))
                else:
                    lower = np.array([0, 0, 30])
                    upper = np.array([180, 60, 120])
            elif button_type in ['call', 'check']:
                if USE_LEARNED:
                    lower = np.array(get_threshold('hsv_green_lower', [35, 50, 50]))
                    upper = np.array(get_threshold('hsv_green_upper', [85, 255, 255]))
                else:
                    lower = np.array([35, 50, 50])
                    upper = np.array([85, 255, 255])
            elif button_type in ['raise', 'bet']:
                if USE_LEARNED:
                    lower = np.array(get_threshold('hsv_orange_lower', [8, 80, 80]))
                    upper = np.array(get_threshold('hsv_orange_upper', [28, 255, 255]))
                else:
                    lower = np.array([8, 80, 80])
                    upper = np.array([28, 255, 255])
            else:
                return False

            # Get learned button_area_min
            min_area = get_threshold('button_area_min', 1500) if USE_LEARNED else 1500

            mask = cv2.inRange(search_region, lower, upper)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Look for button-shaped contours
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area:
                    continue
                x, y, w, bh = cv2.boundingRect(cnt)
                if w < 50 or bh < 20 or w > 400:
                    continue
                aspect = w / bh if bh > 0 else 0
                if 1.2 <= aspect <= 5.0:
                    log.debug(f"Color detection found {button_type} button (area={area}, learned={USE_LEARNED})")
                    return True

            return False

        except Exception as e:
            log.debug(f"Color button detection error: {e}")
            return False

    def has_all_in_call_button(self):
        """Check if all in call button is present"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'all_in_call_button', 'buttons_search_area')

    def get_call_value(self):
        """Read the call value from the call button - with dynamic OCR fallback."""
        self.call_value = ocr(self.screenshot, 'call_value', self.table_dict)

        # Fallback to dynamic OCR if template-based failed
        if (not self.call_value or self.call_value == 0) and DYNAMIC_READER_AVAILABLE:
            try:
                reader = DynamicTableReader(self.screenshot)
                dynamic_call = reader.get_call_amount()
                if dynamic_call and dynamic_call > 0:
                    self.call_value = dynamic_call
                    log.info(f"Using dynamic call value: {self.call_value}")
            except Exception as e:
                log.debug(f"Dynamic call value failed: {e}")

        log.info(f"Call value: {self.call_value}")
        if self.call_value and round(self.call_value) >= 90:
            log.warning("Correcting call value from >90")
            self.call_value -= 90
        return self.call_value

    def get_raise_value(self):
        """Read the value of the raise button - with dynamic OCR fallback."""
        self.raise_value = ocr(self.screenshot, 'raise_value', self.table_dict)

        # Fallback to dynamic OCR if template-based failed
        if (not self.raise_value or self.raise_value == 0) and DYNAMIC_READER_AVAILABLE:
            try:
                reader = DynamicTableReader(self.screenshot)
                dynamic_raise = reader.get_raise_amount()
                if dynamic_raise and dynamic_raise > 0:
                    self.raise_value = dynamic_raise
                    log.info(f"Using dynamic raise value: {self.raise_value}")
            except Exception as e:
                log.debug(f"Dynamic raise value failed: {e}")

        log.info(f"Raise value: {self.raise_value}")
        if self.raise_value and round(self.raise_value) >= 90:
            log.warning("Correcting raise value from >90")
            self.raise_value -= 90
        return self.raise_value

    def get_game_number_on_screen2(self):
        """Game number"""
        self.game_number = ocr(self.screenshot, 'game_number', self.table_dict)
        log.debug(f"Game number: {self.game_number}")
        return self.game_number
