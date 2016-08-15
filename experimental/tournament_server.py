"""Experimental program that plays against itself. Later to be enhances so the bot can self improve when
playing against itself and this program will be used as a base for the server administration"""

import matplotlib.pyplot as plt
import numpy as np


class Sentinel(object):
    def __init__(self, f, c, b):
        self.funds = f
        self.fundsList = [f]
        self.cLimit = c
        self.bLimit = b
        self.myPot = 0
        self.placedBets = 0

    def getDecision(self):
        self.decision = 'f'
        if self.cards >= self.cLimit and self.funds >= self.cLimit: self.decision = 'c'
        if self.cards >= self.bLimit and self.funds >= self.bLimit: self.decision = 'b'

        print("Decision made: " + self.decision)


class Table(object):
    def __init__(self, sb, bb):
        self.pot = 0
        self.tempPot = 0
        self.bigBlind = bb
        self.smallBlind = sb
        self.minCall = bb
        self.betAdd = 2
        self.maxBetsPerRoundperPlayer = 1
        self.forceEndRound = False

    def distributeCards(self):
        for i in playersInGame:
            s[i].cards = np.random.randint(0, 100)

    def processDecision(self, i):
        self.minBet = self.minCall + self.betAdd

        if s[i].decision == 'f':
            playersInGame.remove(i)

        if s[i].decision == 'b' and s[i].placedBets >= t.maxBetsPerRoundperPlayer:
            s[i].decision = 'c'

        if s[i].decision == 'c':
            addon = self.minCall - s[i].myPot
            s[i].funds -= addon
            self.tempPot += addon
            s[i].myPot += addon
            self.highestPot = s[i].myPot

        if s[i].decision == 'b':
            addon = self.minBet - s[i].myPot
            s[i].funds -= addon
            self.tempPot += addon
            s[i].myPot += addon
            self.minCall = s[i].myPot
            self.highestPot = s[i].myPot
            s[i].placedBets += 1

        print("This round pot is now: " + str(self.tempPot))

    def getWinner(self):
        self.winner = playersInGame[0]
        if len(playersInGame) > 1:
            for i in np.arange(len(playersInGame) - 1):
                if s[playersInGame[i]].cards < s[playersInGame[i + 1]].cards:
                    self.winner = playersInGame[i + 1]
        else:
            self.winner = playersInGame[0]

    def endRound(self):
        for p in playersInGame:
            if self.winner == p:
                s[p].funds += self.tempPot

        for i in np.arange(numberOfPlayers):
            s[i].myPot = 0
            s[i].placedBets = 0
            s[i].decision = ''
            s[i].fundsList.append(s[i].funds)

        self.minCall = self.bigBlind
        self.minBet = 0
        self.pot = 0
        self.tempPot = 0
        self.highestPot = 0
        self.forceEndRound = False

    def viewStatus(self):
        print("Winner: " + str(self.winner))
        for i in np.arange(numberOfPlayers):
            print("P" + str(i) + ": Cards: " + str(s[i].cards) + "  Funds: " + str(s[i].funds))

        print("")

    def setRoles(self, n, playersInGame):
        self.dealer_ix = n % len(playersInGame)
        self.sb_ix = self.dealer_ix + 1
        if self.sb_ix > len(playersInGame) - 1: self.sb_ix = 0
        self.bb_ix = self.sb_ix + 1
        if self.bb_ix > len(playersInGame) - 1: self.bb_ix = 0
        self.firstPlayer_ix = self.bb_ix + 1
        if self.firstPlayer_ix > len(playersInGame) - 1: self.firstPlayer_ix = 0

    def postBlinds(self):
        s[playersInGame[self.sb_ix]].funds -= self.smallBlind
        s[playersInGame[self.sb_ix]].myPot += self.smallBlind
        t.tempPot += self.smallBlind

        s[playersInGame[self.bb_ix]].funds -= self.bigBlind
        s[playersInGame[self.bb_ix]].myPot += self.bigBlind
        t.tempPot += self.bigBlind

    def removeZeroCashPlayers(self):
        for n in playersInGame:
            if s[n].funds <= self.smallBlind:
                playersInGame.remove(n)
                playersOriginal.remove(n)


if __name__ == '__main__':
    s = []
    t = Table(1, 2)

    s.append(Sentinel(100, 60, 80))
    s.append(Sentinel(100, 50, 90))
    s.append(Sentinel(100, 40, 90))
    s.append(Sentinel(100, 40, 90))
    s.append(Sentinel(100, 40, 90))
    s.append(Sentinel(100, 40, 90))
    s.append(Sentinel(100, 20, 90))
    numberOfPlayers = len(s)

    playersOriginal = np.arange(numberOfPlayers).tolist()
    for n in np.arange(100000):
        playersInGame = playersOriginal[:]
        t.removeZeroCashPlayers()

        if len(playersInGame) > 1:
            print("")
            print("Game: " + str(n))

            t.distributeCards()
            t.setRoles(n, playersInGame)
            t.postBlinds()

            c = t.firstPlayer_ix

            while True:

                if s[playersInGame[c]].myPot == t.minCall:  # player pot matches mincall
                    break

                if len(playersInGame) < 2:  # only one player left
                    break

                print("Player: " + str(playersInGame[c]))
                s[playersInGame[c]].getDecision()
                t.processDecision(playersInGame[c])

                # get next player
                c += 1
                if c > len(playersInGame) - 1:  # circle around
                    c = 0

            t.getWinner()
            t.endRound()
            t.viewStatus()

    plt.plot(s[t.winner].fundsList)
    plt.title(t.winner)
    plt.show()
