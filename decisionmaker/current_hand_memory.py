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

    def update_values(self,t,decision_str,h):
        self.other_players=deepcopy(t.other_players)
        self.bot_decision=decision_str
        self.bot_position=t.position_utg_plus
        self.rounds=h.round_number
        self.bot_pot=t.bot_pot
        if not np.isnan(t.first_raiser):
            self.other_players[t.first_raiser]['decision'] = 'bet'
        if not np.isnan(t.second_raiser):
            self.other_players[t.second_raiser]['decision'] = 'bet'
        if not np.isnan(t.first_caller):
            self.other_players[t.first_caller]['decision'] = 'call'
        self.first_caller_utg=t.first_caller_utg

        self.first_raiser=t.first_raiser
        self.second_raiser=t.second_raiser
        self.first_caller=t.first_caller
        self.first_raiser_utg=t.first_raiser_utg
        self.second_raiser_utg=t.second_raiser_utg
        self.first_caller_utg=t.first_caller_utg

    def get_reverse_sheetname(self, abs_pos, t, p, h):

        first_raiser_str=''
        second_raiser_str=''
        first_caller_str=''

        utg_position=t.get_utg_from_abs_pos(abs_pos, t.dealer_position)

        if not np.isnan(self.first_raiser_utg) and self.first_raiser_utg<utg_position:
            first_raiser_str='R'+str(self.first_raiser_utg+1)
        if not np.isnan(self.second_raiser_utg) and self.second_raiser_utg<utg_position:
            second_raiser_str='R'+str(self.second_raiser_utg+1)
        if not np.isnan(self.first_caller_utg) and self.first_caller_utg<utg_position:
            first_caller_str='C'+str(self.first_caller_utg+1)

        if h.round_number==0: reference_pot=t.bigBlind
        sheet_name = str(utg_position + 1) + str(first_raiser_str) + str(second_raiser_str) + str(first_caller_str)
        self.logger.info('Reverse Sheetname: '+sheet_name)

        return sheet_name
