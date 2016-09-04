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

        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": p_value,
                        "FinalOutcome": "Won",
                        "rounds.round_values.gameStage": game_stage,
                        "rounds.round_values.decision": decision}},
            {"$group": {
                "_id": "$GameID",
                "FinalFundsChange": {"$last": "$FinalFundsChange"},
                "equity": {"$last": "$rounds.round_values.equity"},
            }
            },
            {"$project": {"equity": 1, "_id": 0}},
        ])
        equity_win = [d['equity'] for d in cursor]

        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": p_value,
                        "FinalOutcome": "Lost",
                        "rounds.round_values.gameStage": game_stage,
                        "rounds.round_values.decision": decision}},
            {"$group": {
                "_id": "$GameID",
                "FinalFundsChange": {"$last": "$FinalFundsChange"},
                "equity": {"$last": "$rounds.round_values.equity"},
            }
            },
            {"$project": {"equity": 1, "_id": 0}},
        ])

        equity_loss = [d['equity'] for d in cursor]

        equity_win= [float(i) for i in equity_win]
        equity_loss=[float(i) for i in equity_loss]

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

        wins=pd.DataFrame(list(self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": p_value,
                        "FinalOutcome": "Won",
                        "rounds.round_values.gameStage": game_stage,
                        "rounds.round_values.decision": decision}},
            {"$group": {
                "_id": "$GameID",
                "FinalFundsChange": {"$last": "$FinalFundsChange"},
                "equity": {"$last": "$rounds.round_values.equity"},
                "minCall": {"$last": "$rounds.round_values.minCall"},
            }
            },
            {"$project": {
                "equity": 1,
                "FinalFundsChange": 1,
                "minCall": 1,
                "_id": 0}},
        ])))

        losses=pd.DataFrame(list(self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": p_value,
                        "FinalOutcome": "Lost",
                        "rounds.round_values.gameStage": game_stage,
                        "rounds.round_values.decision": decision}},
            {"$group": {
                "_id": "$GameID",
                "FinalFundsChange": {"$last": "$FinalFundsChange"},
                "equity": {"$last": "$rounds.round_values.equity"},
                "minCall": {"$last": "$rounds.round_values.minCall"},
            }
            },
            {"$project": {
                "equity": 1,
                "FinalFundsChange": 1,
                "minCall": 1,
                "_id": 0}},
        ])))

        wins=wins if len(wins)>0 else pd.DataFrame(columns=['FinalFundsChange','equity','minCall'],data=[[0,0,0]])
        losses = losses if len(losses) > 0 else pd.DataFrame(columns=['FinalFundsChange','equity','minCall'],data=[[0,0,0]])
        return [wins, losses]

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

