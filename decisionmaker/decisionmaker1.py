""""
Strategy Definition
t contains variables that have been scraped from the table
h contains values from the historical (last) decision
p contains values from the Strategy as defined in the xml file
"""


from .base import DecisionBase, Collusion
import numpy as np
from .curvefitting import *
from .montecarlo_v3 import *

class Decision(DecisionBase):
    def __init__(self):
        pass

    def make_decision(self, t, h, p, logger, l):
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
        #self.maxBetEV = self.calc_bet_limit(t.equity, P, float(p.selected_strategy['c']), t, logger)
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
                #        adjMinCall=minCall*c1*c2

        try:
            t.minBet = float(t.currentBetValue)
            t.opponentBetIncreases = t.minBet - h.myLastBet
        except:
            logger.warning("Betvalue not recognised!")
            t.minBet = float(100.0)
            t.opponentBetIncreases = 0

        self.potAdjustmentPreFlop = t.totalPotValue / t.bigBlind / 250 * float(p.selected_strategy['potAdjustmentPreFlop'])
        self.potAdjustmentPreFlop = min(self.potAdjustmentPreFlop, float(p.selected_strategy['maxPotAdjustmentPreFlop']))

        self.potAdjustment = t.totalPotValue / t.bigBlind / 250 * float(p.selected_strategy['potAdjustment'])
        self.potAdjustment = min(self.potAdjustment, float(p.selected_strategy['maxPotAdjustment']))

        if t.gameStage == "PreFlop":
            t.power1 = float(p.selected_strategy['PreFlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['PreFlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustmentPreFlop
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "Flop":
            t.power1 = float(p.selected_strategy['FlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['FlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "Turn":
            t.power1 = float(p.selected_strategy['TurnCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['TurnMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "River":
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

        if t.gameStage == "PreFlop":
            t.power2 = float(p.selected_strategy['PreFlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['PreFlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = float(p.selected_strategy['PreFlopMaxBetEquity'])
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "Flop":
            t.power2 = float(p.selected_strategy['FlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['FlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "Turn":
            t.power2 = float(p.selected_strategy['TurnBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['TurnMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "River":
            t.power2 = float(p.selected_strategy['RiverBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy['RiverMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2

        # adjustment for player profile
        if t.isHeadsUp and t.gameStage!="PreFlop":
            try:
                self.flop_probability_player=l.get_flop_frequency_of_player(t.PlayerNames[0])
                logger.info("Probability profile of : "+t.PlayerNames[0] +": "+ str(self.flop_probability_player))
            except:
                self.flop_probability_player=np.nan

            if self.flop_probability_player<0.30:
                logger.info("Defensive play due to probability profile")
                t.power1+=2
                t.power2+=2
                self.player_profile_adjustment=2
            elif self.flop_probability_player>0.60:
                logger.info("Agressive play due to probability profile")
                t.power1-=2
                t.power2-=2
                self.player_profile_adjustment=-2
            else:
                self.player_profile_adjustment = 0

        d = Curvefitting(np.array([t.equity]), t.smallBlind, t.minBetAmountIfAboveLimit, t.maxValue, t.minEquityBet,
                         t.maxEquityBet, t.power2)
        self.maxBetE = round(d.y[0], 2)

        self.finalCallLimit = self.maxCallE  # min(self.maxCallE, self.maxCallEV)
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

        # --- start of decision making logic ---


        if t.equity >= float(p.selected_strategy['alwaysCallEquity']):
            self.finalCallLimit = 99999999

        if self.finalCallLimit < t.minCall:
            self.decision = "Fold"
        if self.finalCallLimit >= t.minCall:
            self.decision = "Call"
        if self.finalBetLimit >= t.minBet:
            self.decision = "Bet"
        if self.finalBetLimit >= (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) and (
                    (t.gameStage == "Turn" and t.totalPotValue > t.bigBlind * 3) or t.gameStage == "River"):
            self.decision = "BetPlus"
        if (self.finalBetLimit >= float(t.totalPotValue) / 2) and (t.minBet < float(t.totalPotValue) / 2) and (
                    (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) < float(
                    t.totalPotValue) / 2) and (
                    (t.gameStage == "Turn" and float(t.totalPotValue) / 2 < t.bigBlind * 20) or t.gameStage == "River"):
            self.decision = "Bet half pot"
        if (t.allInCallButton == False and t.equity >= float(p.selected_strategy['betPotRiverEquity'])) and (
                    t.minBet <= float(t.totalPotValue)) and t.gameStage == "River" and (
                    float(t.totalPotValue) < t.bigBlind * float(
                    p.selected_strategy['betPotRiverEquityMaxBBM'])) and (
                    (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) < float(t.totalPotValue)):
            self.decision = "Bet pot"

        if t.checkButton == False and t.minCall == 0.0:
            self.decision = "Fold"  # for cases where call button cannnot be read, not even after deriving from Bet Button
            self.ErrCallButton = True
        else:
            self.ErrCallButton = False

        if t.equity >= float(p.selected_strategy['FlopCheckDeceptionMinEquity']) and t.gameStage == "Flop" and (
                                    self.decision == "Bet" or self.decision == "BetPlus" or self.decision == "Bet half pot" or self.decision == "Bet pot" or self.decision == "Bet max"):
            self.UseFlopCheckDeception = True
            self.decision = "Call Deception"
        else:
            self.UseFlopCheckDeception = False

        if t.allInCallButton == False and t.equity >= float(p.selected_strategy[
                                                                   'secondRiverBetPotMinEquity']) and t.gameStage == "River" and h.histGameStage == "River":
            self.decision = "Bet pot"

        if t.checkButton == True:
            if self.decision == "Fold": self.decision = "Check"
            if self.decision == "Call": self.decision = "Check"
            if self.decision == "Call Deception": self.decision = "Check Deception"

        t.currentBluff = 0
        if t.isHeadsUp == True:
            if t.gameStage == "Flop" and t.PlayerPots == [] and t.equity > float(
                    p.selected_strategy['FlopBluffMinEquity']) and self.decision == "Check" and float(
                p.selected_strategy['FlopBluff']) > 0:
                t.currentBluff = float(p.selected_strategy['FlopBluff'])
                self.decision = "Bet Bluff"
            elif t.gameStage == "Turn" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.selected_strategy['TurnBluff']) > 0 and t.equity > float(
                p.selected_strategy['TurnBluffMinEquity']):
                t.currentBluff = float(p.selected_strategy['TurnBluff'])
                self.decision = "Bet Bluff"
            elif t.gameStage == "River" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.selected_strategy['RiverBluff']) > 0 and t.equity > float(
                p.selected_strategy['RiverBluffMinEquity']):
                t.currentBluff = float(p.selected_strategy['RiverBluff'])
                self.decision = "Bet Bluff"

        # bullyMode
        if t.isHeadsUp:
            try:
                opponentFunds = min(t.PlayerFunds)
            except:
                opponentFunds = float(p.selected_strategy['initialFunds'])

            if opponentFunds=='': opponentFunds=float(p.selected_strategy['initialFunds'])

            self.bullyMode = opponentFunds < float(p.selected_strategy['initialFunds']) / float(
                p.selected_strategy['bullyDivider'])

            if (t.equity >= float(p.selected_strategy['minBullyEquity'])) and (
                        t.equity <= float(p.selected_strategy['maxBullyEquity'])) and self.bullyMode:
                self.decision = "Bet Bluff"
                logger.info("Bullying activated")
                t.currentBluff = 10
                self.bullyDecision = True
            else:
                self.bullyDecision = False

        if t.allInCallButton and self.decision!="Fold":
            self.decision="Call"

        # --- end of decision making logic ---

        h.lastRoundGameID = h.GameID
        h.lastSecondRoundAdjustment = self.secondRoundAdjustment

        if self.decision == "Check" or self.decision == "Check Deception": h.myLastBet = 0
        if self.decision == "Call" or self.decision == "Call Deception":  h.myLastBet = t.minCall

        if self.decision == "Bet": h.myLastBet = t.minBet
        if self.decision == "BetPlus": h.myLastBet = t.minBet * float(p.selected_strategy['BetPlusInc']) + t.minBet
        if self.decision == "Bet Bluff": h.myLastBet = t.bigBlind * t.currentBluff
        if self.decision == "Bet half pot": h.myLastBet = t.totalPotValue / 2
        if self.decision == "Bet pot": h.myLastBet = t.totalPotValue

