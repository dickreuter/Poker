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
    def make_decision(self, t, h, p, gui, logger):
        gui.statusbar.set("Starting decision analysis")
        bigBlind = float(p.XML_entries_list1['bigBlind'].text)
        smallBlind = float(p.XML_entries_list1['smallBlind'].text)


        # Prepare for montecarlo simulation to evaluate equity (probability of winning with given cards)

        if t.gameStage == "PreFlop":
            # t.assumedPlayers = t.coveredCardHolders - int(
            #    round(t.playersAhead * (1 - float(p.XML_entries_list1['CoveredPlayersCallLikelihoodPreFlop'].text)))) + 1
            t.assumedPlayers = 2

        elif t.gameStage == "Flop":
            t.assumedPlayers = t.coveredCardHolders - int(
                round(t.playersAhead * (1 - float(p.XML_entries_list1['CoveredPlayersCallLikelihoodFlop'].text)))) + 1

        else:
            t.assumedPlayers = t.coveredCardHolders + 1

        t.assumedPlayers = min(max(t.assumedPlayers, 2), 3)

        t.PlayerCardList = []
        t.PlayerCardList.append(t.mycards)

        # add cards from colluding players (not yet implemented)
        col = Collusion()

        if t.gameStage == "PreFlop":
            maxRuns = 15000
        else:
            maxRuns = 7500
        maxSecs = 2
        gui.statusbar.set("Running Monte Carlo: " + str(maxRuns))
        m = MonteCarlo()
        m.run_montecarlo(t.PlayerCardList, t.cardsOnTable, int(t.assumedPlayers), gui, maxRuns=maxRuns, maxSecs=maxSecs)
        gui.statusbar.set("Monte Carlo completed successfully")

        bigBlindMultiplier = bigBlind / 0.02
        self.equity = np.round(m.equity, 3)
        # --- Equity calculation completed ---

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
        self.maxCallEV = self.calc_EV_call_limit(m.equity, P)
        self.maxBetEV = self.calc_bet_limit(m.equity, P, float(p.XML_entries_list1['c'].text), t, logger)
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
            gui.statusbar.set("Betvalue not regognised")
            t.minBet = float(100.0)
            t.opponentBetIncreases = 0

        self.potAdjustment = t.totalPotValue / bigBlind / 250 * float(p.XML_entries_list1['potAdjustment'].text)
        self.potAdjustment = min(self.potAdjustment, float(p.XML_entries_list1['maxPotAdjustment'].text))

        if t.gameStage == "PreFlop":
            power1 = float(p.XML_entries_list1['PreFlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XML_entries_list1['PreFlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "Flop":
            power1 = float(p.XML_entries_list1['FlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XML_entries_list1['FlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "Turn":
            power1 = float(p.XML_entries_list1['TurnCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XML_entries_list1['TurnMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "River":
            power1 = float(p.XML_entries_list1['RiverCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XML_entries_list1['RiverMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1

        maxValue = float(p.XML_entries_list1['initialFunds'].text) * potStretch
        d = Curvefitting(np.array([self.equity]), smallBlind, minCallAmountIfAboveLimit, maxValue, minEquityCall,
                         maxEquityCall, power1)
        self.maxCallE = round(d.y[0], 2)

        if t.gameStage == "PreFlop":
            power2 = float(p.XML_entries_list1['PreFlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XML_entries_list1['PreFlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = float(p.XML_entries_list1['PreFlopMaxBetEquity'].text)
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "Flop":
            power2 = float(p.XML_entries_list1['FlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XML_entries_list1['FlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "Turn":
            power2 = float(p.XML_entries_list1['TurnBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XML_entries_list1['TurnMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "River":
            power2 = float(p.XML_entries_list1['RiverBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XML_entries_list1['RiverMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2

        maxValue = float(p.XML_entries_list1['initialFunds'].text) * potStretch
        d = Curvefitting(np.array([self.equity]), smallBlind, minBetAmountIfAboveLimit, maxValue, minEquityBet,
                         maxEquityBet, power2)
        self.maxBetE = round(d.y[0], 2)

        self.finalCallLimit = self.maxCallE  # min(self.maxCallE, self.maxCallEV)
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

        # --- start of decision making logic ---

        if self.equity >= float(p.XML_entries_list1['alwaysCallEquity'].text):
            self.finalCallLimit = 99999999

        if self.finalCallLimit < t.minCall:
            self.decision = "Fold"
        if self.finalCallLimit >= t.minCall:
            self.decision = "Call"
        if self.finalBetLimit >= t.minBet:
            self.decision = "Bet"
        if self.finalBetLimit >= (t.minBet + bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) and (
                    (t.gameStage == "Turn" and t.totalPotValue > bigBlind * 3) or t.gameStage == "River"):
            self.decision = "BetPlus"
        if (self.finalBetLimit >= float(t.totalPotValue) / 2) and (t.minBet < float(t.totalPotValue) / 2) and (
                    (t.minBet + bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) < float(
                    t.totalPotValue) / 2) and (
                    (t.gameStage == "Turn" and float(t.totalPotValue) / 2 < bigBlind * 20) or t.gameStage == "River"):
            self.decision = "Bet half pot"
        if (t.allInCallButton == False and self.equity >= float(p.XML_entries_list1['betPotRiverEquity'].text)) and (
                    t.minBet <= float(t.totalPotValue)) and t.gameStage == "River" and (
                    float(t.totalPotValue) < bigBlind * float(
                    p.XML_entries_list1['betPotRiverEquityMaxBBM'].text)) and (
                    (t.minBet + bigBlind * float(p.XML_entries_list1['BetPlusInc'].text)) < float(t.totalPotValue)):
            self.decision = "Bet pot"

        if t.checkButton == False and t.minCall == 0.0:
            self.decision = "Fold"  # for cases where call button cannnot be read, not even after deriving from Bet Button
            self.ErrCallButton = True
        else:
            self.ErrCallButton = False

        if self.equity >= float(p.XML_entries_list1['FlopCheckDeceptionMinEquity'].text) and t.gameStage == "Flop" and (
                                    self.decision == "Bet" or self.decision == "BetPlus" or self.decision == "Bet half pot" or self.decision == "Bet pot" or self.decision == "Bet max"):
            self.UseFlopCheckDeception = True
            self.decision = "Call Deception"
        else:
            self.UseFlopCheckDeception = False

        if t.allInCallButton == False and self.equity >= float(p.XML_entries_list1[
                                                                   'secondRiverBetPotMinEquity'].text) and t.gameStage == "River" and h.histGameStage == "River":
            self.decision = "Bet pot"

        if t.checkButton == True:
            if self.decision == "Fold": self.decision = "Check"
            if self.decision == "Call": self.decision = "Check"
            if self.decision == "Call Deception": self.decision = "Check Deception"

        t.currentBluff = 0
        if t.isHeadsUp == True:
            if t.gameStage == "Flop" and t.PlayerPots == [] and self.equity > float(
                    p.XML_entries_list1['FlopBluffMinEquity'].text) and self.decision == "Check" and float(
                p.XML_entries_list1['FlopBluff'].text) > 0:
                t.currentBluff = float(p.XML_entries_list1['FlopBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "Turn" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XML_entries_list1['TurnBluff'].text) > 0 and self.equity > float(
                p.XML_entries_list1['TurnBluffMinEquity'].text):
                t.currentBluff = float(p.XML_entries_list1['TurnBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "River" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XML_entries_list1['RiverBluff'].text) > 0 and self.equity > float(
                p.XML_entries_list1['RiverBluffMinEquity'].text):
                t.currentBluff = float(p.XML_entries_list1['RiverBluff'].text)
                self.decision = "Bet Bluff"

        # bullyMode
        if t.isHeadsUp:
            try:
                opponentFunds = min(t.PlayerFunds)
            except:
                opponentFunds = float(p.XML_entries_list1['initialFunds'].text)

            self.bullyMode = opponentFunds < float(p.XML_entries_list1['initialFunds'].text) / float(
                p.XML_entries_list1['bullyDivider'].text)

            if (m.equity >= float(p.XML_entries_list1['minBullyEquity'].text)) and (
                        m.equity <= float(p.XML_entries_list1['maxBullyEquity'].text)) and self.bullyMode:
                self.decision == "Bet Bluff"
                t.currentBluff = 10
                self.bullyDecision = True
            else:
                self.bullyDecision = False

        # --- end of decision making logic ---

        h.lastRoundGameID = h.GameID
        h.lastSecondRoundAdjustment = self.secondRoundAdjustment

        if self.decision == "Check" or self.decision == "Check Deception": h.myLastBet = 0
        if self.decision == "Call" or self.decision == "Call Deception":  h.myLastBet = t.minCall

        if self.decision == "Bet": h.myLastBet = t.minBet
        if self.decision == "BetPlus": h.myLastBet = t.minBet * float(p.XML_entries_list1['BetPlusInc'].text) + t.minBet
        if self.decision == "Bet Bluff": h.myLastBet = bigBlind * t.currentBluff
        if self.decision == "Bet half pot": h.myLastBet = t.totalPotValue / 2
        if self.decision == "Bet pot": h.myLastBet = t.totalPotValue

        gui.var1.set("Decision: " + str(self.decision))
        gui.var2.set(
            "Equity: " + str(self.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                int(t.coveredCardHolders)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
        gui.var3.set("Final Call Limit: " + str(self.finalCallLimit) + " --> " + str(t.minCall))
        gui.var4.set("Final Bet Limit: " + str(self.finalBetLimit) + " --> " + str(t.currentBetValue))
        gui.var5.set("Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(self.maxCallEV, 2)))

        if gui.active == True:
            gui.updatePlots(h.histEquity, h.histMinCall, h.histMinBet, m.equity, t.minCall, t.minBet, 'bo', 'ro')
            gui.updateLines(power1, power2, minEquityCall, minEquityBet, smallBlind, bigBlind, maxValue, maxEquityCall,
                            maxEquityBet)

        if gui.active == True:
            gui.pie.clf()
            gui.piePlot = gui.pie.add_subplot(111)
            gui.piePlot.pie([float(v) for v in m.winnerCardTypeList.values()],
                            labels=[k for k in m.winnerCardTypeList.keys()], autopct=None)
            gui.piePlot.set_title('Winning probabilities')
            subtitle_string = ' '.join(t.mycards) + '\n' + ' '.join(t.cardsOnTable)
            # gui.piePlot.suptitle(subtitle_string, y=1.05, fontsize=10)
            gui.pie.canvas.draw()

        gui.statusbar.set(self.decision)
