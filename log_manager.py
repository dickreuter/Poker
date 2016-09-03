'''
Functions that are used to log and analyse present and past pokergames
'''
import pandas as pd
import numpy as np
import time
from collections import Iterable

class Logging(object):
    def __init__(self, filename):
        self.log_filename = filename

        try:
            if not hasattr(self,'log_data_file'):
                self.log_data_file = pd.read_csv(self.log_filename + ".csv")
                self.log_data_file = self.log_data_file.drop('Unnamed: 0', 1)
        except:
            print("No Logfile found. Creating new one.")
            d = {'lastGameID': '0', 'GameID': '0', 'Template': '0', 'gameStage': '0', 'decision': '0',
                 'FinalOutcome': 'None', 'FinalFundsChange': '0', 'equity': '0'}
            self.log_data_file = pd.DataFrame(d, index=[0])

    def isIterable(self, x):
        # use str instead of basestring if Python3
        if isinstance(x, Iterable) and not isinstance(x, str):
            return x
        return [x]

    def write_CSV(self, df, file):
        try:
            df.to_csv(file + ".csv")
            # print ("writing to CSV Log File...")
        except:
            print("Could not write to Log file!")
            # print FinalDataFrame

    def write_log_file(self, p, h, t, d):
        hDict = {}
        tDict = {}
        dDict = {}
        pDict = {}

        for key, val in vars(p).items():
            pDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(h).items():
            hDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(t).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val)))<50:
                tDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(d).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val)))<20:
                dDict[key] = " ".join(str(ele) for ele in self.isIterable(val))

        Dh = pd.DataFrame(hDict, index=[0])
        Dt = pd.DataFrame(tDict, index=[0])
        Dd = pd.DataFrame(dDict, index=[0])
        Dp = pd.DataFrame(pDict, index=[0])

        self.FinalDataFrame = pd.concat([Dd, Dt, Dh, Dp], axis=1)

        self.log_data_file = pd.concat([self.FinalDataFrame, self.log_data_file], ignore_index=True)
        self.write_CSV(self.log_data_file, self.log_filename)

    def mark_last_game(self, t, h):
        # updates the last game after it becomes know if it was won or lost
        outcome = "na"
        if t.myFundsChange > 0:
            outcome = "Won";
            h.wins += 1;
            h.totalGames += 1
        elif t.myFundsChange < 0:
            outcome = "Lost";
            h.losses += 1;
            h.totalGames += 1
        elif t.myFundsChange == 0:
            outcome = "Neutral";
            h.totalGames += 1
        try:
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalOutcome'] = outcome
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalStage'] = h.histGameStage
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalFundsChange'] = t.myFundsChange
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalFundsChangeABS'] = abs(t.myFundsChange)
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalDecision'] = h.histDecision
            self.log_data_file.ix[self.log_data_file.GameID == h.lastGameID, 'FinalEquity'] = h.histEquity
            # print ("Adjusting log file for last game")
            self.write_CSV(self.log_data_file, self.log_filename)
            # print "LastGameID Full list: "+str(L.LogDataFile.ix[L.LogDataFile.lastGameID])
            # print "LastGameID:" + str(h.lastGameID)
            # print "FinalOutcome:" + str(L.LogDataFile.FinalOutcome)
        except:
            #print("Unable to assess previous game")
            #time.sleep(0.1)
            pass

    def filter_by_parameter(self, parameter, value):
        self.LogDataFileFiltered = self.log_data_file[self.log_data_file[parameter] == value]
        self.LogDataFileFiltered2 = self.log_data_file[(self.log_data_file[parameter] == value) & (
            (self.log_data_file.FinalOutcome == 'Won') | (self.log_data_file.FinalOutcome == 'Lost'))]

    def filter_by_template(self, p_name):
        self.LogDataFileFiltered = self.log_data_file[self.log_data_file.Template == p_name]
        self.LogDataFileFiltered2 = self.log_data_file[(self.log_data_file.Template == p_name) & (
            (self.log_data_file.FinalOutcome == 'Won') | (self.log_data_file.FinalOutcome == 'Lost'))]

    def replace_strings_with_numbers(self):
        self.LogDataFileFiltered = self.LogDataFileFiltered.replace(
            {'Won': 1, 'Lost': -1, 'Neutral': 0, 'Fold': 0, 'Check': 1, 'Check Deception': 1, 'Call': 2,
             'Call Decepsion': 2, 'Bet': 3, 'Bet Bluff': 3, 'BetPlus': 3, 'Bet half pot': 4, 'Bet pot': 5, 'Bet max': 6,
             'PreFlop': 0, 'Flop': 1, 'Turn': 2, 'River': 3})

    def collapse_games(self):
        self.LogDataFileSummary = self.LogDataFileFiltered.pivot_table(index='GameID',
                                                                       values=['FinalFundsChange', 'FinalDecision',
                                                                               'FinalOutcome', 'FinalStage',
                                                                               'FinalEquity'], aggfunc=np.mean)
        self.LogDataFileSummary['FinalDecision'] = self.LogDataFileSummary['FinalDecision'].map(
            {0.0: '0Fold', 1.0: '1Check', 2.0: '2Call', 3.0: '3Bet/Bet+', 4.0: '4Bet++', 5.0: '5Bet pot',
             6.0: '6Bet max'})
        self.LogDataFileSummary['FinalStage'] = self.LogDataFileSummary['FinalStage'].map(
            {0.0: '0PreFlop', 1.0: '1Flop', 2.0: '2Turn', 3.0: '3River'})
        self.write_CSV(self.LogDataFileSummary, self.log_filename + "_summary")

    def pivot1(self):
        try:
            print("\nGamecount stage and action\n" + str(
                self.LogDataFileSummary.pivot_table(index='FinalStage', columns='FinalDecision',
                                                    values='FinalFundsChange', margins=True, aggfunc=np.size)))
            # print "\nMean change of funds by stage and action\n" + str(np.round(self.LogDataFileSummary.pivot_table(index='FinalStage', columns='FinalDecision', values='FinalFundsChange', margins=True, aggfunc=np.mean),2))
            print("\nSum change of funds by stage and action\n" + str(np.round(
                self.LogDataFileSummary.pivot_table(index='FinalStage', columns='FinalDecision',
                                                    values='FinalFundsChange', margins=True, aggfunc=np.sum), 2)))
            # print "\nWinners vs losers\n" + str(np.round(self.LogDataFileFiltered2.pivot_table(index=['decision','gameStage'], columns='FinalOutcome', values='FinalFundsChange', margins=True, aggfunc=np.mean),2))
            # print "\nLosers sum\n: "+ str(self.LogDataFileSummary[self.LogDataFileSummary.FinalOutcome==-1].pivot_table(index='FinalDecision', values='FinalFundsChange', margins=True, aggfunc=np.sum))
            # print "\nWinners sum\n: "+  str(self.LogDataFileSummary[self.LogDataFileSummary.FinalOutcome==1].pivot_table(index='FinalDecision', values='FinalFundsChange', margins=True, aggfunc=np.sum))
            # print "\nTotal sum\n: "+  str(self.LogDataFileSummary.pivot_table(index='FinalDecision', values='FinalFundsChange', margins=True, aggfunc=np.sum))

            FCPG = np.sum(self.LogDataFileSummary['FinalFundsChange']) / np.size(
                self.LogDataFileSummary['FinalFundsChange'])
            print(FCPG)

        # print pd.DataFrame.to_dict(x)
        except:
            print("No log entries with given strategy to analyse.")

    def get_total_funds_change(self):
        FCPG = np.sum(self.LogDataFileSummary['FinalFundsChange']) / np.size(
            self.LogDataFileSummary['FinalFundsChange'])
        return FCPG

    def show_pivots(self, p_name):
        self.filter_by_template(p_name)
        self.replace_strings_with_numbers()
        try:
            self.collapse_games()
        except:
            print("Pivot summary collapsing not working")
        try:
            self.pivot1()
        except:
            print("Could not show Pivot")

    def get_neural_training_data(self, p_name, p_value, game_stage, decision):

        # filter out multiple rounds in the same game and gamestage
        self.log_data_file_collapsed = self.log_data_file.pivot_table(
            index=['GameID', 'gameStage', 'decision', 'FinalOutcome', 'Template', 'minBet', 'minCall'],
            values=['FinalFundsChange', 'equity'], aggfunc=np.mean)
        self.log_data_file_collapsed.reset_index(inplace=True)

        EquityValues = self.log_data_file_collapsed[
            (self.log_data_file_collapsed[p_name] != p_value) & (self.log_data_file_collapsed.decision == decision) & (
                self.log_data_file_collapsed.gameStage == game_stage)].equity.values.tolist()
        MinCallValues = self.log_data_file_collapsed[
            (self.log_data_file_collapsed[p_name] != p_value) & (self.log_data_file_collapsed.decision == decision) & (
                self.log_data_file_collapsed.gameStage == game_stage)].minCall.values.tolist()
        FinalFundsChange = self.log_data_file_collapsed[
            (self.log_data_file_collapsed[p_name] != p_value) & (self.log_data_file_collapsed.decision == decision) & (
                self.log_data_file_collapsed.gameStage == game_stage)].FinalFundsChange.values.tolist()

        Output = np.array([[1, 0] if x >= 0 else [0, 1] for x in FinalFundsChange])
        Input = np.array([list(i) for i in zip(EquityValues, MinCallValues)])

        Data = [Input, Output]

        return Data

    def get_stacked_bar_data(self, p_name, p_value, chartType):

        # filter out multiple rounds in the same game and gamestage
        self.log_data_file_collapsed = self.log_data_file.drop_duplicates(subset=['GameID', 'gameStage'], keep='first')

        self.d = dict()
        self.outcomes = ['Won', 'Lost']
        self.gameStages = ['PreFlop', 'Flop', 'Turn', 'River']
        self.decisions = ['Bet Bluff', 'Check Deception', 'Call Deception', 'Fold', 'Check', 'Call', 'Bet', 'BetPlus',
                          'Bet half pot', 'Bet pot']
        for outcome in self.outcomes:
            for gameStage in self.gameStages:
                for decision in self.decisions:
                    self.d[decision, gameStage, outcome] = sum(abs((self.log_data_file_collapsed[
                                                                        (self.log_data_file_collapsed[p_name] == p_value) & (
                                                                            (
                                                                                self.log_data_file_collapsed.FinalOutcome == outcome) & (
                                                                                self.log_data_file_collapsed.gameStage == gameStage) & (
                                                                                self.log_data_file_collapsed.decision == decision))].FinalFundsChange)))

        numbers = [[self.d['Call', 'PreFlop', 'Lost'], self.d['Call', 'Flop', 'Lost'], self.d['Call', 'River', 'Lost'],
                    self.d['Bet', 'Flop', 'Lost'], self.d['Bet', 'Turn', 'Lost'], self.d['Bet', 'River', 'Lost'],
                    self.d['Bet half pot', 'Turn', 'Lost'], self.d['Bet half pot', 'River', 'Lost'],
                    self.d['Fold', 'PreFlop', 'Lost'], self.d['Fold', 'Flop', 'Lost'], self.d['Fold', 'Turn', 'Lost'],
                    self.d['Fold', 'River', 'Lost'], self.d['Call', 'Flop', 'Won'], self.d['Call', 'Turn', 'Won'],
                    self.d['Call', 'River', 'Won'], self.d['Bet', 'Flop', 'Won'], self.d['Bet', 'Turn', 'Won'],
                    self.d['Bet', 'River', 'Won'], self.d['Bet half pot', 'Turn', 'Won'],
                    self.d['Bet half pot', 'River', 'Won'], 0, 0, 0, 0]]

        if chartType == 'spider':
            Data = {
                'column names':
                    ['Call Flop', 'Call Turn', 'Call River', 'Bet Flop', 'Bet Turn', 'Bet River', 'Bet Half Pot Turn',
                     'Bet Half Pot River', 'Fold PreFlop', 'Fold Flop', 'Fold Turn', 'Fold River'],
                'Sum of FinalFundsChangeABS':
                    numbers}

        if chartType == 'stackedBar':
            FinalData = [[self.d['Bet Bluff', 'PreFlop', 'Won'], self.d['Bet Bluff', 'PreFlop', 'Lost'], 0,
                          self.d['Bet Bluff', 'Flop', 'Won'] + self.d['Check Deception', 'Flop', 'Won'] + self.d[
                              'Call Deception', 'Flop', 'Won'],
                          self.d['Bet Bluff', 'Flop', 'Lost'] + self.d['Check Deception', 'Flop', 'Lost'] + self.d[
                              'Call Deception', 'Flop', 'Lost'], 0, self.d['Bet Bluff', 'Turn', 'Won'],
                          self.d['Bet Bluff', 'Turn', 'Lost'], 0, self.d['Bet Bluff', 'River', 'Won'],
                          self.d['Bet Bluff', 'River', 'Lost']],
                         [0, 0, 0, 0, 0, 0, 0, 0, 0, self.d['Bet pot', 'River', 'Won'],
                          self.d['Bet pot', 'River', 'Lost']],
                         [self.d['Bet half pot', 'PreFlop', 'Won'], self.d['Bet half pot', 'PreFlop', 'Lost'], 0,
                          self.d['Bet half pot', 'Flop', 'Won'], self.d['Bet half pot', 'Flop', 'Lost'], 0,
                          self.d['Bet half pot', 'Turn', 'Won'], self.d['Bet half pot', 'Turn', 'Lost'], 0,
                          self.d['Bet half pot', 'River', 'Won'], self.d['Bet half pot', 'River', 'Lost']],
                         [self.d['Bet', 'PreFlop', 'Won'] + self.d['BetPlus', 'PreFlop', 'Won'],
                          self.d['Bet', 'PreFlop', 'Lost'] + self.d['BetPlus', 'PreFlop', 'Lost'], 0,
                          self.d['Bet', 'Flop', 'Won'] + self.d['BetPlus', 'Flop', 'Won'],
                          self.d['Bet', 'Flop', 'Lost'] + self.d['BetPlus', 'Flop', 'Lost'], 0,
                          self.d['Bet', 'Turn', 'Won'] + self.d['BetPlus', 'Turn', 'Won'],
                          self.d['Bet', 'Turn', 'Lost'] + self.d['BetPlus', 'Turn', 'Lost'], 0,
                          self.d['Bet', 'River', 'Won'] + self.d['BetPlus', 'River', 'Won'],
                          self.d['Bet', 'River', 'Lost'] + self.d['BetPlus', 'River', 'Lost']],
                         [self.d['Call', 'PreFlop', 'Won'], self.d['Call', 'PreFlop', 'Lost'], 0,
                          self.d['Call', 'Flop', 'Won'], self.d['Call', 'Flop', 'Lost'], 0,
                          self.d['Call', 'Turn', 'Won'], self.d['Call', 'Turn', 'Lost'], 0,
                          self.d['Call', 'River', 'Won'], self.d['Call', 'River', 'Lost']],
                         [self.d['Check', 'PreFlop', 'Won'], self.d['Check', 'PreFlop', 'Lost'], 0,
                          self.d['Check', 'Flop', 'Won'], self.d['Check', 'Flop', 'Lost'], 0,
                          self.d['Check', 'Turn', 'Won'], self.d['Check', 'Turn', 'Lost'], 0,
                          self.d['Check', 'River', 'Won'], self.d['Check', 'River', 'Lost']],
                         [0, self.d['Fold', 'PreFlop', 'Lost'], 0, 0, self.d['Fold', 'Flop', 'Lost'], 0, 0,
                          self.d['Fold', 'Turn', 'Lost'], 0, 0, self.d['Fold', 'River', 'Lost']]]

        return FinalData

    def get_histrogram_data(self, p_name, p_value, game_stage, decision):

        # filter out multiple rounds in the same game and gamestage
        self.log_data_file_collapsed = self.log_data_file.pivot_table(
            index=['GameID', 'gameStage', 'decision', 'FinalOutcome', 'Template', 'minBet'],
            values=['FinalFundsChange', 'equity'], aggfunc=np.mean)
        self.log_data_file_collapsed.reset_index(inplace=True)
        equity_win = self.log_data_file_collapsed[
            (self.log_data_file_collapsed[p_name] == p_value) & (self.log_data_file_collapsed.FinalOutcome == 'Won') & (
                self.log_data_file_collapsed.decision == decision) & (
                self.log_data_file_collapsed.gameStage == game_stage)].equity.values.tolist()
        equity_loss = self.log_data_file_collapsed[
            (self.log_data_file_collapsed[p_name] == p_value) & (self.log_data_file_collapsed.FinalOutcome == 'Lost') & (
                self.log_data_file_collapsed.decision == decision) & (
                self.log_data_file_collapsed.gameStage == game_stage)].equity.values.tolist()

        return [equity_win, equity_loss]

    def get_game_count(self, strategy):
        try:
            n = max(self.log_data_file[self.log_data_file['Template'] == strategy].pivot_table(index='GameID',
                                                                                               values=['FinalOutcome'],
                                                                                               aggfunc=np.size).reset_index().index)

        except:
            n = 0
        return int(n + 1)

    def get_strategy_total_funds_change(self, strategy, days):
        try:
            n = round(self.log_data_file[self.log_data_file['Template'] == strategy][
                          ['FinalFundsChange', 'GameID']].drop_duplicates(subset=['GameID'])['FinalFundsChange'][
                      0:days].sum(), 2)
        except:
            n = 0
        return n

    def get_fundschange_chart(self,strategy):
        try:
            y = round(self.log_data_file[self.log_data_file['Template'] == strategy][
                          ['FinalFundsChange', 'GameID']].drop_duplicates(subset=['GameID'])['FinalFundsChange'], 2)
        except:
            y=[0]

        return y

    def get_strategy_list(self):
        strategy_list=list(self.log_data_file['Template'].unique())
        return strategy_list

    def get_scatterplot_data(self, p_name, p_value, game_stage, decision):

        wins=self.log_data_file[
            (self.log_data_file[p_name] == p_value) & (self.log_data_file.FinalOutcome == 'Won') & (
                self.log_data_file.decision == decision) & (
                self.log_data_file.gameStage == game_stage)] \
            [['GameID', 'equity', 'minCall', 'FinalFundsChange']]

        losses=self.log_data_file[
            (self.log_data_file[p_name] == p_value) & (self.log_data_file.FinalOutcome == 'Lost') & (
                self.log_data_file.decision == decision) & (
                self.log_data_file.gameStage == game_stage)] \
            [['GameID','equity', 'minCall', 'FinalFundsChange']]

        wins.drop_duplicates(subset='GameID',inplace=True)
        losses.drop_duplicates(subset='GameID', inplace=True)

        return [wins, losses]

def pivot_by_template():
    LogFilename = 'log'
    p_value = 'Strategy345'
    L = Logging(LogFilename)
    L.filter_by_template(p_value)
    L.replace_strings_with_numbers()
    L.collapse_games()
    L.pivot1()
    print("Funds Change:")
    f = L.get_strategy_total_funds_change(p_value, 30)
    print(f)
    # print L.SpiderData(p)

def filter_log_by_parameter(p_name, p_value):
    LogFilename = 'log'
    L = Logging(LogFilename)
    L.filter_by_parameter(p_name, p_value)
    L.replace_strings_with_numbers()
    L.collapse_games()
    result = L.get_total_funds_change()
    return (result)

def maximize_parameters(rowAmount):
    # experimental function to maximize parameters
    LogFilename = 'log_all'
    L = Logging(LogFilename)
    L.log_data_file = L.log_data_file.ix[0:rowAmount]
    parameterList = ['PreFlopCallPower', 'FlopCallPower', 'TurnCallPower', 'RiverCallPower', 'preFlopCallStretch',
                     'flopCallStretch', 'turnCallStretch', 'riverCallStretch', 'PreFlopBetPower', 'FlopBetPower',
                     'TurnBetPower', 'RiverBetPower', 'preFlopBetStretch', 'flopBetStretch', 'turnBetStretch',
                     'riverBetStretch', 'reducePreFlopOpponents', 'reducePreFlopOpponentsAmount', 'BlindPFMinEQCall1',
                     'BlindPFMultiplier1', 'BlindPFminPlayersAhead', 'BlindPFMinEQCall2', 'BlindPFMultiplier2',
                     'BlindPFMinEQCall3', 'BlindPFMultiplier3', 'FlopCheckDeceptionMinEquity', 'alwaysCallEquity',
                     'allInBetRiverEquity', 'secondRiverBetPotMinEquity', 'potStretchMultiplier']

    FinalList = []

    for p_name in parameterList:
        print(p_name)
        all_p_values = L.log_data_file[p_name].unique().ravel()

        for p_value in all_p_values:
            print(p_value)
            if (np.isnan(p_value)): continue

            result = filter_log_by_parameter(p_name, p_value)
            FinalList.append((p_name, p_value, result))

    result = pd.DataFrame(FinalList, columns=['Variable', 'ParamValue', 'AvgWin'])
    return result



if __name__ == '__main__':
    p_name = 'Template'
    p_value = ''
    gameStage = 'Flop'
    decision = 'Call'
    Strategy='PPStrategy4004'

    # pivot_by_template()
    LogFilename = 'log'
    L = Logging(LogFilename)
    #L.get_neural_training_data(p_name, p_value, gameStage, decision)
    #print(L.get_strategy_total_funds_change(Strategy,500))

    #print(L.get_neural_training_data(p_name,p_value,gameStage,decision))

    print (L.get_fundschange_chart(Strategy))

