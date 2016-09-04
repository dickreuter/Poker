'''
Functions that are used to log and analyse present and past pokergames
'''
import pandas as pd
import numpy as np
from pymongo import MongoClient
from collections import Iterable
import os
import datetime

class Logging(object):
    def __init__(self, filename):
        self.log_filename = filename
        self.mongoclient = MongoClient('mongodb://guest:donald@52.201.173.151:27017/POKER')
        self.mongodb = self.mongoclient.POKER

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

    def write_log_file(self, p, h, t, d):
        hDict = {}
        tDict = {}
        dDict = {}
        pDict = {}

        for key, val in vars(p).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val)))<25:
                pDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(h).items():
            hDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(t).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val)))<50:
                tDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(d).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val)))<20:
                dDict[key] = " ".join(str(ele) for ele in self.isIterable(val))

        pDict['logging_timestamp']=str(datetime.datetime.now())
        pDict['computername']=os.environ['COMPUTERNAME']

        Dh = pd.DataFrame(hDict, index=[0])
        Dt = pd.DataFrame(tDict, index=[0])
        Dd = pd.DataFrame(dDict, index=[0])
        Dp = pd.DataFrame(pDict, index=[0])

        self.FinalDataFrame = pd.concat([Dd, Dt, Dh, Dp], axis=1)
        result = self.mongodb.rounds.insert_one(self.FinalDataFrame.to_dict('records')[0])

    def mark_last_game(self, t, h):
        # updates the last game after it becomes know if it was won or lost
        outcome = "na"
        if t.myFundsChange > 0:
            outcome = "Won"
            h.wins += 1
            h.totalGames += 1
        elif t.myFundsChange < 0:
            outcome = "Lost"
            h.losses += 1
            h.totalGames += 1
        elif t.myFundsChange == 0:
            outcome = "Neutral"
            h.totalGames += 1
        if h.histGameStage!='':

            summary_dict = dict()
            summary_dict['rounds']=[]
            i=0
            cursor = self.mongodb.rounds.find({"GameID": h.lastGameID})
            for round in cursor:
                round_name_value=dict()
                round_name_value['round_number']=str(i)
                round_name_value['round_values']=round
                summary_dict['rounds'].append(round_name_value)
                i+=1

            summary_dict['GameID'] = h.lastGameID
            summary_dict['ComputerName']=os.environ['COMPUTERNAME']
            summary_dict['logging_timestamp']=str(datetime.datetime.now())
            summary_dict['FinalOutcome']= outcome
            summary_dict['FinalStage']= h.histGameStage
            summary_dict['FinalFundsChange']= t.myFundsChange
            summary_dict['FinalFundsChangeABS']= abs(t.myFundsChange)
            summary_dict['FinalDecision'] = h.histDecision
            summary_dict['FinalEquity'] = h.histEquity
            summary_dict['Template'] = t.current_strategy

            result = self.mongodb.games.insert_one(summary_dict)

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

    def get_total_funds_change(self):
        FCPG = np.sum(self.LogDataFileSummary['FinalFundsChange']) / np.size(
            self.LogDataFileSummary['FinalFundsChange'])
        return FCPG

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

        self.d = dict()
        self.outcomes = ['Won', 'Lost']
        self.gameStages = ['PreFlop', 'Flop', 'Turn', 'River']
        self.decisions = ['Bet Bluff', 'Check Deception', 'Call Deception', 'Fold', 'Check', 'Call', 'Bet', 'BetPlus',
                          'Bet half pot', 'Bet pot']

        for outcome in self.outcomes:
            for gameStage in self.gameStages:
                for decision in self.decisions:
                    self.d[decision, gameStage, outcome] = 0

        for gameStage in self.gameStages:
            cursor = self.mongodb.games.aggregate([
            { "$unwind" : "$rounds"},
            { "$match": {"Template": p_value,
                       "rounds.round_values.gameStage": gameStage }},
            { "$group": {
                 "_id": "$GameID",
                 "lastDecision": {"$last": "$rounds.round_values.decision"},
                 "FinalOutcome": { "$last": "$FinalOutcome" },
                 "FinalFundsChange": { "$last": "$FinalFundsChange" },
               }
             },
            { "$group": {
                 "_id": {"ld": "$lastDecision", "fa": "$FinalOutcome"},
                 "Total": {"$sum": "$FinalFundsChange"}}}
            ])

            for e in cursor:
                self.d[e['_id']['ld'], gameStage, e['_id']['fa']] = abs(e['Total'])


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

        # # filter out multiple rounds in the same game and gamestage
        # self.log_data_file_collapsed = self.log_data_file.pivot_table(
        #     index=['GameID', 'gameStage', 'decision', 'FinalOutcome', 'Template', 'minBet'],
        #     values=['FinalFundsChange', 'equity'], aggfunc=np.mean)
        # self.log_data_file_collapsed.reset_index(inplace=True)
        # equity_win = self.log_data_file_collapsed[
        #     (self.log_data_file_collapsed[p_name] == p_value) & (self.log_data_file_collapsed.FinalOutcome == 'Won') & (
        #         self.log_data_file_collapsed.decision == decision) & (
        #         self.log_data_file_collapsed.gameStage == game_stage)].equity.values.tolist()
        # equity_loss = self.log_data_file_collapsed[
        #     (self.log_data_file_collapsed[p_name] == p_value) & (self.log_data_file_collapsed.FinalOutcome == 'Lost') & (
        #         self.log_data_file_collapsed.decision == decision) & (
        #         self.log_data_file_collapsed.gameStage == game_stage)].equity.values.tolist()
        equity_win=[0]
        equity_loss=[0]
        return [equity_win, equity_loss]

    def get_game_count(self, strategy):
        y=self.get_fundschange_chart(strategy)
        return len(y)

    def get_strategy_total_funds_change(self, strategy, days):
        y=self.get_fundschange_chart(strategy)
        return sum(y[-days:])

    def get_fundschange_chart(self,strategy):
        try:
            cursor = self.mongodb.games.aggregate([
                {"$match": {"Template": strategy}},
                {"$group": {
                    "_id": None,
                    "FinalFundsChange": {"$push": "$FinalFundsChange"}
                }}
            ])
            y = list(cursor)[0]['FinalFundsChange']
        except:
            y=[0]
        return y

    def get_strategy_list(self):
        return list(self.mongodb.games.distinct("Template"))

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

