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
        t.bigBlind = float(p.XML_entries_list1['bigBlind'].text)
        t.smallBlind = float(p.XML_entries_list1['smallBlind'].text)



        t.bigBlindMultiplier = t.bigBlind / 0.02

        # in case the other players called my bet become less aggressive and make an adjustment for the second round
        if (h.histGameStage == t.gameStage and h.lastRoundGameID == h.GameID) or h.lastSecondRoundAdjustment > 0:
            if t.gameStage == 'PreFlop':
                self.secondRoundAdjustment = float(p.XML_entries_list1['secondRoundAdjustmentPreFlop'].text)
            else:
                self.secondRoundAdjustment = float(p.XML_entries_list1['secondRoundAdjustment'].text)

            secondRoundAdjustmentPowerIncrease = float(p.XML_entries_list1['secondRoundAdjustmentPowerIncrease'].text)
        else:
            self.secondRoundAdjustment = 0
            secondRoundAdjustmentPowerIncrease = 0

        P = float(t.totalPotValue)
        n = t.coveredCardHolders
        self.maxCallEV = self.calc_EV_call_limit(t.equity, P)
        self.maxBetEV = self.calc_bet_limit(t.equity, P, float(p.XML_entries_list1['c'].text), t, logger)
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

        self.potAdjustmentPreFlop = t.totalPotValue / t.bigBlind / 250 * float(p.XML_entries_list1['potAdjustmentPreFlop'].text)
        self.potAdjustmentPreFlop = min(self.potAdjustmentPreFlop, float(p.XML_entries_list1['maxPotAdjustmentPreFlop'].text))

        self.potAdjustment = t.totalPotValue / t.bigBlind / 250 * float(p.XML_entries_list1['potAdjustment'].text)
        self.potAdjustment = min(self.potAdjustment, float(p.XML_entries_list1['maxPotAdjustment'].text))

        if t.gameStage == "PreFlop":
            t.power1 = float(p.XML_entries_list1['PreFlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.XML_entries_list1['PreFlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustmentPreFlop
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "Flop":
            t.power1 = float(p.XML_entries_list1['FlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.XML_entries_list1['FlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "Turn":
            t.power1 = float(p.XML_entries_list1['TurnCallPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.XML_entries_list1['TurnMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == "River":
            t.power1 = float(p.XML_entries_list1['RiverCallPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.XML_entries_list1['RiverMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1

        t.maxValue = float(p.XML_entries_list1['initialFunds'].text) * t.potStretch
        d = Curvefitting(np.array([t.equity]), t.smallBlind, t.minCallAmountIfAboveLimit, t.maxValue, t.minEquityCall,
                         t.maxEquityCall, t.power1)
        self.maxCallE = round(d.y[0], 2)

        if t.gameStage == "PreFlop":
            t.power2 = float(p.XML_entries_list1['PreFlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.XML_entries_list1['PreFlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = float(p.XML_entries_list1['PreFlopMaxBetEquity'].text)
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "Flop":
            t.power2 = float(p.XML_entries_list1['FlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.XML_entries_list1['FlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "Turn":
            t.power2 = float(p.XML_entries_list1['TurnBetPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.XML_entries_list1['TurnMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == "River":
            t.power2 = float(p.XML_entries_list1['RiverBetPower'].text) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.XML_entries_list1['RiverMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
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


        if t.equity >= float(p.XML_entries_list1['alwaysCallEquity'].text):
            self.finalCallLimit = 99999999

        if self.finalCallLimit < t.minCall:
            self.decision = "Fold"
        if self.finalCallLimit >= t.minCall:
            self.decision = "Call"
        if self.finalBetLimit >= t.minBet:
            self.decision = "Bet"
        if self.finalBetLimit >= (t.minBet + t.bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) and (
                    (t.gameStage == "Turn" and t.totalPotValue > t.bigBlind * 3) or t.gameStage == "River"):
            self.decision = "BetPlus"
        if (self.finalBetLimit >= float(t.totalPotValue) / 2) and (t.minBet < float(t.totalPotValue) / 2) and (
                    (t.minBet + t.bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) < float(
                    t.totalPotValue) / 2) and (
                    (t.gameStage == "Turn" and float(t.totalPotValue) / 2 < t.bigBlind * 20) or t.gameStage == "River"):
            self.decision = "Bet half pot"
        if (t.allInCallButton == False and t.equity >= float(p.XML_entries_list1['betPotRiverEquity'].text)) and (
                    t.minBet <= float(t.totalPotValue)) and t.gameStage == "River" and (
                    float(t.totalPotValue) < t.bigBlind * float(
                    p.XML_entries_list1['betPotRiverEquityMaxBBM'].text)) and (
                    (t.minBet + t.bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) < float(t.totalPotValue)):
            self.decision = "Bet pot"

        if t.checkButton == False and t.minCall == 0.0:
            self.decision = "Fold"  # for cases where call button cannnot be read, not even after deriving from Bet Button
            self.ErrCallButton = True
        else:
            self.ErrCallButton = False

        if t.equity >= float(p.XML_entries_list1['FlopCheckDeceptionMinEquity'].text) and t.gameStage == "Flop" and (
                                    self.decision == "Bet" or self.decision == "BetPlus" or self.decision == "Bet half pot" or self.decision == "Bet pot" or self.decision == "Bet max"):
            self.UseFlopCheckDeception = True
            self.decision = "Call Deception"
        else:
            self.UseFlopCheckDeception = False

        if t.allInCallButton == False and t.equity >= float(p.XML_entries_list1[
                                                                   'secondRiverBetPotMinEquity'].text) and t.gameStage == "River" and h.histGameStage == "River":
            self.decision = "Bet pot"

        if t.checkButton == True:
            if self.decision == "Fold": self.decision = "Check"
            if self.decision == "Call": self.decision = "Check"
            if self.decision == "Call Deception": self.decision = "Check Deception"

        t.currentBluff = 0
        if t.isHeadsUp == True:
            if t.gameStage == "Flop" and t.PlayerPots == [] and t.equity > float(
                    p.XML_entries_list1['FlopBluffMinEquity'].text) and self.decision == "Check" and float(
                p.XML_entries_list1['FlopBluff'].text) > 0:
                t.currentBluff = float(p.XML_entries_list1['FlopBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "Turn" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XML_entries_list1['TurnBluff'].text) > 0 and t.equity > float(
                p.XML_entries_list1['TurnBluffMinEquity'].text):
                t.currentBluff = float(p.XML_entries_list1['TurnBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "River" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XML_entries_list1['RiverBluff'].text) > 0 and t.equity > float(
                p.XML_entries_list1['RiverBluffMinEquity'].text):
                t.currentBluff = float(p.XML_entries_list1['RiverBluff'].text)
                self.decision = "Bet Bluff"

        # bullyMode
        if t.isHeadsUp:
            try:
                opponentFunds = min(t.PlayerFunds)
            except:
                opponentFunds = float(p.XML_entries_list1['initialFunds'].text)

            if opponentFunds=='': opponentFunds=float(p.XML_entries_list1['initialFunds'].text)

            self.bullyMode = opponentFunds < float(p.XML_entries_list1['initialFunds'].text) / float(
                p.XML_entries_list1['bullyDivider'].text)

            if (t.equity >= float(p.XML_entries_list1['minBullyEquity'].text)) and (
                        t.equity <= float(p.XML_entries_list1['maxBullyEquity'].text)) and self.bullyMode:
                self.decision == "Bet Bluff"
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
        if self.decision == "BetPlus": h.myLastBet = t.minBet * float(p.XML_entries_list1['BetPlusInc'].text) + t.minBet
        if self.decision == "Bet Bluff": h.myLastBet = t.bigBlind * t.currentBluff
        if self.decision == "Bet half pot": h.myLastBet = t.totalPotValue / 2
        if self.decision == "Bet pot": h.myLastBet = t.totalPotValue

