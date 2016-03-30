import time
import win32gui
import os.path
import win32api
import re
import threading
import xml.etree.ElementTree as xml
import random
import math
import sys
import numpy as np
import win32con
from PIL import Image, ImageGrab, ImageDraw, ImageFilter
import pytesseract
import cv2
from Curvefitting import Curvefitting
from Montecarlo_v3 import MonteCarlo
from Genetic_Algorithm import *
from XMLHandler import *
from Captcha_manager import *
from KeyPressVBox import *
from Log_manager import *
from GUI_Tkinter import *
from Terminal import *
import winsound

class History(object):
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

class Tools(object):
    # General tools that are used to operate the pokerbot, such as moving the mouse, clicking and routines that
    # call Opencv for image recognition
    def __init__(self):
        self.load_templates()

    def load_templates(self):

        self.cardImages = dict()
        self.img = dict()
        values = "23456789TJQKA"
        suites = "CDHS"
        for x in values:
            for y in suites:
                name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/" + x + y + ".png"
                if os.path.exists(name) == True:
                    self.img[x + y] = Image.open(name)
                    self.cardImages[x + y] = cv2.cvtColor(np.array(self.img[x + y]), cv2.COLOR_BGR2RGB)
                else:
                    print("Cardimage File not found")

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/button.png"
        template = Image.open(name)
        self.button = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/topleft.png"
        template = Image.open(name)
        self.topLeftCorner = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/coveredcard.png"
        template = Image.open(name)
        self.coveredCardHolder = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/imback.png"
        template = Image.open(name)
        self.ImBack = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/check.png"
        template = Image.open(name)
        self.check = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/call.png"
        template = Image.open(name)
        self.call = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/smalldollarsign1.png"
        template = Image.open(name)
        self.smallDollarSign1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        if p.XML_entries_list1['pokerSite'].text == "PP":
            name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/smalldollarsign2.png"
            template = Image.open(name)
            self.smallDollarSign2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/allincallbutton.png"
        template = Image.open(name)
        self.allInCallButton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/lostEverything.png"
        template = Image.open(name)
        self.lostEverything = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

    def take_screenshot(self):
        if gui.active == True:
            gui.statusbar.set("")
        time.sleep(0.1)
        self.entireScreenPIL = ImageGrab.grab()
        if gui.active == True:
            gui.statusbar.set(str(p.current_strategy.text))
        if terminalmode == False and p.ExitThreads == True: sys.exit()
        return True

    def click(self, x, y):
        win32api.SetCursorPos((x, y))
        time.sleep(np.random.uniform(0.1, 0.5, 1))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def mouse_mover(self, x1, y1, x2, y2):
        speed = .4
        stepMin = 7
        stepMax = 50
        rd1 = int(np.round(np.random.uniform(stepMin, stepMax, 1)))
        rd2 = int(np.round(np.random.uniform(stepMin, stepMax, 1)))

        xa = list(range(x1, x2, rd1))
        ya = list(range(y1, y2, rd2))

        for k in range(0, max(0, len(xa) - len(ya))):
            ya.append(y2)
        for k in range(0, max(0, len(ya) - len(xa))):
            xa.append(x2)

        xTremble = 20
        yTremble = 20

        for i in range(len(max(xa, ya))):
            x = xa[i] + int(+random.random() * xTremble)
            y = ya[i] + int(+random.random() * yTremble)
            win32api.SetCursorPos((x, y))
            time.sleep(np.random.uniform(0.1 * speed, 0.01 * speed, 1))

        win32api.SetCursorPos((x2, y2))

    def mouse_clicker(self, x2, y2, buttonToleranceX, buttonToleranceY):

        xrand = np.random.uniform(0, buttonToleranceX, 1)
        yrand = np.random.uniform(0, buttonToleranceY, 1)
        win32api.SetCursorPos((x2 + xrand, y2 + yrand))

        self.click(x2 + xrand, y2 + yrand)

        time.sleep(np.random.uniform(0.1, 0.5, 1))

    def find_template_on_screen(self, template, screenshot, threshold):
        # 'cv2.TM_CCOEFF', 'cv2.TM_CCOEFF_NORMED', 'cv2.TM_CCORR',  'cv2.TM_CCORR_NORMED', 'cv2.TM_SQDIFF', 'cv2.TM_SQDIFF_NORMED']
        method = eval('cv2.TM_SQDIFF_NORMED')
        # Apply template Matching
        res = cv2.matchTemplate(screenshot, template, method)
        loc = np.where(res <= threshold)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            bestFit = min_loc
        else:
            bestFit = max_loc

        count = 0
        points = []
        for pt in zip(*loc[::-1]):
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            points.append(pt)
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        return count, points, bestFit

    def setup_get_item_location(self):
        topleftcorner = "pics/PP/topleft.png"
        name = "pics/PP/screenshot7.png"
        findTemplate = "pics/PP/fullchatwindow.png"

        setup = cv2.cvtColor(np.array(Image.open(name)), cv2.COLOR_BGR2RGB)
        tlc = cv2.cvtColor(np.array(Image.open(topleftcorner)), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(setup, tlc, 0.01)
        rel = tuple(-1 * np.array(bestfit))

        template = cv2.cvtColor(np.array(Image.open(findTemplate)), cv2.COLOR_BGR2RGB)

        count, points, bestfit = a.find_template_on_screen(setup, template, 0.01)
        print(count, points, bestfit)

        print(findTemplate + " Relative: ")
        print(tuple(map(sum, zip(points[0], rel))))

class Collusion(object):
    # If more than one pokerbot plays on the same table, the players can collude. This is not yet fully implemented
    # The gained advantage is expected to be limited unless a corresponding strategy is trained independently
    def __init__(self):
        pass
        # connect to server to download other player cards
        # add cards
        # for cardLIst in ColludingPlayers
        # t.PlayerCardList.append(cardList)

class DecisionMaker(object):
    # Contains routines that make the actual decisions to play: the main function is make_decision
    def calc_bet_EV(self, E, P, S, c):
        n = 1 if t.isHeadsUp == True else 2
        f = max(0, 1 - min(S / P, 1)) * c * n
        EV = E * (P + f) - (1 - E) * S
        return EV

    def calc_call_EV(self, E, P, S):
        EV = (E * (P - S + S)) - ((1 - E) * S)
        return EV

    def calc_EV_call_limit(self, E, P):
        MaxCall = 10
        CallValues = np.arange(0.01, MaxCall, 0.01)
        EV = [self.calc_call_EV(E, P, S) for S in CallValues]
        BestEquity = min(EV, key=lambda x: abs(x - 0))
        ind = EV.index(BestEquity)
        self.zeroEvCallSize = np.round(EV.index(BestEquity), 2)
        return CallValues[self.zeroEvCallSize]

    def calc_bet_limit(self, E, P, c):
        Step = 0.01
        MaxCall = 1000
        rng = int(np.round((1 * Step + MaxCall) / Step))
        EV = [self.calc_bet_EV(E, P, S * Step, c) for S in range(rng)]
        X = range(rng)

        # plt.plot(X[1:200],EV[1:200])
        # plt.show()

        BestEquity = max(EV)
        # print ("Experimental maximum EV for betting: "+str(BestEquity))
        ind = EV.index(BestEquity)
        self.maxEvBetSize = np.round(EV.index(BestEquity) * Step, 2)
        return self.maxEvBetSize

    def calc_max_invest(self, equity, pw, bigBlindMultiplier):
        return np.round((equity ** pw) * bigBlindMultiplier, 2)

    def make_decision(self, t, h, p):
        gui.statusbar.set("Starting decision analysis")
        bigBlind = float(p.XMLEntriesList['bigBlind'].text)
        smallBlind = float(p.XMLEntriesList['smallBlind'].text)

        if t.gameStage == "PreFlop":
            # t.assumedPlayers = t.coveredCardHolders - int(
            #    round(t.playersAhead * (1 - float(p.XMLEntriesList['CoveredPlayersCallLikelihoodPreFlop'].text)))) + 1
            t.assumedPlayers = 2

        elif t.gameStage == "Flop":
            t.assumedPlayers = t.coveredCardHolders - int(
                round(t.playersAhead * (1 - float(p.XMLEntriesList['CoveredPlayersCallLikelihoodFlop'].text)))) + 1

        else:
            t.assumedPlayers = t.coveredCardHolders + 1

        t.assumedPlayers = min(max(t.assumedPlayers, 2), 3)

        t.PlayerCardList = []
        t.PlayerCardList.append(t.mycards)

        # add cards from colluding players
        col = Collusion()

        if t.gameStage == "PreFlop":
            maxRuns = 15000
        else:
            maxRuns = 7500
        maxSecs = 3
        gui.statusbar.set("Running Monte Carlo: " + str(maxRuns))
        m = MonteCarlo()
        m.RunMonteCarlo(t.PlayerCardList, t.cardsOnTable, int(t.assumedPlayers), gui, maxRuns=maxRuns, maxSecs=maxSecs)
        gui.statusbar.set("Monte Carlo completed successfully")

        bigBlindMultiplier = bigBlind / 0.02
        self.equity = np.round(m.equity, 3)

        if (h.histGameStage == t.gameStage and h.lastRoundGameID == h.GameID) or h.lastSecondRoundAdjustment > 0:
            if t.gameStage == 'PreFlop':
                self.secondRoundAdjustment = float(p.XMLEntriesList['secondRoundAdjustmentPreFlop'].text)
            else:
                self.secondRoundAdjustment = float(p.XMLEntriesList['secondRoundAdjustment'].text)

            secondRoundAdjustmentPowerIncrease = float(p.XMLEntriesList['secondRoundAdjustmentPowerIncrease'].text)
        else:
            self.secondRoundAdjustment = 0
            secondRoundAdjustmentPowerIncrease = 0

        P = float(t.totalPotValue)
        n = t.coveredCardHolders
        self.maxCallEV = self.calc_EV_call_limit(m.equity, P)
        self.maxBetEV = self.calc_bet_limit(m.equity, P, float(p.XMLEntriesList['c'].text))
        # print"CALL LIMIT: " + str(S)
        # print "implied EV: "+ str(np.round(d.CalculateEV(E,P,S,I,c,n),2))
        self.DeriveCallButtonFromBetButton = False
        try:
            t.minCall = float(t.currentCallValue)
        except:
            t.minCall = float(0.0)
            if t.checkButton == False:
                print("Failed to convert current Call value, saving error.png, deriving from bet value, result:")
                entireScreen = ImageGrab.grab()
                gui.statusbar.set("Writing error file...")
                entireScreen.save('pics/error.png', format='png')
                self.DeriveCallButtonFromBetButton = True
                t.minCall = np.round(float(t.get_current_bet_value()) / 2, 2)
                print(t.minCall)
                #        adjMinCall=minCall*c1*c2

        try:
            t.minBet = float(t.currentBetValue)
            t.opponentBetIncreases = t.minBet - h.myLastBet
        except:
            print("Betvalue not recognised!")
            gui.statusbar.set("Betvalue not regognised")
            t.minBet = float(100.0)
            t.opponentBetIncreases = 0

        self.potAdjustment = t.totalPotValue / bigBlind / 250 * float(p.XMLEntriesList['potAdjustment'].text)
        self.potAdjustment = min(self.potAdjustment, float(p.XMLEntriesList['maxPotAdjustment'].text))

        if t.gameStage == "PreFlop":
            power1 = float(p.XMLEntriesList['PreFlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XMLEntriesList['PreFlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "Flop":
            power1 = float(p.XMLEntriesList['FlopCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XMLEntriesList['FlopMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "Turn":
            power1 = float(p.XMLEntriesList['TurnCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XMLEntriesList['TurnMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1
        elif t.gameStage == "River":
            power1 = float(p.XMLEntriesList['RiverCallPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityCall = float(
                p.XMLEntriesList['RiverMinCallEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            minCallAmountIfAboveLimit = bigBlind * 2
            potStretch = 1
            maxEquityCall = 1

        maxValue = float(p.XMLEntriesList['initialFunds'].text) * potStretch
        d = Curvefitting(np.array([self.equity]), smallBlind, minCallAmountIfAboveLimit, maxValue, minEquityCall,
                         maxEquityCall, power1)
        self.maxCallE = round(d.y[0], 2)

        if t.gameStage == "PreFlop":
            power2 = float(p.XMLEntriesList['PreFlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XMLEntriesList['PreFlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = float(p.XMLEntriesList['PreFlopMaxBetEquity'].text)
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "Flop":
            power2 = float(p.XMLEntriesList['FlopBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XMLEntriesList['FlopMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "Turn":
            power2 = float(p.XMLEntriesList['TurnBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XMLEntriesList['TurnMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2
        elif t.gameStage == "River":
            power2 = float(p.XMLEntriesList['RiverBetPower'].text) + secondRoundAdjustmentPowerIncrease
            minEquityBet = float(
                p.XMLEntriesList['RiverMinBetEquity'].text) + self.secondRoundAdjustment - self.potAdjustment
            maxEquityBet = 1
            minBetAmountIfAboveLimit = bigBlind * 2

        maxValue = float(p.XMLEntriesList['initialFunds'].text) * potStretch
        d = Curvefitting(np.array([self.equity]), smallBlind, minBetAmountIfAboveLimit, maxValue, minEquityBet,
                         maxEquityBet, power2)
        self.maxBetE = round(d.y[0], 2)

        self.finalCallLimit = self.maxCallE  # min(self.maxCallE, self.maxCallEV)
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

        # --- start of decision making logic ---

        if self.equity >= float(p.XMLEntriesList['alwaysCallEquity'].text):
            self.finalCallLimit = 99999999

        if self.finalCallLimit < t.minCall:
            self.decision = "Fold"
        if self.finalCallLimit >= t.minCall:
            self.decision = "Call"
        if self.finalBetLimit >= t.minBet:
            self.decision = "Bet"
        if self.finalBetLimit >= (t.minBet + bigBlind * float(p.XMLEntriesList['BetPlusInc'].text)) and (
                    (t.gameStage == "Turn" and t.totalPotValue > bigBlind * 3) or t.gameStage == "River"):
            self.decision = "BetPlus"
        if (self.finalBetLimit >= float(t.totalPotValue) / 2) and (t.minBet < float(t.totalPotValue) / 2) and (
                    (t.minBet + bigBlind * float(p.XMLEntriesList['BetPlusInc'].text)) < float(
                    t.totalPotValue) / 2) and (
                    (t.gameStage == "Turn" and float(t.totalPotValue) / 2 < bigBlind * 20) or t.gameStage == "River"):
            self.decision = "Bet half pot"
        if (t.allInCallButton == False and self.equity >= float(p.XMLEntriesList['betPotRiverEquity'].text)) and (
                    t.minBet <= float(t.totalPotValue)) and t.gameStage == "River" and (
                    float(t.totalPotValue) < bigBlind * float(p.XMLEntriesList['betPotRiverEquityMaxBBM'].text)) and (
                    (t.minBet + bigBlind * float(p.XMLEntriesList['BetPlusInc'].text)) < float(t.totalPotValue)):
            self.decision = "Bet pot"

        if t.checkButton == False and t.minCall == 0.0:
            self.decision = "Fold"  # for cases where call button cannnot be read, not even after deriving from Bet Button
            self.ErrCallButton = True
        else:
            self.ErrCallButton = False

        if self.equity >= float(p.XMLEntriesList['FlopCheckDeceptionMinEquity'].text) and t.gameStage == "Flop" and (
                                    self.decision == "Bet" or self.decision == "BetPlus" or self.decision == "Bet half pot" or self.decision == "Bet pot" or self.decision == "Bet max"):
            self.UseFlopCheckDeception = True
            self.decision = "Call Deception"
        else:
            self.UseFlopCheckDeception = False

        if t.allInCallButton == False and self.equity >= float(p.XMLEntriesList[
                                                                   'secondRiverBetPotMinEquity'].text) and t.gameStage == "River" and h.histGameStage == "River":
            self.decision = "Bet pot"

        if t.checkButton == True:
            if self.decision == "Fold": self.decision = "Check"
            if self.decision == "Call": self.decision = "Check"
            if self.decision == "Call Deception": self.decision = "Check Deception"

        t.currentBluff = 0
        if t.isHeadsUp == True:
            if t.gameStage == "Flop" and t.PlayerPots == [] and self.equity > float(
                    p.XMLEntriesList['FlopBluffMinEquity'].text) and self.decision == "Check" and float(
                p.XMLEntriesList['FlopBluff'].text) > 0:
                t.currentBluff = float(p.XMLEntriesList['FlopBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "Turn" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XMLEntriesList['TurnBluff'].text) > 0 and self.equity > float(
                p.XMLEntriesList['TurnBluffMinEquity'].text):
                t.currentBluff = float(p.XMLEntriesList['TurnBluff'].text)
                self.decision = "Bet Bluff"
            elif t.gameStage == "River" and h.histPlayerPots == [] and t.PlayerPots == [] and self.decision == "Check" and float(
                    p.XMLEntriesList['RiverBluff'].text) > 0 and self.equity > float(
                p.XMLEntriesList['RiverBluffMinEquity'].text):
                t.currentBluff = float(p.XMLEntriesList['RiverBluff'].text)
                self.decision = "Bet Bluff"

        # bullyMode
        if t.isHeadsUp:
            try:
                opponentFunds = min(t.PlayerFunds)
            except:
                opponentFunds = float(p.XMLEntriesList['initialFunds'].text)

            self.bullyMode = opponentFunds < float(p.XMLEntriesList['initialFunds'].text) / float(
                p.XMLEntriesList['bullyDivider'].text)

            if (m.equity >= float(p.XMLEntriesList['minBullyEquity'].text)) and (
                        m.equity <= float(p.XMLEntriesList['maxBullyEquity'].text)) and self.bullyMode:
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
        if self.decision == "BetPlus": h.myLastBet = t.minBet * float(p.XMLEntriesList['BetPlusInc'].text) + t.minBet
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
        mouse.MouseAction(self.decision)

class Table(object):
    # baseclass that is inherited by the different types of Tables (e.g. Pokerstars of Party Poker Table)
    def call_genetic_algorithm(self):
        gui.statusbar.set("Checking for AI update")
        n = L.get_game_count(p.current_strategy.text)
        lg = int(
            p.XML_entries_list1['considerLastGames'].text)  # only consider lg last games to see if there was a loss
        f = L.get_strategy_total_funds_change(p.current_strategy.text, lg)
        gui.var6.set("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))
        if n % int(p.XML_entries_list1['strategyIterationGames'].text) == 0 and f < float(
                p.XML_entries_list1['minimumLossForIteration'].text):
            pass
            gui.statusbar.set("***Improving current strategy***")
            winsound.Beep(500, 100)
            Genetic_Algorithm(True)
            p.read_XML()

    def crop_image(self, original, left, top, right, bottom):
        # original.show()
        width, height = original.size  # Get dimensions
        cropped_example = original.crop((left, top, right, bottom))
        # cropped_example.show()
        return cropped_example

class TablePS(Table):
    def get_top_left_corner(self, scraped):
        img = cv2.cvtColor(np.array(a.entireScreenPIL), cv2.COLOR_BGR2RGB)

        template = scraped.topLeftCorner

        method = eval('cv2.TM_SQDIFF_NORMED')
        res = cv2.matchTemplate(img, template, method)
        threshold = 0.01
        loc = np.where(res <= threshold)
        topleftcorner_temp = []
        self.topleftcorner = []

        c = 0
        for pt in zip(*loc[::-1]):
            c += 1
            if c > 1:
                print("multiple windows found")
                break  # only handle one table

            topleftcorner_temp = pt

        # plt.subplot(121),plt.imshow(res,cmap = 'jet')
        #        plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
        #        plt.subplot(122),plt.imshow(img,cmap = 'jet')
        #        plt.title('Detected Point'), plt.xticks([]), plt.yticks([])
        #        plt.suptitle(method)
        #        plt.show()
        # print self.topleftcorner
        if len(topleftcorner_temp) == 2:
            self.topleftcorner.append(topleftcorner_temp[0] - 7)
            self.topleftcorner.append(topleftcorner_temp[1] - 32)
            # print self.topleftcorner
            return True
        else:
            gui.statusbar.set("Pokerstars not found yet")
            time.sleep(1)
            return False

    def check_for_button(self, scraped):
        cards = ' '.join(t.mycards)
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 570, self.topleftcorner[1] + 376,
                                    self.topleftcorner[0] + 900, self.topleftcorner[1] + 580)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.button, img, 0.05)

        if count > 0:
            gui.statusbar.set("Buttons found, preparing Montecarlo with: " + str(cards))
            return True

        else:
            # sprint "No Buttons"
            return False

    def check_for_checkbutton(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 370, self.topleftcorner[1] + 376,
                                    self.topleftcorner[0] + 900, self.topleftcorner[1] + 580)
        # pil_image.save("pics/getCheckButton.png")
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.check, img, 0.01)

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            # print "check button found"
        else:
            self.checkButton = False
            # print "check button not found"
        # print "Check: " + str(self.checkButton)
        return True

    def check_for_captcha(self):
        ChatWindow = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 7, self.topleftcorner[1] + 490,
                                     self.topleftcorner[0] + 345, self.topleftcorner[1] + 550)
        basewidth = 500
        wpercent = (basewidth / float(ChatWindow.size[0]))
        hsize = int((float(ChatWindow.size[1]) * float(wpercent)))
        ChatWindow = ChatWindow.resize((basewidth, hsize), Image.ANTIALIAS)
        # ChatWindow.show()
        try:
            t.chatText = (pytesseract.image_to_string(ChatWindow, None, False, "-psm 6"))
            t.chatText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]", "", t.chatText)
            keyword1 = 'disp'
            keyword2 = 'left'
            keyword3 = 'pic'
            keyword4 = 'key'
            keyword5 = 'lete'
            # print (recognizedText)
            if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2) > 0) or (
                        t.chatText.find(keyword3) > 0) or (t.chatText.find(keyword4) > 0) or (
                        t.chatText.find(keyword5) > 0)):
                gui.statusbar.set("Captcha discovered! Submitting...")
                captchaIMG = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 5, self.topleftcorner[1] + 490,
                                             self.topleftcorner[0] + 335, self.topleftcorner[1] + 550)
                captchaIMG.save("pics/captcha.png")
                # captchaIMG.show()
                time.sleep(0.5)
                t.captcha = solveCaptcha("pics/captcha.png")
                mouse.EnterCaptcha(t.captcha)
                print("Entered captcha")
                print(t.captcha)
        except:
            print("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 550, self.topleftcorner[1] + 456,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.ImBack, img, 0.01)
        if count > 0:
            mouse.MouseAction("Imback")
            return False
            gui.statusbar.set("I am back found")
        else:
            return True

    def check_for_call(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 370, self.topleftcorner[1] + 376,
                                    self.topleftcorner[0] + 900, self.topleftcorner[1] + 580)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.call, img, 0.05)
        if count > 0:
            self.callButton = True
        else:
            self.callButton = False
        return True

    def check_for_allincall_button(self, scraped):

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 650, self.topleftcorner[1] + 376,
                                    self.topleftcorner[0] + 900, self.topleftcorner[1] + 580)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
        else:
            self.allInCallButton = False

        return True

    def get_deck_cards(self, scraped):
        self.cardsOnTable = []
        pil_image = self.crop_image(a.entireScreenPIL, t.topleftcorner[0] + 250, t.topleftcorner[1] + 200,
                                    t.topleftcorner[0] + 550, t.topleftcorner[1] + 280)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value

            method = eval('cv2.TM_SQDIFF_NORMED')

            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.0001:
                self.cardsOnTable.append(key)
            if len(self.cardsOnTable) < 1:
                self.gameStage = "PreFlop"
            elif len(self.cardsOnTable) == 3:
                self.gameStage = "Flop"
            elif len(self.cardsOnTable) == 4:
                self.gameStage = "Turn"
            elif len(self.cardsOnTable) == 5:
                self.gameStage = "River"

        return True

    def get_my_cards(self, scraped):
        self.mycards = []
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 340, self.topleftcorner[1] + 350,
                                    self.topleftcorner[0] + 430, self.topleftcorner[1] + 420)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value
            method = eval('cv2.TM_SQDIFF_NORMED')
            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.01:
                # print files+" found", min_val, max_val, min_loc, max_loc
                self.mycards.append(key)
        if len(self.mycards) == 2:
            t.myFundsChange = float(t.myFunds) - float(str(h.myFundsHistory[-1]).strip('[]'))
            return True
        else:
            # print (self.mycards)
            return False

    def get_covered_card_holders(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)

        template = scraped.coveredCardHolder
        # w, h = template.shape[::-1]
        method = eval('cv2.TM_SQDIFF_NORMED')

        # Apply template Matching
        res = cv2.matchTemplate(img, template, method)

        threshold = 0.001
        loc = np.where(res <= threshold)
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        PlayerCoordinates = []
        t.PlayerNames = []

        playerNameImage = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 336, self.topleftcorner[1] + 418,
                                          self.topleftcorner[0] + 428, self.topleftcorner[1] + 434)
        # playerNameImage.show()
        recognizedText = (
            pytesseract.image_to_string(playerNameImage, None, False, "-psm 6").replace(" ", "").replace("$",
                                                                                                         "").replace(
                "!", "").replace(")", "").replace("}", "").replace(":", "").replace(":", "").replace("]", ""))
        recognizedText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]", "",
                                recognizedText)
        t.PlayerNames.append(recognizedText)

        count = 0
        for pt in zip(*loc[::-1]):
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            if count % 2 == 0:
                playerNameImage = pil_image.crop((pt[0] - 27, pt[1] + 30, pt[0] + 65, pt[1] + 50))
                basewidth = 500
                wpercent = (basewidth / float(playerNameImage.size[0]))
                hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
                playerNameImage = playerNameImage.resize((basewidth, hsize), Image.ANTIALIAS)
                # playerNameImage.show()
                try:
                    recognizedText = (pytesseract.image_to_string(playerNameImage, None, False, "-psm 6"))
                    recognizedText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789]", "",
                                            recognizedText)
                    t.PlayerNames.append(recognizedText)
                except:
                    print("Pyteseract error in player name recognition")
        # print (t.PlayerNames)

        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        self.coveredCardHolders = np.round(count / 2)

        # print self.coveredCardHolders

        if self.coveredCardHolders == 1:
            self.isHeadsUp = True
            # print "HeadSUP!"
        else:
            self.isHeadsUp = False

        if self.coveredCardHolders > 0:
            return True
        else:
            print("No other players found. Assuming 1 player")
            self.coveredCardHolders = 1
            return True

    def get_played_players(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)

        im = pil_image
        x, y = im.size
        eX, eY = 280, 140  # Size of Bounding Box for ellipse

        bbox = (x / 2 - eX / 2, y / 2 - eY / 2, x / 2 + eX / 2, y / 2 + eY / 2)
        draw = ImageDraw.Draw(im)
        draw.ellipse(bbox, fill=128)
        del draw
        # im.show()
        pil_image_ellipsed = im

        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image_ellipsed), cv2.COLOR_BGR2RGB)
        template = scraped.smallDollarSign1
        # w, h = template.shape[::-1]
        method = eval('cv2.TM_SQDIFF_NORMED')
        # Apply template Matching
        res = cv2.matchTemplate(img, template, method)
        threshold = 0.01
        loc = np.where(res <= threshold)
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        count = 0
        self.iAmBigBLind = False
        self.PlayerPots = []
        for pt in zip(*loc[::-1]):
            x = pt[0] + 9
            y = pt[1] - 2
            modpt = (x, y)
            w = 40
            h = 17
            cv2.rectangle(img, modpt, (x + w, y + h), (0, 0, 255), 2)
            # cv2.imshow("Image",img)
            count += 1
            playerPotImage = pil_image_ellipsed.crop((pt[0], pt[1], pt[0] + w, pt[1] + h))
            recognizedText = (
                pytesseract.image_to_string(playerPotImage, None, False, "-psm 6").replace(" ", "").replace("$",
                                                                                                            "").replace(
                    "!",
                    "").replace(
                    ")", "").replace("}", "").replace(":", "").replace(":", "").replace("]", ""))
            recognizedText = re.sub("[^0123456789.]", "", recognizedText)
            if pt == (393, 331) and recognizedText == str(
                    float(p.XML_entries_list1['p.bigBlind'].text)): self.iAmBigBLind = True
            if recognizedText != "":
                self.PlayerPots.append(recognizedText)

        self.PlayerPots.sort()

        try:
            t = [float(x) for x in self.PlayerPots]
            self.playerBetIncreases = [t[i + 1] - t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncrease = max(self.playerBetIncreases)

            self.playerBetIncreasesAsPotPercentage = [(x / self.totalPotValue) for x in self.playerBetIncreases]
            self.maxPlayerBetIncreasesAsPotPercentage = max(self.playerBetIncreasesAsPotPercentage)
        except:  # when no other players are around (avoid division by zero)
            self.maxPlayerBetIncrease = 0
            self.playerBetIncreasesAsPotPercentage = [0]
            self.maxPlayerBetIncreasesAsPotPercentage = 0

        try:
            self.playerBetIncreasesPercentage = [t[i + 1] / t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncreasesPercentage = max(self.playerBetIncreasesPercentage)

            # print "Player Pots:           " + str(self.PlayerPots)
            # print "Player Pots increases: " + str(self.playerBetIncreases)
            # print "Player increase as %:  " + str(self.playerBetIncreasesPercentage)

        except:
            self.playerBetIncreasesPercentage = [0]
            self.maxPlayerBetIncreasesPercentage = 0

        if self.isHeadsUp == True:
            try:
                self.maxPlayerBetIncreasesPercentage = (self.totalPotValue - h.previousPot - h.myLastBet) / h.myLastBet
                self.maxPlayerBetIncrease = (self.totalPotValue - h.previousPot - h.myLastBet) - h.myLastBet
                print("Remembering last bet: " + str(self.myLastBet))
            except:
                # print ("Not remembering last bet")
                self.maxPlayerBetIncreasesPercentage = 0
                self.maxPlayerBetIncrease = 0

        # raw_input("Press Enter to continue...")
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()


        self.playersBehind = count

        if self.iAmBigBLind == True: self.playersBehind -= 1

        self.playersAhead = int(np.round(self.coveredCardHolders - self.playersBehind))
        # print (self.PlayerPots)

        if str(p.smallBlind) in self.PlayerPots:
            self.playersAhead += 1
            self.playersBehind = 1
            # print ("Found small blind")

        self.playersAhead = int(max(self.playersAhead, 0))
        # print ("Played players: " + str(self.playersBehind))

        return True

    def get_total_pot_value(self):
        returnvalue = True
        x1 = 409
        y1 = 186
        x2 = 470
        y2 = 200
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$", "")
        try:
            self.totalPotValue = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            print("unable to get pot value")
            pil_image.save("pics/ErrPotValue.png")
            returnvalue = False
        return returnvalue

    def get_my_funds(self):
        returnvalue = True
        if p.TableType.text == "Zoom":
            x1 = 372
            y1 = 440
            x2 = 421
            y2 = 454
        elif p.TableType.text == "Cash":
            x1 = 405
            y1 = 430
            x2 = 450
            y2 = 454
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()

        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$", "")
        self.myFundsError = False

        # pil_image.show()
        try:
            pil_image.save("pics/myFunds.png")
        except:
            print("Could not save myFunds.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)


        try:
            self.myFunds = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            print("myFunds not regognised!")
            gui.statusbar.set("!!Funds NOT recognised!!")
            time.sleep(0.5)
        return True

    def get_current_call_value(self):
        x1 = 575
        y1 = 545
        x2 = 665
        y2 = 565

        if self.allInCallButton == True:
            x1 = 710
            x2 = 770

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        # pil_image.save("pics/currentCallValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        if t.checkButton == False:
            recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$",
                                                                                                                    "")
            try:
                self.currentCallValue = float(re.sub("[^0123456789\.]", "", recognizedText))
                self.getCallButtonValueSuccess = True
                if self.allInCallButton == True and self.myFundsError == False and self.currentCallValue < self.myFunds:
                    self.getCallButtonValueSuccess = False
                    pil_image.save("pics/ErrCallValue.png")
                    self.currentCallValue = self.myFunds

            except:
                self.currentCallValue = "error"
                self.getCallButtonValueSuccess = False
                pil_image.save("pics/ErrCallValue.png")

        # if len(self.currentRoundPotValue)>0: return True
        # else: return False

        return True

    def get_current_bet_value(self):
        x1 = 710
        y1 = 547
        x2 = 770
        y2 = 566

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        # pil_image.save("pics/currentBetValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$", "")
        try:
            self.currentBetValue = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            returnvalue = False
            self.currentBetValue = 9999999.0

        return True

    def get_current_pot_value(self):
        x1 = 390
        y1 = 324
        x2 = 431
        y2 = 340
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        pil_image.save("pics/currenPotValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        self.currentRoundPotValue = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ",
                                                                                                          "").replace(
            "$", "")
        if len(self.currentRoundPotValue) > 6: self.currentRoundPotValue = ""
        # else: return False

        return True

    def get_new_hand(self):
        if h.previousCards != t.mycards:
            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            L.mark_last_game(t, h)

            self.call_genetic_algorithm()

            cards = ' '.join(t.mycards)
            gui.statusbar.set("New hand: " + str(cards))

            if gui.active == True:
                gui.y.append(t.myFunds)
                gui.line1.set_ydata(gui.y[-100:])
                maxh = max(gui.y)
                gui.a.set_ylim(0, max(6, maxh))
                gui.f.canvas.draw()

            if gui.active == True:
                data = L.get_stacked_bar_data('Template', p.current_strategy.text, 'stackedBar')
                maxh = float(p.XML_entries_list1['bigBlind'].text) * 10
                i = 0
                for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(gui.p0.patches, gui.p1.patches,
                                                                           gui.p2.patches,
                                                                           gui.p3.patches, gui.p4.patches,
                                                                           gui.p5.patches, gui.p6.patches):
                    g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
                    height = g[i]
                    i += 1
                    rect0.set_height(height[0])
                    rect1.set_y(height[0])
                    rect1.set_height(height[1])
                    rect2.set_y(height[0] + height[1])
                    rect2.set_height(height[2])
                    rect3.set_y(height[0] + height[1] + height[2])
                    rect3.set_height(height[3])
                    rect4.set_y(height[0] + height[1] + height[2] + height[3])
                    rect4.set_height(height[4])
                    rect5.set_y(height[0] + height[1] + height[2] + height[3] + height[4])
                    rect5.set_height(height[5])
                    rect6.set_y(height[0] + height[1] + height[2] + height[3] + height[4] + height[5])
                    rect6.set_height(height[6])
                    maxh = max(height[0] + height[1] + height[2] + height[3] + height[4] + height[5] + height[6], maxh)
                # canvas = FigureCanvasTkAgg(gui.h, master=gui.root)

                gui.c.set_ylim((0, maxh))
                gui.h.canvas.draw()
                # canvas.get_tk_widget().grid(row=6, column=1)

            h.myLastBet = 0
            h.myFundsHistory.append(str(t.myFunds))
            h.previousCards = t.mycards
            h.lastSecondRoundAdjustment = 0

            a.take_screenshot()

        return True

class TablePP(Table):
    def get_top_left_corner(self, scraped):
        img = cv2.cvtColor(np.array(a.entireScreenPIL), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.topLeftCorner, img, 0.01)
        if count == 1:
            self.topleftcorner = points[0]
            return True
        else:
            gui.statusbar.set(p.XML_entries_list1['pokerSite'].text + " not found yet")
            time.sleep(1)
            return False

    def check_for_button(self, scraped):
        cards = ' '.join(t.mycards)
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 540, self.topleftcorner[1] + 480,
                                    self.topleftcorner[0] + 700, self.topleftcorner[1] + 580)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.button, img, 0.01)

        if count > 0:
            gui.statusbar.set("Buttons found, preparing Montecarlo with: " + str(cards))
            return True

        else:
            # sprint "No Buttons"
            return False

    def check_for_checkbutton(self, scraped):
        gui.statusbar.set("Check for Check")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 560, self.topleftcorner[1] + 478,
                                    self.topleftcorner[0] + 670, self.topleftcorner[1] + 550)
        # pil_image.save("pics/getCheckButton.png")
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.check, img, 0.01)

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            # print "check button found"
        else:
            self.checkButton = False
            # print "check button not found"
        # print "Check: " + str(self.checkButton)
        return True

    def check_for_captcha(self):
        # ChatWindow = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 3, self.topleftcorner[1] + 443,
        #                             self.topleftcorner[0] + 400, self.topleftcorner[1] + 443 + 90)
        # basewidth = 500
        # wpercent = (basewidth / float(ChatWindow.size[0]))
        # hsize = int((float(ChatWindow.size[1]) * float(wpercent)))
        # ChatWindow = ChatWindow.resize((basewidth, hsize), Image.ANTIALIAS)
        # # ChatWindow.show()
        # try:
        #     t.chatText = (pytesseract.image_to_string(ChatWindow, None, False, "-psm 6"))
        #     t.chatText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]", "", t.chatText)
        #     keyword1 = 'disp'
        #     keyword2 = 'left'
        #     keyword3 = 'pic'
        #     keyword4 = 'key'
        #     keyword5 = 'lete'
        #     # print (recognizedText)
        #     if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2) > 0) or (
        #                 t.chatText.find(keyword3) > 0) or (t.chatText.find(keyword4) > 0) or (
        #                 t.chatText.find(keyword5) > 0)):
        #         gui.statusbar.set("Captcha discovered! Submitting...")
        #         captchaIMG = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 5, self.topleftcorner[1] + 490,
        #                                     self.topleftcorner[0] + 335, self.topleftcorner[1] + 550)
        #         captchaIMG.save("pics/captcha.png")
        #         # captchaIMG.show()
        #         time.sleep(0.5)
        #         t.captcha = solveCaptcha("pics/captcha.png")
        #         mouse.EnterCaptcha(t.captcha)
        #         print("Entered captcha")
        #         print(t.captcha)
        # except:
        #     print("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 402, self.topleftcorner[1] + 458,
                                    self.topleftcorner[0] + 442 + 400, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.ImBack, img, 0.08)
        if count > 0:
            mouse.MouseAction("Imback")
            return False
            gui.statusbar.set("I am back found")
        else:
            return True

    def check_for_call(self, scraped):
        gui.statusbar.set("Check for Call")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 575, self.topleftcorner[1] + 483,
                                    self.topleftcorner[0] + 575 + 100, self.topleftcorner[1] + 483 + 100)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.call, img, 0.01)
        if count > 0:
            self.callButton = True
        else:
            self.callButton = False
        return True

    def check_for_allincall_button(self, scraped):
        gui.statusbar.set("Check for All in")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 557, self.topleftcorner[1] + 493,
                                    self.topleftcorner[0] + 670, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
        else:
            self.allInCallButton = False

        return True

    def get_deck_cards(self, scraped):
        gui.statusbar.set("Get Deck cards")
        self.cardsOnTable = []
        pil_image = self.crop_image(a.entireScreenPIL, t.topleftcorner[0] + 206, t.topleftcorner[1] + 158,
                                    t.topleftcorner[0] + 600, t.topleftcorner[1] + 158 + 120)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value

            method = eval('cv2.TM_SQDIFF_NORMED')

            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.01:
                self.cardsOnTable.append(key)
            if len(self.cardsOnTable) < 1:
                self.gameStage = "PreFlop"
            elif len(self.cardsOnTable) == 3:
                self.gameStage = "Flop"
            elif len(self.cardsOnTable) == 4:
                self.gameStage = "Turn"
            elif len(self.cardsOnTable) == 5:
                self.gameStage = "River"

        return True

    def get_my_cards(self, scraped):
        self.mycards = []
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 450, self.topleftcorner[1] + 330,
                                    self.topleftcorner[0] + 450 + 80, self.topleftcorner[1] + 330 + 80)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value
            method = eval('cv2.TM_SQDIFF_NORMED')
            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.01:
                # print files+" found", min_val, max_val, min_loc, max_loc
                self.mycards.append(key)
        if len(self.mycards) == 2:
            t.myFundsChange = float(t.myFunds) - float(str(h.myFundsHistory[-1]).strip('[]'))
            return True
        else:
            # print (self.mycards)
            return False

    def get_covered_card_holders(self, scraped):
        gui.statusbar.set("Analyse other players and position")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.coveredCardHolder, img, 0.0001)
        t.PlayerNames = []
        t.PlayerFunds = []

        t.PlayerNames.append("Myself")
        count = 0
        for pt in points:
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            playerNameImage = pil_image.crop(
                (pt[0] - (955 - 890), pt[1] + 270 - 222, pt[0] + 20, pt[1] + +280 - 222))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerNameImage = playerNameImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerNameImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerNameImage, None, False, "-psm 6"))
                recognizedText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789]", "",
                                        recognizedText)
                t.PlayerNames.append(recognizedText)
            except:
                print("Pyteseract error in player name recognition")

            playerFundsImage = pil_image.crop(
                (pt[0] - (955 - 890) + 10, pt[1] + 270 - 222 + 20, pt[0] + 10, pt[1] + +280 - 222 + 22))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerFundsImage = playerFundsImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerFundsImage = playerFundsImage.filter(ImageFilter.MaxFilter)
            # playerFundsImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerFundsImage, None, False, "-psm 6")).replace("-",
                                                                                                                ".")
                recognizedText = re.sub("[^0123456789.]", "",
                                        recognizedText)
                t.PlayerFunds.append(float(recognizedText))
            except:
                print("Pyteseract error in player name recognition")

        # print (t.PlayerNames)

        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        self.coveredCardHolders = np.round(count)

        # print self.coveredCardHolders

        if self.coveredCardHolders == 1:
            self.isHeadsUp = True
            # print "HeadSUP!"
        else:
            self.isHeadsUp = False

        if self.coveredCardHolders > 0:
            return True
        else:
            print("No other players found. Assuming 1 player")
            self.coveredCardHolders = 1
            return True

    def get_played_players(self, scraped):
        gui.statusbar.set("Analyse past players")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)

        im = pil_image
        x, y = im.size
        eX, eY = 280, 150  # Size of Bounding Box for ellipse

        bbox = (x / 2 - eX / 2, y / 2 - eY / 2, x / 2 + eX / 2, y / 2 + eY / 2 - 20)
        rectangle1 = (0, 0, 800, 130)
        rectangle2 = (0, 380, 800, 499)
        rectangle3 = (0, 1, 110, 499)
        rectangle4 = (690, 1, 800, 499)
        rectangle5 = (400, 300, 500, 400)
        draw = ImageDraw.Draw(im)
        draw.ellipse(bbox, fill=128)
        draw.rectangle(rectangle1, fill=128)
        draw.rectangle(rectangle2, fill=128)
        draw.rectangle(rectangle3, fill=128)
        draw.rectangle(rectangle4, fill=128)
        draw.rectangle(rectangle5, fill=128)
        del draw
        # im.show()
        pil_image_ellipsed = im

        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image_ellipsed), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.smallDollarSign1, img, 0.05)

        self.PlayerPots = []
        for pt in points:
            x = pt[0] + 9
            y = pt[1] + 1
            modpt = (x, y)
            w = 40
            h = 15
            cv2.rectangle(img, modpt, (x + w, y + h), (0, 0, 255), 2)
            # cv2.imshow("Image",img)
            playerPotImage = pil_image_ellipsed.crop((x, y, x + w, y + h))

            basewidth = 100
            wpercent = (basewidth / float(playerPotImage.size[0]))
            hsize = int((float(playerPotImage.size[1]) * float(wpercent)))
            playerPotImage = playerPotImage.resize((basewidth, hsize), Image.ANTIALIAS)

            playerPotImage = playerPotImage.filter(ImageFilter.MinFilter)

            recognizedText = pytesseract.image_to_string(playerPotImage, None, False, "-psm 6")
            recognizedText = re.sub("[^0123456789.]", "", recognizedText)
            if recognizedText != "":
                self.PlayerPots.append(recognizedText)

        self.PlayerPots.sort()

        try:
            t = [float(x) for x in self.PlayerPots]
            self.playerBetIncreases = [t[i + 1] - t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncrease = max(self.playerBetIncreases)

            self.playerBetIncreasesAsPotPercentage = [(x / self.totalPotValue) for x in self.playerBetIncreases]
            self.maxPlayerBetIncreasesAsPotPercentage = max(self.playerBetIncreasesAsPotPercentage)
        except:  # when no other players are around (avoid division by zero)
            self.maxPlayerBetIncrease = 0
            self.playerBetIncreasesAsPotPercentage = [0]
            self.maxPlayerBetIncreasesAsPotPercentage = 0

        try:
            self.playerBetIncreasesPercentage = [t[i + 1] / t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncreasesPercentage = max(self.playerBetIncreasesPercentage)

            # print "Player Pots:           " + str(self.PlayerPots)
            # print "Player Pots increases: " + str(self.playerBetIncreases)
            # print "Player increase as %:  " + str(self.playerBetIncreasesPercentage)

        except:
            self.playerBetIncreasesPercentage = [0]
            self.maxPlayerBetIncreasesPercentage = 0

        if self.isHeadsUp == True:
            try:
                self.maxPlayerBetIncreasesPercentage = (self.totalPotValue - h.previousPot - h.myLastBet) / h.myLastBet
                self.maxPlayerBetIncrease = (self.totalPotValue - h.previousPot - h.myLastBet) - h.myLastBet
                print("Remembering last bet: " + str(self.myLastBet))
            except:
                # print ("Not remembering last bet")
                self.maxPlayerBetIncreasesPercentage = 0
                self.maxPlayerBetIncrease = 0

        # raw_input("Press Enter to continue...")
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()


        self.playersBehind = count

        self.playersAhead = int(np.round(self.coveredCardHolders - self.playersBehind))
        # print (self.PlayerPots)

        if p.XML_entries_list1['smallBlind'].text in self.PlayerPots:
            self.playersAhead += 1
            self.playersBehind -= 1
            # print ("Found small blind")

        self.playersAhead = int(max(self.playersAhead, 0))
        # print ("Played players: " + str(self.playersBehind))

        return True

    def get_total_pot_value(self):
        gui.statusbar.set("Get Pot Value")
        returnvalue = True
        x1 = 385
        y1 = 120
        x2 = 430
        y2 = 131
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 200
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        pil_image_min = pil_image.filter(ImageFilter.MinFilter)
        pil_image_median = pil_image.filter(ImageFilter.MedianFilter)
        pil_image_mode = pil_image.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)

        try:
            recognizedText1 = pytesseract.image_to_string(
                pil_image.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN), None, False, "-psm 6").replace(
                "I", "1").replace("O", "0").replace("o", "0").replace("-", ".")
            self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText1)
            if self.totalPotValue[0] == ".": self.totalPotValue = self.totalPotValue[1:]
            # if self.totalPotValue == "":
            #     self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText2)
            #     if self.totalPotValue == "":
            #         self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText3)
            # if self.totalPotValue[0] == ".": self.totalPotValue = self.totalPotValue[1:]
            self.totalPotValue = float(float(self.totalPotValue))

        except:
            print("unable to get pot value")
            gui.statusbar.set("Unable to get pot value")
            time.sleep(1)
            pil_image.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        if self.totalPotValue < 0.01:
            print("unable to get pot value")
            gui.statusbar.set("Unable to get pot value")
            time.sleep(1)
            pil_image.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        return True

    def get_my_funds(self):
        x1 = 469
        y1 = 403
        x2 = 469 + 38
        y2 = 403 + 11
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 200
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
        pil_image_filtered = pil_image.filter(ImageFilter.ModeFilter)
        pil_image_filtered2 = pil_image.filter(ImageFilter.MedianFilter)
        self.myFundsError = False

        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace("I", "1").replace("O",
                                                                                                                 "0").replace(
            "o", "0")
        if recognizedText == "":
            recognizedText = pytesseract.image_to_string(pil_image_filtered, None, False, "-psm 6").replace("I",
                                                                                                            "1").replace(
                "O", "0").replace("o", "0")
            if recognizedText == "":
                recognizedText = pytesseract.image_to_string(pil_image_filtered2, None, False, "-psm 6").replace("I",
                                                                                                                 "1").replace(
                    "O", "0").replace("o", "0")
        # pil_image.show()
        try:
            pil_image.save("pics/myFunds.png")
        except:
            print("Could not save myFunds.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)


        try:
            if recognizedText[0] == ".": recognizedText = recognizedText[1:]
            self.myFunds = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            print("myFunds not regognised!")
            gui.statusbar.set("!!Funds NOT recognised!!")
            a.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)
        return True

    def get_current_call_value(self):
        gui.statusbar.set("Get Call value")
        x1 = 590
        y1 = 511
        x2 = 590 + 50
        y2 = 511 + 14

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 100
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        pil_image = pil_image.filter(ImageFilter.ModeFilter)

        if t.checkButton == False:
            recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ",
                                                                                                   "").replace(
                "$", "")
            try:
                self.currentCallValue = float(re.sub("[^0123456789\.]", "", recognizedText))
                self.getCallButtonValueSuccess = True
                if self.allInCallButton == True and self.myFundsError == False and self.currentCallValue < self.myFunds:
                    self.getCallButtonValueSuccess = False
                    pil_image.save("pics/ErrCallValue.png")
                    self.currentCallValue = self.myFunds
            except:
                self.currentCallValue = 0
                self.CallValueReadError = True
                pil_image.save("pics/ErrCallValue.png")

        # if len(self.currentRoundPotValue)>0: return True
        # else: return False

        return True

    def get_current_bet_value(self):
        gui.statusbar.set("Get Bet Value")
        x1 = 590 + 125
        y1 = 511
        x2 = 590 + 50 + 125
        y2 = 511 + 14

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        basewidth = 100
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
        pil_image = pil_image.filter(ImageFilter.MedianFilter)

        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6 digits").replace(" ", "").replace(
            "$", "")
        try:
            self.currentBetValue = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            returnvalue = False
            self.currentBetValue = 9999999.0

        if self.currentBetValue < self.currentCallValue:
            self.currentCallValue = self.currentBetValue / 2
            self.BetValueReadError = True
            a.entireScreenPIL.save("pics/BetValueError.png")

        return True

    def get_current_pot_value(self):
        x1 = 390
        y1 = 324
        x2 = 431
        y2 = 340
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        pil_image.save("pics/currenPotValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        self.currentRoundPotValue = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ",
                                                                                                          "").replace(
            "$", "")
        if len(self.currentRoundPotValue) > 6: self.currentRoundPotValue = ""
        # else: return False

        return True

    def get_lost_everything(self, scraped):
        x1 = 100
        y1 = 100
        x2 = 590 + 50 + 125
        y2 = 511 + 14
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.lostEverything, img, 0.001)

        if count > 0:
            h.lastGameID = str(h.GameID)
            t.myFundsChange = float(0) - float(str(h.myFundsHistory[-1]).strip('[]'))
            L.mark_last_game(t, h)
            gui.statusbar.set("Everything is lost. Last game has been marked.")
            user_input = input("Press Enter for exit ")
            sys.exit()
        else:
            return True

    def get_new_hand(self):
        if h.previousCards != t.mycards:
            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            cards = ' '.join(t.mycards)
            gui.statusbar.set("New hand: " + str(cards))
            L.mark_last_game(t, h)

            self.call_genetic_algorithm()

            if gui.active == True:
                gui.y.append(t.myFunds)
                gui.line1.set_ydata(gui.y[-100:])
                gui.f.canvas.draw()

                maxh = max(gui.y)
                gui.a.set_ylim(0, max(6, maxh))
                gui.f.canvas.draw()

            if gui.active == True:
                data = L.get_stacked_bar_data('Template', p.current_strategy.text, 'stackedBar')
                maxh = float(p.XML_entries_list1['bigBlind'].text) * 10
                i = 0
                for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(gui.p0.patches, gui.p1.patches,
                                                                           gui.p2.patches,
                                                                           gui.p3.patches, gui.p4.patches,
                                                                           gui.p5.patches, gui.p6.patches):
                    g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
                    height = g[i]
                    i += 1
                    rect0.set_height(height[0])
                    rect1.set_y(height[0])
                    rect1.set_height(height[1])
                    rect2.set_y(height[0] + height[1])
                    rect2.set_height(height[2])
                    rect3.set_y(height[0] + height[1] + height[2])
                    rect3.set_height(height[3])
                    rect4.set_y(height[0] + height[1] + height[2] + height[3])
                    rect4.set_height(height[4])
                    rect5.set_y(height[0] + height[1] + height[2] + height[3] + height[4])
                    rect5.set_height(height[5])
                    rect6.set_y(height[0] + height[1] + height[2] + height[3] + height[4] + height[5])
                    rect6.set_height(height[6])
                    maxh = max(height[0] + height[1] + height[2] + height[3] + height[4] + height[5] + height[6], maxh)
                # canvas = FigureCanvasTkAgg(gui.h, master=gui.root)

                gui.c.set_ylim((0, maxh))
                gui.h.canvas.draw()
                # canvas.get_tk_widget().grid(row=6, column=1)

            h.myLastBet = 0
            h.myFundsHistory.append(str(t.myFunds))
            h.previousCards = t.mycards
            h.lastSecondRoundAdjustment = 0

            a.take_screenshot()

        return True

class TableF1(Table):
    def get_top_left_corner(self, scraped):
        img = cv2.cvtColor(np.array(a.entireScreenPIL), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.topLeftCorner, img, 0.01)
        if count == 1:
            self.topleftcorner = points[0]
            return True
        else:
            gui.statusbar.set(p.XML_entries_list1['pokerSite'].text + " not found yet")
            time.sleep(1)
            return False

    def check_for_button(self, scraped):
        cards = ' '.join(t.mycards)
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 540, self.topleftcorner[1] + 480,
                                   self.topleftcorner[0] + 700, self.topleftcorner[1] + 580)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.button, img, 0.01)

        if count > 0:
            gui.statusbar.set("Buttons found, preparing Montecarlo with: " + str(cards))
            return True

        else:
            # sprint "No Buttons"
            return False

    def check_for_checkbutton(self, scraped):
        gui.statusbar.set("Check for Check")
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 560, self.topleftcorner[1] + 478,
                                   self.topleftcorner[0] + 670, self.topleftcorner[1] + 550)
        # pil_image.save("pics/getCheckButton.png")
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.check, img, 0.01)

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            # print "check button found"
        else:
            self.checkButton = False
            # print "check button not found"
        # print "Check: " + str(self.checkButton)
        return True

    def check_for_captcha(self):
        # ChatWindow = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 3, self.topleftcorner[1] + 443,
        #                             self.topleftcorner[0] + 400, self.topleftcorner[1] + 443 + 90)
        # basewidth = 500
        # wpercent = (basewidth / float(ChatWindow.size[0]))
        # hsize = int((float(ChatWindow.size[1]) * float(wpercent)))
        # ChatWindow = ChatWindow.resize((basewidth, hsize), Image.ANTIALIAS)
        # # ChatWindow.show()
        # try:
        #     t.chatText = (pytesseract.image_to_string(ChatWindow, None, False, "-psm 6"))
        #     t.chatText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]", "", t.chatText)
        #     keyword1 = 'disp'
        #     keyword2 = 'left'
        #     keyword3 = 'pic'
        #     keyword4 = 'key'
        #     keyword5 = 'lete'
        #     # print (recognizedText)
        #     if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2) > 0) or (
        #                 t.chatText.find(keyword3) > 0) or (t.chatText.find(keyword4) > 0) or (
        #                 t.chatText.find(keyword5) > 0)):
        #         gui.statusbar.set("Captcha discovered! Submitting...")
        #         captchaIMG = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 5, self.topleftcorner[1] + 490,
        #                                     self.topleftcorner[0] + 335, self.topleftcorner[1] + 550)
        #         captchaIMG.save("pics/captcha.png")
        #         # captchaIMG.show()
        #         time.sleep(0.5)
        #         t.captcha = solveCaptcha("pics/captcha.png")
        #         mouse.EnterCaptcha(t.captcha)
        #         print("Entered captcha")
        #         print(t.captcha)
        # except:
        #     print("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, scraped):
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 402, self.topleftcorner[1] + 458,
                                   self.topleftcorner[0] + 442 + 400, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.ImBack, img, 0.08)
        if count > 0:
            mouse.MouseAction("Imback")
            return False
            gui.statusbar.set("I am back found")
        else:
            return True

    def check_for_call(self, scraped):
        gui.statusbar.set("Check for Call")
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 575, self.topleftcorner[1] + 483,
                                   self.topleftcorner[0] + 575 + 100, self.topleftcorner[1] + 483 + 100)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.call, img, 0.01)
        if count > 0:
            self.callButton = True
        else:
            self.callButton = False
        return True

    def check_for_allincall_button(self, scraped):
        gui.statusbar.set("Check for All in")
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 557, self.topleftcorner[1] + 493,
                                   self.topleftcorner[0] + 670, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
        else:
            self.allInCallButton = False

        return True

    def get_deck_cards(self, scraped):
        gui.statusbar.set("Get Deck cards")
        self.cardsOnTable = []
        pil_image = self.CropImage(a.entireScreenPIL, t.topleftcorner[0] + 206, t.topleftcorner[1] + 158,
                                   t.topleftcorner[0] + 600, t.topleftcorner[1] + 158 + 120)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value

            method = eval('cv2.TM_SQDIFF_NORMED')

            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.01:
                self.cardsOnTable.append(key)
            if len(self.cardsOnTable) < 1:
                self.gameStage = "PreFlop"
            elif len(self.cardsOnTable) == 3:
                self.gameStage = "Flop"
            elif len(self.cardsOnTable) == 4:
                self.gameStage = "Turn"
            elif len(self.cardsOnTable) == 5:
                self.gameStage = "River"

        return True

    def get_my_cards(self, scraped):
        self.mycards = []
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 450, self.topleftcorner[1] + 330,
                                   self.topleftcorner[0] + 450 + 80, self.topleftcorner[1] + 330 + 80)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        for key, value in scraped.cardImages.items():
            template = value
            method = eval('cv2.TM_SQDIFF_NORMED')
            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if min_val < 0.01:
                # print files+" found", min_val, max_val, min_loc, max_loc
                self.mycards.append(key)
        if len(self.mycards) == 2:
            t.myFundsChange = float(t.myFunds) - float(str(h.myFundsHistory[-1]).strip('[]'))
            return True
        else:
            # print (self.mycards)
            return False

    def get_covered_card_holders(self, scraped):
        gui.statusbar.set("Analyse other players and position")
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                   self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.coveredCardHolder, img, 0.0001)
        t.PlayerNames = []
        t.PlayerFunds = []

        t.PlayerNames.append("Myself")
        count = 0
        for pt in points:
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            playerNameImage = pil_image.crop(
                (pt[0] - (955 - 890), pt[1] + 270 - 222, pt[0] + 20, pt[1] + +280 - 222))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerNameImage = playerNameImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerNameImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerNameImage, None, False, "-psm 6"))
                recognizedText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789]", "",
                                        recognizedText)
                t.PlayerNames.append(recognizedText)
            except:
                print("Pyteseract error in player name recognition")

            playerFundsImage = pil_image.crop(
                (pt[0] - (955 - 890) + 10, pt[1] + 270 - 222 + 20, pt[0] + 10, pt[1] + +280 - 222 + 22))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerFundsImage = playerFundsImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerFundsImage = playerFundsImage.filter(ImageFilter.MaxFilter)
            # playerFundsImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerFundsImage, None, False, "-psm 6")).replace("-",
                                                                                                                ".")
                recognizedText = re.sub("[^0123456789.]", "",
                                        recognizedText)
                t.PlayerFunds.append(float(recognizedText))
            except:
                print("Pyteseract error in player name recognition")

        # print (t.PlayerNames)

        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        self.coveredCardHolders = np.round(count)

        # print self.coveredCardHolders

        if self.coveredCardHolders == 1:
            self.isHeadsUp = True
            # print "HeadSUP!"
        else:
            self.isHeadsUp = False

        if self.coveredCardHolders > 0:
            return True
        else:
            print("No other players found. Assuming 1 player")
            self.coveredCardHolders = 1
            return True

    def get_played_players(self, scraped):
        gui.statusbar.set("Analyse past players")
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                   self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)

        im = pil_image
        x, y = im.size
        eX, eY = 280, 150  # Size of Bounding Box for ellipse

        bbox = (x / 2 - eX / 2, y / 2 - eY / 2, x / 2 + eX / 2, y / 2 + eY / 2 - 20)
        rectangle1 = (0, 0, 800, 130)
        rectangle2 = (0, 380, 800, 499)
        rectangle3 = (0, 1, 110, 499)
        rectangle4 = (690, 1, 800, 499)
        rectangle5 = (400, 300, 500, 400)
        draw = ImageDraw.Draw(im)
        draw.ellipse(bbox, fill=128)
        draw.rectangle(rectangle1, fill=128)
        draw.rectangle(rectangle2, fill=128)
        draw.rectangle(rectangle3, fill=128)
        draw.rectangle(rectangle4, fill=128)
        draw.rectangle(rectangle5, fill=128)
        del draw
        # im.show()
        pil_image_ellipsed = im

        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image_ellipsed), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.smallDollarSign1, img, 0.05)

        self.PlayerPots = []
        for pt in points:
            x = pt[0] + 9
            y = pt[1] + 1
            modpt = (x, y)
            w = 40
            h = 15
            cv2.rectangle(img, modpt, (x + w, y + h), (0, 0, 255), 2)
            # cv2.imshow("Image",img)
            playerPotImage = pil_image_ellipsed.crop((x, y, x + w, y + h))

            basewidth = 100
            wpercent = (basewidth / float(playerPotImage.size[0]))
            hsize = int((float(playerPotImage.size[1]) * float(wpercent)))
            playerPotImage = playerPotImage.resize((basewidth, hsize), Image.ANTIALIAS)

            playerPotImage = playerPotImage.filter(ImageFilter.MinFilter)

            recognizedText = pytesseract.image_to_string(playerPotImage, None, False, "-psm 6")
            recognizedText = re.sub("[^0123456789.]", "", recognizedText)
            if recognizedText != "":
                self.PlayerPots.append(recognizedText)

        self.PlayerPots.sort()

        try:
            t = [float(x) for x in self.PlayerPots]
            self.playerBetIncreases = [t[i + 1] - t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncrease = max(self.playerBetIncreases)

            self.playerBetIncreasesAsPotPercentage = [(x / self.totalPotValue) for x in self.playerBetIncreases]
            self.maxPlayerBetIncreasesAsPotPercentage = max(self.playerBetIncreasesAsPotPercentage)
        except:  # when no other players are around (avoid division by zero)
            self.maxPlayerBetIncrease = 0
            self.playerBetIncreasesAsPotPercentage = [0]
            self.maxPlayerBetIncreasesAsPotPercentage = 0

        try:
            self.playerBetIncreasesPercentage = [t[i + 1] / t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncreasesPercentage = max(self.playerBetIncreasesPercentage)

            # print "Player Pots:           " + str(self.PlayerPots)
            # print "Player Pots increases: " + str(self.playerBetIncreases)
            # print "Player increase as %:  " + str(self.playerBetIncreasesPercentage)

        except:
            self.playerBetIncreasesPercentage = [0]
            self.maxPlayerBetIncreasesPercentage = 0

        if self.isHeadsUp == True:
            try:
                self.maxPlayerBetIncreasesPercentage = (self.totalPotValue - h.previousPot - h.myLastBet) / h.myLastBet
                self.maxPlayerBetIncrease = (self.totalPotValue - h.previousPot - h.myLastBet) - h.myLastBet
                print("Remembering last bet: " + str(self.myLastBet))
            except:
                # print ("Not remembering last bet")
                self.maxPlayerBetIncreasesPercentage = 0
                self.maxPlayerBetIncrease = 0

        # raw_input("Press Enter to continue...")
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()


        self.playersBehind = count

        self.playersAhead = int(np.round(self.coveredCardHolders - self.playersBehind))
        # print (self.PlayerPots)

        if p.XML_entries_list1['smallBlind'].text in self.PlayerPots:
            self.playersAhead += 1
            self.playersBehind -= 1
            # print ("Found small blind")

        self.playersAhead = int(max(self.playersAhead, 0))
        # print ("Played players: " + str(self.playersBehind))

        return True

    def get_total_pot_value(self):
        gui.statusbar.set("Get Pot Value")
        returnvalue = True
        x1 = 385
        y1 = 120
        x2 = 430
        y2 = 131
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 200
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        pil_image_min = pil_image.filter(ImageFilter.MinFilter)
        pil_image_median = pil_image.filter(ImageFilter.MedianFilter)
        pil_image_mode = pil_image.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)
        # recognizedText1 = pytesseract.image_to_string(pil_image.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN), None, False, "-psm 6 nobatch digits")
        # recognizedText2 = pytesseract.image_to_string(pil_image_mode, None, False, "-psm 6").replace("-", ".")  #
        # recognizedText3 = pytesseract.image_to_string(pil_image_min, None, False, "-psm 6").replace("-", ".")
        try:
            recognizedText1 = pytesseract.image_to_string(
                pil_image.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN), None, False,
                "-psm 6 nobatch digits")
            self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText1)
            # if self.totalPotValue == "":
            #     self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText2)
            #     if self.totalPotValue == "":
            #         self.totalPotValue = re.sub("[^0123456789.]", "", recognizedText3)
            # if self.totalPotValue[0] == ".": self.totalPotValue = self.totalPotValue[1:]
            self.totalPotValue = float(float(self.totalPotValue))

        except:
            print("unable to get pot value")
            gui.statusbar.set("Unable to get pot value")
            time.sleep(1)
            pil_image.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot
        return True

    def get_my_funds(self):
        x1 = 469
        y1 = 403
        x2 = 469 + 38
        y2 = 403 + 11
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 200
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
        pil_image_filtered = pil_image.filter(ImageFilter.ModeFilter)
        pil_image_filtered2 = pil_image.filter(ImageFilter.MedianFilter)
        self.myFundsError = False

        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6")
        if recognizedText == "":
            recognizedText = pytesseract.image_to_string(pil_image_filtered, None, False, "-psm 6")
            if recognizedText == "":
                recognizedText = pytesseract.image_to_string(pil_image_filtered2, None, False, "-psm 6")
        # pil_image.show()
        try:
            pil_image.save("pics/myFunds.png")
        except:
            print("Could not save myFunds.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)


        try:
            self.myFunds = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            print("myFunds not regognised!")
            gui.statusbar.set("!!Funds NOT recognised!!")
            a.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)
        return True

    def getCurrentCallValue(self):
        gui.statusbar.set("Get Call value")
        x1 = 590
        y1 = 511
        x2 = 590 + 50
        y2 = 511 + 14

        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        basewidth = 100
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        pil_image = pil_image.filter(ImageFilter.ModeFilter)

        if t.checkButton == False:
            recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$",
                                                                                                                    "")
            try:
                self.currentCallValue = float(re.sub("[^0123456789\.]", "", recognizedText))
                self.getCallButtonValueSuccess = True
                if self.allInCallButton == True and self.myFundsError == False and self.currentCallValue < self.myFunds:
                    self.getCallButtonValueSuccess = False
                    pil_image.save("pics/ErrCallValue.png")
                    self.currentCallValue = self.myFunds
            except:
                self.currentCallValue = 0
                self.CallValueReadError = True
                pil_image.save("pics/ErrCallValue.png")

        # if len(self.currentRoundPotValue)>0: return True
        # else: return False

        return True

    def get_current_bet_value(self):
        gui.statusbar.set("Get Bet Value")
        x1 = 590 + 125
        y1 = 511
        x2 = 590 + 50 + 125
        y2 = 511 + 14

        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        basewidth = 100
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
        pil_image = pil_image.filter(ImageFilter.MedianFilter)

        recognizedText = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ", "").replace("$", "")
        try:
            self.currentBetValue = float(re.sub("[^0123456789\.]", "", recognizedText))
        except:
            returnvalue = False
            self.currentBetValue = 9999999.0

        if self.currentBetValue < self.currentCallValue:
            self.currentBetValue = self.currentCallValue * 2
            self.BetValueReadError = True
            a.entireScreenPIL.save("pics/BetValueError.png")

        return True

    def get_current_pot_value(self):
        x1 = 390
        y1 = 324
        x2 = 431
        y2 = 340
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        pil_image.save("pics/currenPotValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        self.currentRoundPotValue = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ",
                                                                                                          "").replace(
            "$", "")
        if len(self.currentRoundPotValue) > 6: self.currentRoundPotValue = ""
        # else: return False

        return True

    def get_lost_everything(self, scraped):
        x1 = 100
        y1 = 100
        x2 = 590 + 50 + 125
        y2 = 511 + 14
        pil_image = self.CropImage(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                   self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.lostEverything, img, 0.001)

        if count > 0:
            h.lastGameID = str(h.GameID)
            t.myFundsChange = float(0) - float(str(h.myFundsHistory[-1]).strip('[]'))
            L.mark_last_game(t, h)
            gui.statusbar.set("Everything is lost. Last game has been marked.")
            user_input = input("Press Enter for exit ")
            sys.exit()
        else:
            return True

    def get_new_hand(self):
        if h.previousCards != t.mycards:
            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            L.mark_last_game(t, h)

            self.call_genetic_algorithm()

            cards = ' '.join(t.mycards)
            gui.statusbar.set("New hand: " + str(cards))

            if gui.active == True:
                gui.y.append(t.myFunds)
                gui.line1.set_ydata(gui.y[-100:])
                gui.f.canvas.draw()

                maxh = max(gui.y)
                gui.a.set_ylim(0, max(6, maxh))
                gui.f.canvas.draw()

            if gui.active == True:
                data = L.get_stacked_bar_data('Template', p.current_strategy.text, 'stackedBar')
                maxh = float(p.XML_entries_list1['bigBlind'].text) * 10
                i = 0
                for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(gui.p0.patches, gui.p1.patches,
                                                                           gui.p2.patches,
                                                                           gui.p3.patches, gui.p4.patches,
                                                                           gui.p5.patches, gui.p6.patches):
                    g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
                    height = g[i]
                    i += 1
                    rect0.set_height(height[0])
                    rect1.set_y(height[0])
                    rect1.set_height(height[1])
                    rect2.set_y(height[0] + height[1])
                    rect2.set_height(height[2])
                    rect3.set_y(height[0] + height[1] + height[2])
                    rect3.set_height(height[3])
                    rect4.set_y(height[0] + height[1] + height[2] + height[3])
                    rect4.set_height(height[4])
                    rect5.set_y(height[0] + height[1] + height[2] + height[3] + height[4])
                    rect5.set_height(height[5])
                    rect6.set_y(height[0] + height[1] + height[2] + height[3] + height[4] + height[5])
                    rect6.set_height(height[6])
                    maxh = max(height[0] + height[1] + height[2] + height[3] + height[4] + height[5] + height[6], maxh)
                # canvas = FigureCanvasTkAgg(gui.h, master=gui.root)

                gui.c.set_ylim((0, maxh))
                gui.h.canvas.draw()
                # canvas.get_tk_widget().grid(row=6, column=1)

            h.myLastBet = 0
            h.myFundsHistory.append(str(t.myFunds))
            h.previousCards = t.mycards
            h.lastSecondRoundAdjustment = 0

            a.take_screenshot()

        return True

class MouseMoverPS(object):
    def EnterCaptcha(self, captchaString):
        gui.statusbar.set("Entering Captcha: " + str(captchaString))
        buttonToleranceX = 30
        buttonToleranceY = 0
        tlx = t.topleftcorner[0]
        tly = t.topleftcorner[1]
        flags, hcursor, (x1, y1) = win32gui.GetCursorInfo()
        x2 = 30 + tlx
        y2 = 565 + tly
        a.mouse_mover(x1, y1, x2, y2)
        a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
        try:
            Write(captchaString, "win")
        except:
            t.error = "Failing to type Captcha"
            print(t.error)

    def MouseAction(self, decision):
        tlx = t.topleftcorner[0]
        tly = t.topleftcorner[1]
        flags, hcursor, (x1, y1) = win32gui.GetCursorInfo()
        buttonToleranceX = 635 - 525
        buttonToleranceY = 564 - 531

        if decision == "Imback":
            time.sleep(np.random.uniform(1, 5, 1))
            buttonToleranceX = 10
            buttonToleranceY = 31
            x2 = 663 + tlx
            y2 = 502 + tly
            # print "move mouse to "+str(y2)
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Fold":
            x2 = 393 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Call" or decision == "Call Deception":
            x2 = 529 + tlx
            y2 = 534 + tly

            if t.allInCallButton == True:
                x2 = 660 + tlx

            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Check" or decision == "Check Deception":
            x2 = 529 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet":
            x2 = 666 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "BetPlus":
            buttonToleranceX = 100
            buttonToleranceY = 5
            x2 = 630 + tlx
            y2 = 500 + tly
            a.mouse_mover(x1, y1, x2, y2)

            for n in range(int(p.XML_entries_list1['BetPlusInc'].text)):
                a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 666 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet Bluff":
            buttonToleranceX = 100
            buttonToleranceY = 5
            x2 = 630 + tlx
            y2 = 500 + tly
            a.mouse_mover(x1, y1, x2, y2)

            for n in range(t.currentBluff - 1):
                self.MouseClicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 666 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet half pot":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 597 + tlx
            y2 = 470 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 666 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet pot":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 655 + tlx
            y2 = 470 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1))
            x2 = 666 + tlx
            y2 = 534 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet max":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 722 + tlx
            y2 = 470 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1))
            x2 = 666 + tlx
            y2 = 528 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        xscatter = int(np.round(np.random.uniform(1600, 1800, 1), 0))
        yscatter = int(np.round(np.random.uniform(300, 400, 1), 0))
        # print xrand,yrand
        time.sleep(np.random.uniform(0.4, 1.0, 1))
        # print x2
        # print xscatter
        a.mouse_mover(x2, y2, xscatter, yscatter)

class MouseMoverPP(object):
    def EnterCaptcha(self, captchaString):
        gui.statusbar.set("Entering Captcha: " + str(captchaString))
        buttonToleranceX = 30
        buttonToleranceY = 0
        tlx = t.topleftcorner[0]
        tly = t.topleftcorner[1]
        flags, hcursor, (x1, y1) = win32gui.GetCursorInfo()
        x2 = 30 + tlx
        y2 = 565 + tly
        a.mouse_mover(x1, y1, x2, y2)
        a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
        try:
            Write(captchaString, "win")
        except:
            t.error = "Failing to type Captcha"
            print(t.error)

    def MouseAction(self, decision):
        tlx = t.topleftcorner[0]
        tly = t.topleftcorner[1]
        flags, hcursor, (x1, y1) = win32gui.GetCursorInfo()
        buttonToleranceX = 100
        buttonToleranceY = 35

        if decision == "Imback":
            time.sleep(np.random.uniform(1, 5, 1))
            buttonToleranceX = 100
            buttonToleranceY = 31
            x2 = 560 + tlx
            y2 = 492 + tly
            # print "move mouse to "+str(y2)
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Fold":
            x2 = 419 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Call" or decision == "Call Deception":
            x2 = 546 + tlx
            y2 = 492 + tly

            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Check" or decision == "Check Deception":
            x2 = 546 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet":
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "BetPlus":
            buttonToleranceX = 4
            buttonToleranceY = 5
            x2 = 662 + tlx
            y2 = 492 - 37 + tly
            a.mouse_mover(x1, y1, x2, y2)

            for n in range(int(p.XML_entries_list1['BetPlusInc'].text)):
                a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
                if t.minBet > float(p.XML_entries_list1['BetPlusInc'].text): continue

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 100
            buttonToleranceY = 35
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet Bluff":
            buttonToleranceX = 100
            buttonToleranceY = 5
            x2 = 662 + tlx
            y2 = 492 - 37 + tly
            a.mouse_mover(x1, y1, x2, y2)

            if t.currentBluff > 1:
                for n in range(t.currentBluff - 1):
                    self.MouseClicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet half pot":
            buttonToleranceX = 10
            buttonToleranceY = 5
            x2 = 419 + 73 + tlx
            y2 = 492 - 65 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1))
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet pot":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 546 + 25 + tlx
            y2 = 492 - 65 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1))
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet max":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 722 + tlx
            y2 = 492 - 65 + tly
            a.mouse_mover(x1, y1, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1))
            x2 = 675 + tlx
            y2 = 492 + tly
            a.mouse_mover(x1temp, y1temp, x2, y2)
            a.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        xscatter = int(np.round(np.random.uniform(1600, 1800, 1), 0))
        yscatter = int(np.round(np.random.uniform(300, 400, 1), 0))
        # print xrand,yrand
        time.sleep(np.random.uniform(0.4, 1.0, 1))
        # print x2
        # print xscatter
        a.mouse_mover(x2, y2, xscatter, yscatter)


# ==== MAIN PROGRAM =====
if __name__ == '__main__':
    def run_pokerbot():
        global LogFilename, h, L, p, mouse, t, a, d

        LogFilename = 'log'
        h = History()
        L = Logging(LogFilename)
        a = Tools()

        if p.XMLEntriesList['pokerSite'].text == "PS":
            mouse = MouseMoverPS()
        elif p.XMLEntriesList['pokerSite'].text == "PP":
            mouse = MouseMoverPP()
        else:
            raise ("Invalid PokerSite")
        counter = 0

        while True:
            p.read_XML()
            if p.XMLEntriesList['pokerSite'].text == "PS":
                t = TablePS()
            elif p.XMLEntriesList['pokerSite'].text == "PP":
                t = TablePP()
            elif p.XMLEntriesList['pokerSite'].text == "F1":
                t = TableF1()

            ready = False
            while (not ready):
                t.timeout_start = time.time()
                ready = a.take_screenshot() and \
                        t.get_top_left_corner(a) and \
                        t.check_for_captcha() and \
                        t.get_lost_everything(a) and \
                        t.check_for_imback(a) and \
                        t.get_my_funds() and \
                        t.get_my_cards(a) and \
                        t.get_new_hand() and \
                        t.check_for_button(a) and \
                        t.get_covered_card_holders(a) and \
                        t.get_total_pot_value() and \
                        t.get_played_players(a) and \
                        t.check_for_checkbutton(a) and \
                        t.get_deck_cards(a) and \
                        t.check_for_call(a) and \
                        t.check_for_allincall_button(a) and \
                        t.get_current_call_value() and \
                        t.get_current_bet_value()

            d = DecisionMaker()

            d.make_decision(t, h, p)

            gui.statusbar.set("Writing log file")

            L.write_log_file(p, h, t, d)

            h.previousPot = t.totalPotValue
            h.histGameStage = t.gameStage
            h.histDecision = d.decision
            h.histEquity = d.equity
            h.histMinCall = t.minCall
            h.histMinBet = t.minBet
            h.histPlayerPots = t.PlayerPots

            # print ("")


    terminalmode = False
    setupmode = False

    p = XMLHandler('strategies.xml')
    p.read_XML()

    if setupmode == True:
        a = Tools()
        a.setup_get_item_location()
        sys.exit()

    if terminalmode == False:
        gui = GUI(p)
        p.ExitThreads = False
        t1 = threading.Thread(target=run_pokerbot, args=[])
        t1.start()
        gui.root.mainloop()
        p.ExitThreads = True

    elif terminalmode == True:
        gui = Terminal()
        run_pokerbot()
