""""
Strategy Definition
t contains variables that have been scraped from the table
h contains values from the historical (last) decision
p contains values from the Strategy as defined in the xml file
"""

import logging
from enum import Enum

from .base import DecisionBase, Collusion
from .curvefitting import *
from .montecarlo_python import *
from .outs_calculator import Outs_Calculator


class DecisionTypes(Enum):
    i_am_back, fold, check, call, bet1, bet2, bet3, bet4, bet_bluff, call_deception, check_deception = ['Imback',
                                                                                                        'Fold', 'Check',
                                                                                                        'Call', 'Bet',
                                                                                                        'BetPlus',
                                                                                                        'Bet half pot',
                                                                                                        'Bet pot',
                                                                                                        'Bet Bluff',
                                                                                                        'Call Deception',
                                                                                                        'Check Deception']


class GameStages(Enum):
    PreFlop, Flop, Turn, River = ['PreFlop', 'Flop', 'Turn', 'River']


class Decision(DecisionBase):
    def __init__(self, t, h, p, l):
        self.logger = logging.getLogger('decision')
        self.logger.setLevel(logging.DEBUG)
        t.bigBlind = float(p.selected_strategy['bigBlind'])
        t.smallBlind = float(p.selected_strategy['smallBlind'])

        t.bigBlindMultiplier = t.bigBlind / 0.02


        pots = [player['pot'] for player in t.other_players if type(player['pot']) != str]
        try:
            self.max_player_pot = max(pots)
            self.logger.debug("Highest player pot: %s",self.max_player_pot)
        except:
            self.max_player_pot = 0
        self.logger.debug("Round pot: "+str(t.round_pot_value))
        if t.round_pot_value==0:
            t.round_pot_value=t.bigBlind*4
            self.logger.debug("Assuming round pot is 4*bigBlind")
        self.pot_multiple = self.max_player_pot / t.round_pot_value
        if self.pot_multiple == '':
            self.pot_multiple = 0

        if p.selected_strategy['use_pot_multiples']:
            self.logger.info("Using pot multiple: Replacing mincall and minbet: " + str(self.pot_multiple))
            t.minCall = self.pot_multiple
            t.minBet = self.pot_multiple
        else:
            try:
                t.minCall = float(t.currentCallValue)
            except:
                t.minCall = float(0.0)
                if t.checkButton == False:
                    self.logger.warning(
                        "Failed to convert current Call value, saving error.png, deriving from bet value, result:")
                    self.DeriveCallButtonFromBetButton = True
                    t.minCall = np.round(float(t.get_current_bet_value(p)) / 2, 2)
                    self.logger.info("mincall: " + str(t.minCall))
                    # adjMinCall=minCall*c1*c2

            try:
                t.minBet = float(t.currentBetValue)
                t.opponentBetIncreases = t.minBet - h.myLastBet
            except:
                self.logger.warning("Betvalue not recognised!")
                t.minBet = float(100.0)
                t.opponentBetIncreases = 0

        if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
            self.logger.info("Replacing equity with relative equity")
            t.equity = t.relative_equity
        else:
            t.equity = t.abs_equity
            self.logger.info("Use absolute equity")

        out_multiplier = p.selected_strategy['out_multiplier']
        oc = Outs_Calculator()
        if 3 <= len(t.cardsOnTable) <= 4:  #
            try:
                outs = oc.evaluate_hands(t.mycards, t.cardsOnTable, oc)
            except:
                outs = 0
                self.logger.critical("Error in outs calculation!")
        else:
            outs = 0
        self.out_adjustment = outs * out_multiplier * .01

        self.outs = outs

        if outs > 0:
            self.logger.info("Minimum equity is reduced because of outs by percent: %s", int(self.out_adjustment * 100))

        self.preflop_adjustment = -float(
            p.selected_strategy['pre_flop_equity_reduction_by_position']) * t.position_utg_plus

        if not np.isnan(t.first_raiser_utg):
            self.preflop_adjustment += float(p.selected_strategy['pre_flop_equity_increase_if_bet']) + (
                (5 - t.first_raiser_utg) * 0.01)

        if not np.isnan(t.first_caller_utg):
            self.preflop_adjustment += float(p.selected_strategy['pre_flop_equity_increase_if_call']) + (
                (5 - t.first_caller_utg) * 0.01)

        # in case the other players called my bet become less aggressive and make an adjustment for the second round
        if (h.histGameStage == t.gameStage and h.lastRoundGameID == h.GameID) or h.lastSecondRoundAdjustment > 0:
            if t.gameStage == 'PreFlop':
                self.secondRoundAdjustment = float(p.selected_strategy['secondRoundAdjustmentPreFlop'])
            else:
                self.secondRoundAdjustment = float(p.selected_strategy['secondRoundAdjustment'])

            secondRoundAdjustmentPowerIncrease = int(p.selected_strategy['secondRoundAdjustmentPowerIncrease'])
        else:
            self.secondRoundAdjustment = 0
            secondRoundAdjustmentPowerIncrease = 0

        P = float(t.totalPotValue)
        self.maxCallEV = self.calc_EV_call_limit(t.equity, P)
        # self.maxBetEV = self.calc_bet_limit(t.equity, P, float(p.selected_strategy['c']), t, logger)
        self.logger.debug("Max call EV: " + str(self.maxCallEV))

        self.DeriveCallButtonFromBetButton = False

        self.potAdjustmentPreFlop = t.totalPotValue / t.bigBlind / 250 * float(
            p.selected_strategy['potAdjustmentPreFlop'])
        self.potAdjustmentPreFlop = min(self.potAdjustmentPreFlop,
                                        float(p.selected_strategy['maxPotAdjustmentPreFlop']))

        self.potAdjustment = t.totalPotValue / t.bigBlind / 250 * float(p.selected_strategy['potAdjustment'])
        self.potAdjustment = min(self.potAdjustment, float(p.selected_strategy['maxPotAdjustment']))

        if t.gameStage == GameStages.PreFlop.value:
            t.power1 = int(p.selected_strategy['PreFlopCallPower'])
            t.minEquityCall = float(
                p.selected_strategy[
                    'PreFlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustmentPreFlop + self.preflop_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Flop.value:
            t.power1 = int(p.selected_strategy['FlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy[
                    'FlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment - self.out_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Turn.value:
            t.power1 = int(p.selected_strategy['TurnCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy[
                    'TurnMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment - self.out_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.River.value:
            t.power1 = int(p.selected_strategy['RiverCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['RiverMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1

        t.maxValue_call = float(p.selected_strategy['initialFunds']) * t.potStretch
        minimum_curve_value = 0 if p.selected_strategy['use_pot_multiples'] else t.smallBlind
        minimum_curve_value2 = 0 if p.selected_strategy['use_pot_multiples'] else t.minCallAmountIfAboveLimit
        d = Curvefitting(np.array([t.equity]), minimum_curve_value, minimum_curve_value2, t.maxValue_call, t.minEquityCall,
                         t.maxEquityCall, t.max_X, t.power1)
        self.maxCallE = round(d.y[0], 2)

        if not t.other_player_has_initiative and not t.checkButton:
            opponent_raised_without_initiative = 1
            self.logger.info(
                "Other player has no initiative and there is no check button. Activate increased required equity for betting")
        else:
            opponent_raised_without_initiative = 0
            self.logger.debug("Increase required equity for betting not acviated")

        opponent_raised_without_initiative_flop = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_flop'] * opponent_raised_without_initiative
        opponent_raised_without_initiative_turn = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_turn'] * opponent_raised_without_initiative
        opponent_raised_without_initiative_river = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_river'] * opponent_raised_without_initiative

        if t.gameStage == GameStages.PreFlop.value:
            t.power2 = int(p.selected_strategy['PreFlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'PreFlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment + self.preflop_adjustment
            t.maxEquityBet = float(p.selected_strategy['PreFlopMaxBetEquity'])
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Flop.value:
            t.power2 = int(p.selected_strategy['FlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'FlopMinBetEquity']) + self.secondRoundAdjustment - self.out_adjustment + opponent_raised_without_initiative_flop
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Turn.value:
            t.power2 = int(p.selected_strategy['TurnBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'TurnMinBetEquity']) + self.secondRoundAdjustment - self.out_adjustment + opponent_raised_without_initiative_turn
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.River.value:
            t.power2 = int(p.selected_strategy['RiverBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'RiverMinBetEquity']) + self.secondRoundAdjustment + opponent_raised_without_initiative_river
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2

        # adjustment for player profile
        if t.isHeadsUp and t.gameStage != GameStages.PreFlop.value:
            try:
                self.flop_probability_player = l.get_flop_frequency_of_player(t.PlayerNames[0])
                self.logger.info(
                    "Probability profile of : " + t.PlayerNames[0] + ": " + str(self.flop_probability_player))
            except:
                self.flop_probability_player = np.nan

            if self.flop_probability_player < 0.30:
                self.logger.info("Defensive play due to probability profile")
                t.power1 += 2
                t.power2 += 2
                self.player_profile_adjustment = 2
            elif self.flop_probability_player > 0.60:
                self.logger.info("Agressive play due to probability profile")
                t.power1 -= 2
                t.power2 -= 2
                self.player_profile_adjustment = -2
            else:
                self.player_profile_adjustment = 0
        t.maxValue_bet = float(p.selected_strategy['initialFunds2']) * t.potStretch
        d = Curvefitting(np.array([t.equity]), minimum_curve_value, t.minBetAmountIfAboveLimit, t.maxValue_bet, t.minEquityBet,
                         t.maxEquityBet, t.max_X, t.power2)
        self.maxBetE = round(d.y[0], 2)

        self.finalCallLimit = self.maxCallE  # min(self.maxCallE, self.maxCallEV)
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

    def preflop_table_analyser(self, t, logger, h, p):
        if t.gameStage == GameStages.PreFlop.value:
            m = MonteCarlo()
            crd1, crd2 = m.get_two_short_notation(t.mycards)
            crd1 = crd1.upper()
            crd2 = crd2.upper()

            sheet_name = t.derive_preflop_sheet_name(t, h, t.first_raiser_utg, t.first_caller_utg, t.second_raiser_utg)

            self.logger.info("Sheet name: " + sheet_name)
            excel_file = h.preflop_sheet
            info_sheet = excel_file['Info']
            sheet_version = info_sheet['Version'].iloc[0]
            self.logger.info("Preflop Excelsheet Version: " + str(sheet_version))
            if sheet_name in excel_file:
                sheet = excel_file[sheet_name]
                self.logger.debug("Sheetname found")
            elif sheet_name[:-2] in excel_file:
                self.logger.warning("Sheetname " + sheet_name + " not found, cutting last element: " + sheet_name[:-2])
                sheet = excel_file[sheet_name[:-2]]
            else:
                backup_sheet_name = '2R1'
                sheet = excel_file[backup_sheet_name]
                self.logger.warning("Sheetname not found: " + sheet_name)
                self.logger.warning("Backup sheet in use: " + backup_sheet_name)
                t.entireScreenPIL.save('sheet_not_found.png')
            sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())

            handlist = set(sheet['Hand'].tolist())
            self.preflop_bot_ranges = handlist

            found_card = ''

            if crd1 in handlist:
                found_card = crd1
            elif crd2 in handlist:
                found_card = crd2

            self.logger.debug("Looking in preflop table for: " + crd1 + ", " + crd2 + ", " + crd1[0:2])
            self.logger.debug("Found in preflop table: " + found_card)

            if found_card != '':
                call_probability = sheet[sheet['Hand'] == found_card]['Call'].iloc[0]
                bet_probability = sheet[sheet['Hand'] == found_card]['Raise'].iloc[0]
                rnd = np.random.uniform(0, 100, 1)[0] / 100
                self.logger.debug("Random number: " + str(rnd))
                self.logger.debug("Call probability: " + str(call_probability))
                self.logger.debug("Raise probability: " + str(bet_probability))

                if rnd < call_probability:
                    self.decision = DecisionTypes.call
                    self.logger.info('Preflop calling activated from preflop table')

                elif rnd >= call_probability and rnd <= bet_probability + call_probability:
                    if sheet_name in ['1', '2', '3', '4']:
                        self.decision = DecisionTypes.bet3
                        self.logger.info('Preflop betting 3 activated from preflop table')
                    else:
                        self.decision = DecisionTypes.bet4
                        self.logger.info('Preflop betting 4 activated from preflop table')
                        # 1, 2, 3, 4 = half pot
                        # 5 = pot and the
                        # rest POT
                else:
                    self.decision = DecisionTypes.fold
                    self.logger.info('Preflop folding from preflop table')
            else:
                self.decision = DecisionTypes.fold
                self.logger.info('Preflop folding, hands not found in preflop table')

            t.currentBluff = 0

    def calling(self, t, p, h):
        if self.finalCallLimit < t.minCall:
            self.decision = DecisionTypes.fold
            self.logger.debug("Call limit exceeded: suggest folding")
        if self.finalCallLimit >= t.minCall:
            self.decision = DecisionTypes.call
            self.logger.debug("Call limit ok: calling would be fine")

    def betting(self, t, p, h):
        # preflop
        if t.gameStage == GameStages.PreFlop.value:
            if self.finalBetLimit > float(t.minBet):
                self.logger.info("Bet3 condition met")
                self.decision = DecisionTypes.bet3

            # if (self.finalBetLimit > float(t.minBet)) and \
            #         (t.first_raiser_utg >= 0 or t.first_caller_utg >= 0):
            #     self.logger.info("Bet4 condition met")
            #     self.decision = DecisionTypes.bet4

        stage = t.gameStage.lower()
        # flop turn river
        if t.gameStage != GameStages.PreFlop.value:

            # multiple decision
            if p.selected_strategy['use_pot_multiples']:
                if self.finalBetLimit > t.minBet and \
                        (not t.checkButton or not t.other_player_has_initiative or
                        p.selected_strategy[stage + '_betting_condidion_1'] == 0):
                    self.decision = DecisionTypes.bet3
                    self.logger.info("Bet3 activated (based on pot multiple decision)")


            # absolute value decision
            else:
                if not (h.round_number > 0 and h.previous_decision == DecisionTypes.check_deception.value):
                    # bet1
                    if self.finalBetLimit >= t.minBet and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                    stage + '_betting_condidion_1'] == 0):
                        self.decision = DecisionTypes.bet1
                        self.logger.info("Bet1 condition met")
                    # bet2
                    if self.finalBetLimit >= (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) and ((
                             t.gameStage == GameStages.Turn.value and t.totalPotValue > t.bigBlind * 3) or
                             t.gameStage == GameStages.River.value) and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                    stage + '_betting_condidion_1'] == 0):
                        self.decision = DecisionTypes.bet2
                        self.logger.info("Bet2 condition met")
                    # bet3
                    self.logger.debug(
                        "Checking for betting half pot: " + str(
                            float(t.totalPotValue) / 2) + " needs be be below or equal " + str(
                            self.finalBetLimit))
                    if (self.finalBetLimit >= float(t.totalPotValue) / 2) \
                            and (t.minBet < float(t.totalPotValue) / 2) and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                    stage + '_betting_condidion_1'] == 0):
                        self.logger.info("Bet3 condition met")
                        self.decision = DecisionTypes.bet3
                    # bet4
                    if t.allInCallButton == False and t.equity >= float(p.selected_strategy['betPotRiverEquity']) and \
                                    t.gameStage == GameStages.River.value and \
                                    float(t.totalPotValue) < t.bigBlind * float(
                                p.selected_strategy['betPotRiverEquityMaxBBM']) and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                    stage + '_betting_condidion_1'] == 0):
                        self.logger.info("Bet4 condition met")
                        self.decision = DecisionTypes.bet4

    def bluff(self, t, p, h):
        t.currentBluff = 0

        if t.isHeadsUp == True and h.round_number == 0:

            # flop
            if t.gameStage == GameStages.Flop.value and \
                                    float(p.selected_strategy['FlopBluffMaxEquity']) > t.equity > float(
                        p.selected_strategy['FlopBluffMinEquity']) and \
                            self.decision == DecisionTypes.check and \
                    (t.playersAhead == 0 or p.selected_strategy['flop_bluffing_condidion_1'] == 0):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                self.logger.debug("Bluffing activated")

            # turn
            elif t.gameStage == GameStages.Turn.value and \
                    not h.last_round_bluff and \
                    (not t.other_player_has_initiative or p.selected_strategy['turn_bluffing_condidion_2'] == 0) and \
                            self.decision == DecisionTypes.check and \
                                    float(p.selected_strategy['TurnBluffMaxEquity']) > t.equity > float(
                        p.selected_strategy['TurnBluffMinEquity']) and \
                    (t.playersAhead == 0 or p.selected_strategy['turn_bluffing_condidion_1'] == 0):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                self.logger.debug("Bluffing activated")

            # river
            elif t.gameStage == GameStages.River.value and \
                    not h.last_round_bluff and \
                    (not t.other_player_has_initiative or p.selected_strategy['river_bluffing_condidion_2'] == 0) and \
                            self.decision == DecisionTypes.check and \
                                    float(p.selected_strategy['RiverBluffMaxEquity']) > t.equity > float(
                        p.selected_strategy['RiverBluffMinEquity']) and \
                    (t.playersAhead == 0 or p.selected_strategy['river_bluffing_condidion_1'] == 0):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                self.logger.debug("Bluffing activated")

    def check_deception(self, t, p, h):
        # Flop
        if t.equity > float(
                p.selected_strategy['FlopCheckDeceptionMinEquity']) and t.gameStage == GameStages.Flop.value and (
                                self.decision == DecisionTypes.bet1 or self.decision == DecisionTypes.bet2 or self.decision == DecisionTypes.bet3 or self.decision == DecisionTypes.bet4):
            self.UseFlopCheckDeception = True
            self.decision = DecisionTypes.check_deception
            self.logger.debug("Check deception activated")
        else:
            self.UseFlopCheckDeception = False

        # Turn
        if h.previous_decision == DecisionTypes.call.value and t.equity > float(
                p.selected_strategy['TurnCheckDeceptionMinEquity']) and t.gameStage == GameStages.Turn.value and (
                                self.decision == DecisionTypes.bet1 or self.decision == DecisionTypes.bet2 or self.decision == DecisionTypes.bet3 or self.decision == DecisionTypes.bet4):
            self.UseTurnCheckDeception = True
            self.decision = DecisionTypes.check_deception
            self.logger.debug("Check deception activated")
        else:
            self.UseTurnCheckDeception = False

        # River
        if h.previous_decision == DecisionTypes.call.value and t.equity > float(
                p.selected_strategy['RiverCheckDeceptionMinEquity']) and t.gameStage == GameStages.River.value and (
                                self.decision == DecisionTypes.bet1 or self.decision == DecisionTypes.bet2 or self.decision == DecisionTypes.bet3 or self.decision == DecisionTypes.bet4):
            self.UseRiverCheckDeception = True
            self.decision = DecisionTypes.check_deception
            self.logger.debug("Check deception activated")
        else:
            self.UseRiverCheckDeception = False

    def call_deception(self, t, p, h):
        pass

    def bully(self, t, p, h):
        if t.isHeadsUp:
            for i in range(5):
                if t.other_players[i]['status'] == 1:
                    break
            opponentFunds = t.other_players[i]['funds']

            if opponentFunds == '': opponentFunds = float(p.selected_strategy['initialFunds'])

            self.bullyMode = opponentFunds > float(p.selected_strategy['bullyDivider'])

            if (t.equity >= float(p.selected_strategy['minBullyEquity'])) and (
                        t.equity <= float(p.selected_strategy['maxBullyEquity'])) and self.bullyMode:
                self.decision = DecisionTypes.bet_bluff
                self.logger.info("Bullying activated")
                self.bullyDecision = True
            else:
                self.bullyDecision = False

    def admin(self, t, p, h):
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 2 and self.decision == DecisionTypes.bet1: self.decision = DecisionTypes.bet2
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 3 and self.decision == DecisionTypes.bet1: self.decision = DecisionTypes.bet3
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 3 and self.decision == DecisionTypes.bet2: self.decision = DecisionTypes.bet3
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet1: self.decision = DecisionTypes.bet4
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet2: self.decision = DecisionTypes.bet4
        if int(p.selected_strategy[
                   'minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet3: self.decision = DecisionTypes.bet4

        if t.checkButton == False and t.minCall == 0.0 and p.selected_strategy['use_pot_multiples'] == 0:
            self.ErrCallButton = True
            self.logger.error("Call button or pot multiple had no value")
        else:
            self.ErrCallButton = False

        if t.checkButton == True:
            if self.decision == DecisionTypes.fold: self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call: self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call_deception: self.decision = DecisionTypes.check_deception

        if t.allInCallButton and self.decision != DecisionTypes.fold:
            self.decision = DecisionTypes.call

        h.lastSecondRoundAdjustment = self.secondRoundAdjustment

        if self.decision == DecisionTypes.check or self.decision == DecisionTypes.check_deception: h.myLastBet = 0
        if self.decision == DecisionTypes.call or self.decision == DecisionTypes.check_deception:  h.myLastBet = t.minCall

        if self.decision == DecisionTypes.bet1: h.myLastBet = t.minBet
        if self.decision == DecisionTypes.bet2: h.myLastBet = t.minBet * float(
            p.selected_strategy['BetPlusInc']) + t.minBet
        if self.decision == DecisionTypes.bet_bluff: h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet3: h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet4: h.myLastBet = t.totalPotValue

    def make_decision(self, t, h, p, logger, l):
        self.preflop_sheet_name = ''
        if t.equity >= float(p.selected_strategy['alwaysCallEquity']):
            self.logger.info("Equity is above the always call threshold")
            self.finalCallLimit = 99999999

        if t.myFunds * int(p.selected_strategy['always_call_low_stack_multiplier']) < t.totalPotValue:
            self.logger.info("Low funds call everything activated")
            self.finalCallLimit = 99999999

        if t.gameStage == GameStages.PreFlop.value:
            self.preflop_table_analyser(t, logger, h, p)

        if not(p.selected_strategy['preflop_override'] and t.gameStage == GameStages.PreFlop.value):
            self.logger.info('Make preflop decision based on non-preflop table')
            self.calling(t, p, h)
            self.betting(t, p, h)
            if t.checkButton:
                self.check_deception(t, p, h)

            if t.allInCallButton == False and t.equity >= float(p.selected_strategy[
                                                                    'secondRiverBetPotMinEquity']) and t.gameStage == GameStages.River.value and h.histGameStage == GameStages.River.value:
                self.decision = DecisionTypes.bet4

                # self.bully(t,p,h,logger)
        else:
            self.logger.info('Preflop table not used for this decision')

        self.admin(t, p, h)
        self.bluff(t, p, h)
        self.decision = self.decision.value
