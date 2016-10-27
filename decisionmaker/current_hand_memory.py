import numpy as np
from copy import copy, deepcopy

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

    def calculate_reverse_table(self, abs_pos, dealer_pos, t, p, h):
        utg_position=t.get_utg_from_abs_pos(abs_pos, dealer_pos)
        if h.round_number==0: reference_pot=t.bigBlind

        i=abs_pos-3
        first_raiser, \
        second_raiser, \
        first_caller, \
        first_raiser_utg, \
        second_raiser_utg, \
        first_caller_utg = \
            t.get_raisers_and_callers(p, reference_pot, relative_to_bot=i)

        sheet_name = str(utg_position + 1)

        return sheet_name
