""""
Strategy Definition
t contains variables that have been scraped from the table
h contains values from the historical (last) decision
p contains values from the Strategy as defined in the xml file
"""

from .base import DecisionBase, Collusion
from .curvefitting import *
from .montecarlo_v3 import *
from enum import Enum
import pandas as pd

class DecisionTypes(Enum):
    i_am_back,fold,check,call,bet1,bet2,bet3,bet4,bet_bluff,call_deception, check_deception=['Imback','Fold','Check','Call','Bet half pot', 'Bet half pot','Bet half pot', 'Bet pot','Bet Bluff','Call Deception','Check Deception']

class GameStages(Enum):
    PreFlop,Flop,Turn,River=['PreFlop','Flop','Turn','River']

class Decision(DecisionBase):
    def __init__(self, t, h, p, logger, l):
        t.bigBlind = float(p.selected_strategy['bigBlind'])
        t.smallBlind = float(p.selected_strategy['smallBlind'])

        t.bigBlindMultiplier = t.bigBlind / 0.02

        # in case the other players called my bet become less aggressive and make an adjustment for the second round
        if (h.histGameStage == t.gameStage and h.lastRoundGameID == h.GameID) or h.lastSecondRoundAdjustment > 0:
            if t.gameStage == 'PreFlop':
                self.secondRoundAdjustment = float(p.selected_strategy['secondRoundAdjustmentPreFlop'])
            else:
                self.secondRoundAdjustment = float(p.selected_strategy['secondRoundAdjustment'])

            secondRoundAdjustmentPowerIncrease = float(p.selected_strategy['secondRoundAdjustmentPowerIncrease'])
        else:
            self.secondRoundAdjustment = 0
            secondRoundAdjustmentPowerIncrease = 0

        P = float(t.totalPotValue)
        n = t.coveredCardHolders
        self.maxCallEV = self.calc_EV_call_limit(t.equity, P)
        # self.maxBetEV = self.calc_bet_limit(t.equity, P, float(p.selected_strategy['c']), t, logger)
        logger.debug("Max call EV: " + str(self.maxCallEV))

        self.DeriveCallButtonFromBetButton = False
        try:
            t.minCall = float(t.currentCallValue)
        except:
            t.minCall = float(0.0)
            if t.checkButton == False:
                logger.warning(
                    "Failed to convert current Call value, saving error.png, deriving from bet value, result:")
                self.DeriveCallButtonFromBetButton = True
                t.minCall = np.round(float(t.get_current_bet_value()) / 2, 2)
                logger.info("mincall: " + str(t.minCall))
                # adjMinCall=minCall*c1*c2

        try:
            t.minBet = float(t.currentBetValue)
            t.opponentBetIncreases = t.minBet - h.myLastBet
        except:
            logger.warning("Betvalue not recognised!")
            t.minBet = float(100.0)
            t.opponentBetIncreases = 0

        self.potAdjustmentPreFlop = t.totalPotValue / t.bigBlind / 250 * float(
            p.selected_strategy['potAdjustmentPreFlop'])
        self.potAdjustmentPreFlop = min(self.potAdjustmentPreFlop,
                                        float(p.selected_strategy['maxPotAdjustmentPreFlop']))

        self.potAdjustment = t.totalPotValue / t.bigBlind / 250 * float(p.selected_strategy['potAdjustment'])
        self.potAdjustment = min(self.potAdjustment, float(p.selected_strategy['maxPotAdjustment']))

        if t.gameStage == GameStages.PreFlop.value:
            t.power1 = float(p.selected_strategy['PreFlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['PreFlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustmentPreFlop
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Flop.value:
            t.power1 = float(p.selected_strategy['FlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['FlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Turn.value:
            t.power1 = float(p.selected_strategy['TurnCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['TurnMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.River.value:
            t.power1 = float(p.selected_strategy['RiverCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['RiverMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1

        t.maxValue = float(p.selected_strategy['initialFunds']) * t.potStretch
        d = Curvefitting(np.array([t.equity]), t.smallBlind, t.minCallAmountIfAboveLimit, t.maxValue, t.minEquityCall,
                         t.maxEquityCall, t.power1)
        self.maxCallE = round(d.y[0], 2)

        if t.gameStage == GameStages.PreFlop.value:
            t.power2 = float(p.selected_strategy['PreFlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['PreFlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = float(p.selected_strategy['PreFlopMaxBetEquity'])
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Flop.value:
            t.power2 = float(p.selected_strategy['FlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['FlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Turn.value:
            t.power2 = float(p.selected_strategy['TurnBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['TurnMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.River.value:
            t.power2 = float(p.selected_strategy['RiverBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['RiverMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2

        # adjustment for player profile
        if t.isHeadsUp and t.gameStage != GameStages.PreFlop.value:
            try:
                self.flop_probability_player = l.get_flop_frequency_of_player(t.PlayerNames[0])
                logger.info("Probability profile of : " + t.PlayerNames[0] + ": " + str(self.flop_probability_player))
            except:
                self.flop_probability_player = np.nan

            if self.flop_probability_player < 0.30:
                logger.info("Defensive play due to probability profile")
                t.power1 += 2
                t.power2 += 2
                self.player_profile_adjustment = 2
            elif self.flop_probability_player > 0.60:
                logger.info("Agressive play due to probability profile")
                t.power1 -= 2
                t.power2 -= 2
                self.player_profile_adjustment = -2
            else:
                self.player_profile_adjustment = 0

        d = Curvefitting(np.array([t.equity]), t.smallBlind, t.minBetAmountIfAboveLimit, t.maxValue, t.minEquityBet,
                         t.maxEquityBet, t.power2)
        self.maxBetE = round(d.y[0], 2)

        self.finalCallLimit = self.maxCallE  # min(self.maxCallE, self.maxCallEV)
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

    def preflop_override(self,t,logger):
        def check_probability(sheet):
            try:
                probability = sheet[sheet.ix[:, 0] == card_str1].ix[:, 1].iloc[0]
            except:
                try:
                    probability = sheet[sheet.ix[:, 0] == card_str2].ix[:, 1].iloc[0]
                except:
                    probability = 100

            if probability > rnd:
                return True
            else:
                return False

        if t.gameStage==GameStages.PreFlop.value:
            pass
            rnd=np.random.uniform(0, 100, 1)[0]
            cards=''.join([x[0] for x in t.mycards])
            cards2=cards[1]+cards[0]
            suits=''.join([x[1] for x in t.mycards])
            suited='S' if suits[0]==suits[1] else 'O'
            suited=suited if not cards[0]==cards[1] else ''
            card_str1=cards+suited
            card_str2=cards2+suited

            if t.position_utg_plus==0:
                pass

            call_sheet=pd.ExcelFile('preflop_table.xlsx').parse('Blad1')
            bet_sheet=pd.ExcelFile('preflop_table.xlsx').parse('Blad1')

            bet_list=list(map(lambda x:x.upper(),bet_sheet.ix[:,0].astype(str).tolist()))
            call_list=list(map(lambda x: x.upper(),call_sheet.ix[:, 0].astype(str).tolist()))

            try:
                max_player_pot = max(t.PlayerPots) if max(t.PlayerPots) != '' else 0
            except:
                max_player_pot = 0

            self.decision = DecisionTypes.fold

            if (card_str1 in bet_list or card_str2 in bet_list) and max_player_pot < 2 * t.bigBlind:
                if check_probability(bet_sheet):
                    self.decision=DecisionTypes.bet3
                    logger.info('Preflop betting activated from table')

            elif (card_str1 in call_list or card_str2 in call_list):
                if check_probability(call_sheet):
                    self.decision = DecisionTypes.call
                    logger.info('Preflop calling activated from table')



    def calling(self,t,p,h,logger):
        if self.finalCallLimit < t.minCall:
            self.decision = DecisionTypes.fold
            logger.debug("Call limit exceeded: suggest folding")
        if self.finalCallLimit >= t.minCall:
            self.decision = DecisionTypes.call
            logger.debug("Call limit ok: calling would be fine")

    def betting(self,t,p,h,logger):
        try: max_player_pot=max(t.PlayerPots) if max(t.PlayerPots)!='' else 0
        except: max_player_pot=0

        if t.gameStage != GameStages.PreFlop.value or t.gameStage == GameStages.PreFlop.value and max_player_pot < 2 * t.bigBlind:
            if self.finalBetLimit >= t.minBet:
                self.decision = DecisionTypes.bet1
            if self.finalBetLimit >= (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) and (
                                t.gameStage == GameStages.PreFlop.value or (
                                t.gameStage == GameStages.Turn.value and t.totalPotValue > t.bigBlind * 3) or t.gameStage == GameStages.River.value):
                self.decision = DecisionTypes.bet2
            if (self.finalBetLimit >= float(t.totalPotValue) / 2) and (t.minBet < float(t.totalPotValue) / 2) and (
                        (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) < float(
                        t.totalPotValue) / 2) and (
                        (t.gameStage == GameStages.Turn.value and float(
                            t.totalPotValue) / 2 < t.bigBlind * 20) or t.gameStage == GameStages.River.value):
                self.decision = DecisionTypes.bet3
            if (t.allInCallButton == False and t.equity >= float(p.selected_strategy['betPotRiverEquity'])) and (
                        t.minBet <= float(t.totalPotValue)) and t.gameStage == GameStages.River.value and (
                        float(t.totalPotValue) < t.bigBlind * float(
                        p.selected_strategy['betPotRiverEquityMaxBBM'])) and (
                        (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) < float(t.totalPotValue)):
                self.decision = DecisionTypes.bet4

    def bluff(self,t,p,h,logger):
        t.currentBluff = 0
        if t.isHeadsUp == True:
            if t.gameStage == GameStages.Flop.value and t.PlayerPots == [] and t.equity > float(
                    p.selected_strategy['FlopBluffMinEquity']) and self.decision == DecisionTypes.check and float(
                p.selected_strategy['FlopBluff']) > 0:
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                logger.debug("Bluffing activated")
            elif t.gameStage == GameStages.Turn.value and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == DecisionTypes.check and float(
                    p.selected_strategy['TurnBluff']) > 0 and t.equity > float(
                p.selected_strategy['TurnBluffMinEquity']):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                logger.debug("Bluffing activated")
            elif t.gameStage == GameStages.River.value and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == DecisionTypes.check and float(
                    p.selected_strategy['RiverBluff']) > 0 and t.equity > float(
                p.selected_strategy['RiverBluffMinEquity']):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet_bluff
                logger.debug("Bluffing activated")

    def check_deception(self,t,p,logger):
        if t.equity >= float(p.selected_strategy['FlopCheckDeceptionMinEquity']) and t.gameStage == GameStages.Flop.value and (
                                    self.decision == DecisionTypes.bet1 or self.decision == DecisionTypes.bet2 or self.decision == DecisionTypes.bet3 or self.decision == DecisionTypes.bet4):
            self.UseFlopCheckDeception = True
            self.decision = DecisionTypes.check_deception
            logger.debug("Check deception activated")
        else:
            self.UseFlopCheckDeception = False
            logger.debug("No check deception")

    def bully(self,t,p,h,logger):
        if t.isHeadsUp:
            try:
                opponentFunds = min(t.PlayerFunds)
            except:
                opponentFunds = float(p.selected_strategy['initialFunds'])

            if opponentFunds == '': opponentFunds = float(p.selected_strategy['initialFunds'])

            self.bullyMode = opponentFunds < float(p.selected_strategy['initialFunds']) / float(
                p.selected_strategy['bullyDivider'])

            if (t.equity >= float(p.selected_strategy['minBullyEquity'])) and (
                        t.equity <= float(p.selected_strategy['maxBullyEquity'])) and self.bullyMode:
                self.decision = DecisionTypes.bet_bluff
                logger.info("Bullying activated")
                self.bullyDecision = True
            else:
                self.bullyDecision = False

    def admin(self,t,p,h,logger):
        if t.checkButton == False and t.minCall == 0.0:
            self.decision = DecisionTypes.fold  # for cases where call button cannnot be read, not even after deriving from Bet Button
            self.ErrCallButton = True
            logger.error("Call button had no value")
        else:
            self.ErrCallButton = False

        if t.checkButton == True:
            if self.decision == DecisionTypes.fold: self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call: self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call_deception: self.decision = DecisionTypes.check_deception

        if t.allInCallButton and self.decision != DecisionTypes.fold:
            self.decision = DecisionTypes.call

        h.lastRoundGameID = h.GameID
        h.lastSecondRoundAdjustment = self.secondRoundAdjustment

        if self.decision == DecisionTypes.check or self.decision == DecisionTypes.check_deception: h.myLastBet = 0
        if self.decision == DecisionTypes.call or self.decision == DecisionTypes.check_deception:  h.myLastBet = t.minCall

        if self.decision == DecisionTypes.bet1: h.myLastBet = t.minBet
        if self.decision == DecisionTypes.bet2: h.myLastBet = t.minBet * float(
            p.selected_strategy['BetPlusInc']) + t.minBet
        if self.decision == DecisionTypes.bet_bluff: h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet3: h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet4: h.myLastBet = t.totalPotValue

        self.decision_obj = copy(self.decision)
        self.decision = self.decision.value

    def make_decision(self, t, h, p, logger, l):
        if t.equity >= float(p.selected_strategy['alwaysCallEquity']):
            self.finalCallLimit = 99999999

        self.calling(t,p,h,logger)
        self.betting(t,p,h,logger)
        self.check_deception(t,p,logger)

        if t.allInCallButton == False and t.equity >= float(p.selected_strategy['secondRiverBetPotMinEquity']) and t.gameStage == GameStages.River.value and h.histGameStage == GameStages.River.value:
            self.decision = DecisionTypes.bet3

        self.bluff(t,p,h,logger)
        self.bully(t,p,h,logger)

        if p.selected_strategy['preflop_override']:
            self.preflop_override(t,logger)

        self.admin(t,p,h,logger)
