"""Recognize table"""
import logging

from poker.scraper.table_scraper_nn import predict
from poker.scraper.table_setup_actions_and_signals import CARD_SUITES, CARD_VALUES
from poker.tools.helper import get_dir
from poker.tools.screen_operations import take_screenshot, crop_screenshot_with_topleft_corner, \
    is_template_in_search_area, binary_pil_to_cv2, ocr

log = logging.getLogger(__name__)


class TableScraper:
    def __init__(self, table_dict):
        self.table_dict = table_dict
        self.screenshot = None

        self.total_players = 6 if not 'total_players' in self.table_dict else self.table_dict['total_players']
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
        """Crop top left corner based on the current selected table dict and replace self.screnshot with it"""
        self.screenshot, self.tlc = crop_screenshot_with_topleft_corner(self.screenshot,
                                                                        binary_pil_to_cv2(
                                                                            self.table_dict['topleft_corner']))
        return self.screenshot

    def lost_everything(self):
        """Check if lost everything has occurred"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'lost_everything', 'lost_everything_search_area')

    def im_back(self):
        """Check if I'm back button is visible"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'im_back', 'buttons_search_area')

    def resume_hand(self):
        """Check if I'm back button is visible"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'resume_hand', 'buttons_search_area')

    def get_my_cards2(self):
        """Get my cards"""
        self.my_cards = []

        if 'use_neural_network' in self.table_dict and self.table_dict['use_neural_network'] == '2':
            self.get_my_cards_nn()
        else:
            for value in CARD_VALUES:
                for suit in CARD_SUITES:
                    if is_template_in_search_area(self.table_dict, self.screenshot,
                                                  value.lower() + suit.lower(), 'my_cards_area', extended=True):
                        self.my_cards.append(value + suit)

        if len(self.my_cards) != 2:
            log.warning("My cards not recognized")
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

    def get_table_cards2(self):
        """Get the cards on the table"""
        self.table_cards = []
        for value in CARD_VALUES:
            for suit in CARD_SUITES:
                if is_template_in_search_area(self.table_dict, self.screenshot,
                                              value.lower() + suit.lower(), 'table_cards_area'):
                    self.table_cards.append(value + suit)
        log.info(f"Table cards: {self.table_cards}")
        if len(self.table_cards) == 1 or len(self.table_cards) == 2:
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
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'my_turn', 'my_turn_search_area')

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
        """Get current and total pot"""
        self.current_round_pot = ocr(self.screenshot, 'current_round_pot', self.table_dict, fast=True)
        log.info(f"Current round pot {self.current_round_pot}")
        self.total_pot = ocr(self.screenshot, 'total_pot_area', self.table_dict)
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
        """Chek if call button is visible"""
        self.call_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                      'call_button', 'buttons_search_area')
        log.info(f"Call button found: {self.call_button}")
        return self.call_button

    def has_raise_button(self):
        """Check if raise button is present"""
        self.raise_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                       'raise_button', 'buttons_search_area')
        log.info(f"Raise button found: {self.raise_button}")
        return self.raise_button

    def has_bet_button(self):
        """Check if bet button is present"""
        self.bet_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                     'bet_button', 'buttons_search_area')
        log.info(f"Bet button found: {self.bet_button}")
        return self.bet_button

    def has_check_button(self):
        """Check if check button is present"""
        self.check_button = is_template_in_search_area(self.table_dict, self.screenshot,
                                                       'check_button', 'buttons_search_area')
        log.info(f"Check button found: {self.check_button}")
        return self.check_button

    def has_all_in_call_button(self):
        """Check if all in call button is present"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'all_in_call_button', 'buttons_search_area')

    def get_call_value(self):
        """Read the call value from the call button"""
        self.call_value = ocr(self.screenshot, 'call_value', self.table_dict)
        log.info(f"Call value: {self.call_value}")
        if round(self.call_value) >= 90:
            log.warning("Correcting call value from >90")
            self.call_value -= 90
        return self.call_value

    def get_raise_value(self):
        """Read the value of the raise button"""
        self.raise_value = ocr(self.screenshot, 'raise_value', self.table_dict)
        log.info(f"Raise value: {self.raise_value}")
        if round(self.raise_value) >= 90:
            log.warning("Correcting raise value from >90")
            self.raise_value -= 90
        return self.raise_value

    def get_game_number_on_screen2(self):
        """Game number"""
        self.game_number = ocr(self.screenshot, 'game_number', self.table_dict)
        log.debug(f"Game number: {self.game_number}")
        return self.game_number
