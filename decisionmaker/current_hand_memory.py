import numpy as np
from copy import copy, deepcopy
from tools.debug_logger import debug_logger


class History:
    def __init__(self):
        # keeps values of the last round
        self.previousPot = 0
        self.previousCards = []
        self.myLastBet = 0
        self.histGameStage = ""
        self.myFundsHistory = [2.0]
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


class CurrentHandPreflopState:
    def __init__(self):
        self.other_player = None
        self.logger = debug_logger().start_logger('preflop_memory')
        self.bot_preflop_decision = ''
        self.preflop_caller_positions = []
        self.preflop_raiser_positions = []

    def reset(self):
        self.__init__()

    def update_values(self, t, decision_str, h):
        self.other_players = deepcopy(t.other_players)

        self.bot_preflop_position_utg = t.position_utg_plus
        self.bot_preflop_decision = decision_str

        self.rounds = h.round_number
        if not np.isnan(t.first_raiser):
            self.preflop_raiser_positions.append(t.first_raiser)
        if not np.isnan(t.second_raiser):
            self.preflop_raiser_positions.append(t.second_raiser)
        if not np.isnan(t.first_caller):
            self.preflop_caller_positions.append(t.first_caller)
        self.first_caller_utg = t.first_caller_utg

        self.logger.debug("Preflop state has been updated")

    def get_reverse_sheetname(self, abs_pos, t):
        # if the player is situated after the bot, consider the bot's decision in the reverse table
        utg_position = t.get_utg_from_abs_pos(abs_pos, t.dealer_position)
        if utg_position > self.bot_preflop_position_utg:
            if self.bot_preflop_decision == 'Call' or self.bot_preflop_decision == 'Call2':
                self.preflop_caller_positions.append(t.position_utg_plus + 1)
            if self.bot_preflop_decision == 'Bet' \
                    or self.bot_preflop_decision == 'BetPlus' \
                    or self.bot_preflop_decision == 'Bet half pot' \
                    or self.bot_preflop_decision == 'Bet pot' \
                    or self.bot_preflop_decision == 'Bet Bluff':
                self.preflop_raiser_positions.append(t.position_utg_plus + 1)

        sheet_name = str(utg_position + 1)

        sheet_name += ''.join(['R' + str(x) for x in sorted(self.preflop_raiser_positions)])
        sheet_name += ''.join(['C' + str(x) for x in sorted(self.preflop_caller_positions)])

        self.logger.info('Reverse sheetname: ' + sheet_name)
        return sheet_name

    def get_rangecards_from_sheetname(self,opponent_decision,tablename):
        return None
