import logging
from copy import copy, deepcopy

import numpy as np

# from poker.card_recognition.card_neural_network import CardNeuralNetwork


class History:
    def __init__(self):
        # keeps values of the last round
        self.previousPot = 0
        self.previousCards = []
        self.myLastBet = 0
        self.histGameStage = ""
        self.myFundsHistory = []
        self.losses = 0
        self.wins = 0
        self.totalGames = 0
        self.GameID = int(np.round(np.random.uniform(0, 999999999), 0))  # first game ID
        self.lastRoundGameID = 0
        self.lastSecondRoundAdjustment = 0
        self.lastGameID = "0"
        self.histDecision = 0
        self.histEquity = 0
        self.histMinCall = 0
        self.histMinBet = 0
        self.histPlayerPots = 0
        self.first_raiser = np.nan
        self.previous_decision = 0
        self.last_round_bluff = False
        self.uploader = {}

        # initialize the card regognition neural network
        # self.n = CardNeuralNetwork()
        # self.n.load_model()


class CurrentHandPreflopState:
    def __init__(self):
        self.other_player = None
        self.logger = logging.getLogger('handmemory')
        self.logger.setLevel(logging.DEBUG)
        self.bot_preflop_decision = ''
        self.preflop_caller_positions = []  # abs
        self.preflop_raiser_positions = []  # abs
        self.range_column_name = ''
        self.preflop_sheet_name = None
        self.preflop_bot_ranges = None

    def reset(self):
        self.__init__()

    def update_values(self, t, decision_str, h, d):
        self.reset()
        self.other_players = deepcopy(t.other_players)

        self.bot_preflop_position_utg = t.position_utg_plus
        self.bot_preflop_decision = decision_str
        self.preflop_sheet_name = t.preflop_sheet_name
        self.preflop_bot_ranges = d.preflop_bot_ranges

        self.rounds = h.round_number
        if not np.isnan(t.first_raiser_utg):
            self.preflop_raiser_positions.append(t.first_raiser)
        if not np.isnan(t.second_raiser_utg):
            self.preflop_raiser_positions.append(t.second_raiser)
        if not np.isnan(t.first_caller_utg):
            self.preflop_caller_positions.append(t.first_caller)
        self.first_caller_utg = t.first_caller_utg

        self.logger.debug("Preflop state has been updated")

    def get_reverse_sheetname(self, abs_pos, t, h):
        bot_abs_pos = t.get_abs_from_utg_pos(t.position_utg_plus, t.dealer_position)
        second_round = False
        # if the player is situated after the bot, consider the bot's decision in the reverse table
        utg_position = t.get_utg_from_abs_pos(abs_pos, t.dealer_position)
        preflop_raiser_positions = copy(self.preflop_raiser_positions)  # absolute
        preflop_caller_positions = copy(self.preflop_caller_positions)  # absolute

        if self.bot_preflop_decision == 'Bet' \
                or self.bot_preflop_decision == 'BetPlus' \
                or self.bot_preflop_decision == 'Bet half pot' \
                or self.bot_preflop_decision == 'Bet pot' \
                or self.bot_preflop_decision == 'Bet Bluff':
            preflop_raiser_positions.append(bot_abs_pos)

            if utg_position < self.bot_preflop_position_utg:
                second_round = True

        if utg_position > self.bot_preflop_position_utg or self.rounds > 0:
            if self.bot_preflop_decision == 'Call' or self.bot_preflop_decision == 'Call2':
                preflop_caller_positions.append(bot_abs_pos)

        sheet_name = str(utg_position + 1)

        if abs_pos in preflop_raiser_positions: preflop_raiser_positions.remove(abs_pos)
        if abs_pos in preflop_caller_positions: preflop_caller_positions.remove(abs_pos)

        self.all_preflop_raiser_positions_abs = copy(preflop_raiser_positions)

        try:
            second_round = True if utg_position < t.get_utg_from_abs_pos(preflop_raiser_positions[0],
                                                                         t.dealer_position) else second_round
        except:
            pass

        try:
            second_round = True if utg_position < t.get_utg_from_abs_pos(preflop_raiser_positions[1],
                                                                         t.dealer_position) else second_round
        except:
            pass

        if second_round:
            # second round reverse table'
            self.logger.info('Using second round reverse table')
            sheet_name += '2'

        sheet_name += ''.join(
            ['R' + str(t.get_utg_from_abs_pos(x, t.dealer_position) + 1) for x in sorted(preflop_raiser_positions)])
        sheet_name += ''.join(
            ['C' + str(t.get_utg_from_abs_pos(x, t.dealer_position) + 1) for x in sorted(preflop_caller_positions)])

        self.logger.info('Reverse sheetname: ' + sheet_name)

        t.reverse_sheet_name = sheet_name
        t.reverse_econd_round = second_round
        return sheet_name

    def get_rangecards_from_sheetname(self, abs_pos, sheet_name, t, h, p):
        utg_position = t.get_utg_from_abs_pos(abs_pos, t.dealer_position)

        if sheet_name == '6': sheet_name = '5'

        if sheet_name not in h.preflop_sheet:
            self.logger.warning('Reverse sheetname not found: ' + sheet_name)
            sheet_name = sheet_name[:-2]
            self.logger.warning('Trying to cut last element of reverse sheet: ' + sheet_name)

            if sheet_name not in h.preflop_sheet:
                self.logger.warning('Cut reverse sheetname not found either: ' + sheet_name)
                sheet_name = sheet_name[0]
                self.logger.warning('Using backup reverse sheet: ' + sheet_name)

        ranges_call = h.preflop_sheet[sheet_name][h.preflop_sheet[sheet_name]['Call'] > 0.1]['Hand'].tolist()
        ranges_raise = h.preflop_sheet[sheet_name][h.preflop_sheet[sheet_name]['Raise'] > 0.1]['Hand'].tolist()

        if p.selected_strategy['differentiate_reverse_sheet']:

            if abs_pos in self.all_preflop_raiser_positions_abs:
                ranges = ranges_raise
                self.logger.info("Use raiser reverse column")
                self.range_column_name = 'Raise'
            else:
                ranges = ranges_call
                self.logger.info(
                    "Use caller reverse column because abs_pos " + str(abs_pos) + " is not in raisers: " + str(
                        self.preflop_raiser_positions))
                self.range_column_name = 'Call'

        else:
            ranges = ranges_call + ranges_raise
            self.logger.info("Use caller and raiser reverse column")
            self.range_column_name = 'All'

        if len(ranges) == 0:
            ranges = ranges_call + ranges_raise
            self.logger.info("Use caller and raiser reverse column because the opponent made incorrect decision")
            self.range_column_name = 'All bc mistake'

        ranges = [str(x).upper() for x in ranges]

        return set(ranges)
