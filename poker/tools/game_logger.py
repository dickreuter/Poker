import datetime
import os
import threading

import pandas as pd
import numpy as np
from collections import Iterable

from pymongo import MongoClient

from poker.tools.singleton import Singleton


class GameLogger(object, metaclass=Singleton):
    def __init__(self):
        self.mongo_client = MongoClient(f'mongodb://neuron_poker:donald@dickreuter.com/neuron_poker')
        self.mongodb = self.mongo_client.neuron_poker

        self.FinalDataFrame = None

    def clean_database(self):
        if os.environ['COMPUTERNAME'] == 'NICOLAS-ASUS' or os.environ['COMPUTERNAME'] == 'Home-PC-ND':
            # self.mongodb.rounds.remove({})
            self.mongodb.collusion.remove({})

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

        for key, val in p.selected_strategy.items():
            pDict[key] = val
        for key, val in vars(h).items():
            hDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(t).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val))) < 50:
                tDict[key] = " ".join(str(ele) for ele in self.isIterable(val))
        for key, val in vars(d).items():
            if len(" ".join(str(ele) for ele in self.isIterable(val))) < 20:
                dDict[key] = " ".join(str(ele) for ele in self.isIterable(val))

        pDict['computername'] = os.environ['COMPUTERNAME']

        Dh = pd.DataFrame(hDict, index=[0])
        Dt = pd.DataFrame(tDict, index=[0])
        Dd = pd.DataFrame(dDict, index=[0])
        Dp = pd.DataFrame(pDict, index=[0])

        self.FinalDataFrame = pd.concat([Dd, Dt, Dh, Dp], axis=1)
        rec = self.FinalDataFrame.to_dict('records')[0]
        rec['other_players'] = t.other_players
        rec['logging_timestamp'] = datetime.datetime.utcnow()
        del rec['_id']
        self.mongodb.rounds.insert_one(rec)

    def mark_last_game(self, t, h, p):
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
        if h.histGameStage != '':

            summary_dict = dict()
            summary_dict['rounds'] = []
            i = 0
            cursor = self.mongodb.rounds.find({"GameID": h.lastGameID})
            for _round in cursor:
                round_name_value = dict()
                round_name_value['round_number'] = str(i)
                round_name_value['round_values'] = _round
                summary_dict['rounds'].append(round_name_value)
                i += 1

            summary_dict['GameID'] = h.lastGameID
            summary_dict['ComputerName'] = os.environ['COMPUTERNAME']
            summary_dict['logging_timestamp'] = str(datetime.datetime.now())
            summary_dict['FinalOutcome'] = outcome
            summary_dict['FinalStage'] = h.histGameStage
            summary_dict['FinalFundsChange'] = t.myFundsChange
            summary_dict['FinalFundsChangeABS'] = abs(t.myFundsChange)
            summary_dict['FinalDecision'] = h.histDecision
            summary_dict['FinalEquity'] = h.histEquity
            summary_dict['Template'] = t.current_strategy
            summary_dict['software_version'] = t.version
            summary_dict['ip'] = t.ip

            if abs(t.myFundsChange) <= float(p.selected_strategy['max_abs_fundchange']):
                t_write_db = threading.Thread(name='write_mongo', target=self.mongodb.games.insert_one,
                                              args=[summary_dict])
                t_write_db.daemon = True
                t_write_db.start()
                # result = self.mongodb.games.insert_one(summary_dict)

    def upload_collusion_data(self, gamenumber, mycards, p, gamestage):
        package = {'gamenumber': gamenumber, 'cards': mycards, 'computername': os.environ['COMPUTERNAME'],
                   'strategy': p.current_strategy, 'timestamp': datetime.datetime.utcnow(), 'gamestage': gamestage}
        t_write_db = threading.Thread(name='write_collusion', target=self.mongodb.collusion.insert_one, args=[package])
        t_write_db.daemon = True
        t_write_db.start()

    def get_collusion_cards(self, gamenumber, gamestage):
        gamenumber_part = gamenumber
        computername = os.environ['COMPUTERNAME']
        cursor = self.mongodb.collusion.find(
            {"gamenumber": {"$regex": gamenumber_part}, "computername": {"$ne": computername}})
        record = {}
        player_dropped_out = False

        try:
            for document in cursor:
                record[document['gamestage']] = document['cards']

            if gamestage in record:
                collusion_cards = record[gamestage]
            else:
                player_dropped_out = True
                collusion_cards = record['PreFlop']
        except:
            collusion_cards = ''
        return collusion_cards, player_dropped_out

    def get_neural_training_data(self):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": ".*"},
                        "software_version": {"$gte": 1.85}
                        }},
            {"$project":
                {
                    "advice_fold": "$rounds.round_values.fold_advice",
                    "advice_call": "$rounds.round_values.call_advice",
                    "advice_raise": "$rounds.round_values.raise_advice",

                    "equity": "$rounds.round_values.equity",
                    "total_pot": "$rounds.round_values.totalPotValue",
                    "min_call": "$rounds.round_values.minCall",
                    "min_bet": "$rounds.round_values.minBet",

                    "_id": 0}}
        ])

        result = [d for d in cursor]

        return result

    def get_stacked_bar_data(self, p_name, p_value, chartType):
        final_data = []
        d = dict()
        outcomes = ['Won', 'Lost']
        gameStages = ['PreFlop', 'Flop', 'Turn', 'River']
        decisions = ['Bet Bluff', 'Check Deception', 'Call Deception', 'Fold', 'Check', 'Call', 'Bet', 'BetPlus',
                     'Bet half pot', 'Bet pot']

        for outcome in outcomes:
            for gameStage in gameStages:
                for decision in decisions:
                    d[decision, gameStage, outcome] = 0

        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": p_value}}},
            {"$group": {
                "_id": {"GameID": "$GameID", "gameStage": "$rounds.round_values.gameStage"},
                "lastDecision": {"$last": "$rounds.round_values.decision"},
                "FinalOutcome": {"$last": "$FinalOutcome"},
                "FinalFundsChange": {"$last": "$FinalFundsChange"},
            }
            },
            {"$group": {
                "_id": {"ld": "$lastDecision", "fa": "$FinalOutcome", "gs": "$_id.gameStage"},
                "Total": {"$sum": "$FinalFundsChange"}}}
        ])

        for e in cursor:
            d[e['_id']['ld'], e['_id']['gs'], e['_id']['fa']] = abs(e['Total'])

        numbers = [[d['Call', 'PreFlop', 'Lost'], d['Call', 'Flop', 'Lost'], d['Call', 'River', 'Lost'],
                    d['Bet', 'Flop', 'Lost'], d['Bet', 'Turn', 'Lost'], d['Bet', 'River', 'Lost'],
                    d['Bet half pot', 'Turn', 'Lost'], d['Bet half pot', 'River', 'Lost'],
                    d['Fold', 'PreFlop', 'Lost'], d['Fold', 'Flop', 'Lost'], d['Fold', 'Turn', 'Lost'],
                    d['Fold', 'River', 'Lost'], d['Call', 'Flop', 'Won'], d['Call', 'Turn', 'Won'],
                    d['Call', 'River', 'Won'], d['Bet', 'Flop', 'Won'], d['Bet', 'Turn', 'Won'],
                    d['Bet', 'River', 'Won'], d['Bet half pot', 'Turn', 'Won'],
                    d['Bet half pot', 'River', 'Won'], 0, 0, 0, 0]]

        if chartType == 'spider':
            Data = {
                'column names':
                    ['Call Flop', 'Call Turn', 'Call River', 'Bet Flop', 'Bet Turn', 'Bet River', 'Bet Half Pot Turn',
                     'Bet Half Pot River', 'Fold PreFlop', 'Fold Flop', 'Fold Turn', 'Fold River'],
                'Sum of FinalFundsChangeABS':
                    numbers}

        if chartType == 'stackedBar':
            final_data = [[d['Bet Bluff', 'PreFlop', 'Won'], d['Bet Bluff', 'PreFlop', 'Lost'], 0,
                           d['Bet Bluff', 'Flop', 'Won'] + d['Check Deception', 'Flop', 'Won'] + d[
                               'Call Deception', 'Flop', 'Won'],
                           d['Bet Bluff', 'Flop', 'Lost'] + d['Check Deception', 'Flop', 'Lost'] + d[
                               'Call Deception', 'Flop', 'Lost'], 0, d['Bet Bluff', 'Turn', 'Won'],
                           d['Bet Bluff', 'Turn', 'Lost'], 0, d['Bet Bluff', 'River', 'Won'],
                           d['Bet Bluff', 'River', 'Lost']],
                          [d['Bet pot', 'PreFlop', 'Won'], d['Bet pot', 'PreFlop', 'Lost'], 0,
                           d['Bet pot', 'Flop', 'Won'], d['Bet pot', 'Flop', 'Lost'], 0,
                           d['Bet pot', 'Turn', 'Won'], d['Bet pot', 'Turn', 'Lost'], 0,
                           d['Bet pot', 'River', 'Won'], d['Bet pot', 'River', 'Lost']],
                          [d['Bet half pot', 'PreFlop', 'Won'], d['Bet half pot', 'PreFlop', 'Lost'], 0,
                           d['Bet half pot', 'Flop', 'Won'], d['Bet half pot', 'Flop', 'Lost'], 0,
                           d['Bet half pot', 'Turn', 'Won'], d['Bet half pot', 'Turn', 'Lost'], 0,
                           d['Bet half pot', 'River', 'Won'], d['Bet half pot', 'River', 'Lost']],
                          [d['Bet', 'PreFlop', 'Won'] + d['BetPlus', 'PreFlop', 'Won'],
                           d['Bet', 'PreFlop', 'Lost'] + d['BetPlus', 'PreFlop', 'Lost'], 0,
                           d['Bet', 'Flop', 'Won'] + d['BetPlus', 'Flop', 'Won'],
                           d['Bet', 'Flop', 'Lost'] + d['BetPlus', 'Flop', 'Lost'], 0,
                           d['Bet', 'Turn', 'Won'] + d['BetPlus', 'Turn', 'Won'],
                           d['Bet', 'Turn', 'Lost'] + d['BetPlus', 'Turn', 'Lost'], 0,
                           d['Bet', 'River', 'Won'] + d['BetPlus', 'River', 'Won'],
                           d['Bet', 'River', 'Lost'] + d['BetPlus', 'River', 'Lost']],
                          [d['Call', 'PreFlop', 'Won'], d['Call', 'PreFlop', 'Lost'], 0,
                           d['Call', 'Flop', 'Won'], d['Call', 'Flop', 'Lost'], 0,
                           d['Call', 'Turn', 'Won'], d['Call', 'Turn', 'Lost'], 0,
                           d['Call', 'River', 'Won'], d['Call', 'River', 'Lost']],
                          [d['Check', 'PreFlop', 'Won'], d['Check', 'PreFlop', 'Lost'], 0,
                           d['Check', 'Flop', 'Won'], d['Check', 'Flop', 'Lost'], 0,
                           d['Check', 'Turn', 'Won'], d['Check', 'Turn', 'Lost'], 0,
                           d['Check', 'River', 'Won'], d['Check', 'River', 'Lost']],
                          [0, d['Fold', 'PreFlop', 'Lost'], 0, 0, d['Fold', 'Flop', 'Lost'], 0, 0,
                           d['Fold', 'Turn', 'Lost'], 0, 0, d['Fold', 'River', 'Lost']]]

        return final_data

    def get_histrogram_data(self, p_name, p_value, game_stage, decision):

        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": p_value},
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
            {"$match": {"Template": {"$regex": p_value},
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

        equity_win = [float(i) for i in equity_win]
        equity_loss = [float(i) for i in equity_loss]

        return [equity_win, equity_loss]

    def get_game_count(self, strategy):
        cursor = self.mongodb.games.aggregate([
            {
                "$match":
                    {
                        "Template":
                            {
                                "$regex": strategy
                            }
                    }
            },
            {
                "$group":
                    {
                        "_id": "none",
                        "count": {"$sum": 1}
                    },
            }
        ])

        try:
            games = list(cursor)[0]['count']
        except:
            games = 0

        return games

    def get_strategy_return(self, strategy, days):
        cursor = self.mongodb.games.aggregate([
            {"$match": {"Template": {"$regex": strategy}}},
            {"$sort": {"logging_timestamp": -1}},
            {"$limit": days},
            {
                "$group":
                    {
                        "_id": "none",
                        "FinalFundsChange": {"$sum": "$FinalFundsChange"}
                    },
            }
        ])
        try:
            change = list(cursor)[0]['FinalFundsChange']
        except:
            change = 0
        return change

    def get_fundschange_chart(self, strategy):
        try:
            cursor = self.mongodb.games.aggregate([
                {"$match": {"Template": {"$regex": strategy}}},
                {"$group": {
                    "_id": None,
                    "FinalFundsChange": {"$push": "$FinalFundsChange"}
                }}
            ])
            y = list(cursor)[0]['FinalFundsChange']
        except:
            y = [0]
        return y

    def get_played_strategy_list(self):
        lst = list(self.mongodb.games.distinct("Template"))
        lst.append('.*')
        return lst

    def get_played_players(self):
        return list(self.mongodb.games.distinct("ComputerName"))

    def get_scatterplot_data(self, p_name, p_value, game_stage, decision):

        wins = pd.DataFrame(list(self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": p_value},
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

        losses = pd.DataFrame(list(self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": p_value},
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

        wins = wins if len(wins) > 0 else pd.DataFrame(columns=['FinalFundsChange', 'equity', 'minCall'],
                                                       data=[[0, 0, 0]])
        losses = losses if len(losses) > 0 else pd.DataFrame(columns=['FinalFundsChange', 'equity', 'minCall'],
                                                             data=[[0, 0, 0]])
        return [wins, losses]

    def get_worst_games(self, strategy):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": strategy}}},
            {"$project": {
                "Game Stage": "$rounds.round_values.gameStage",
                "ID": "$GameID",
                "Equity": "$rounds.round_values.equity",
                "Pot": "$rounds.round_values.totalPotValue",
                "Player Funds": "$rounds.round_values.PlayerFunds",
                "Loss": "$FinalFundsChange",
                "Required Call": "$rounds.round_values.minCall",
                "Ending Stage": "$FinalStage",
                "Decision": "$rounds.round_values.decision",
                "_id": 0
            }},
            {"$sort": {"Loss": 1}},
            {"$limit": 99}
        ])
        return pd.DataFrame(list(cursor))

    def optimize_preflop_call_parameters(self, p_name, p_value, game_stage, decision):
        from poker.decisionmaker.curvefitting import Curvefitting
        L = GameLogger()
        df = L.get_neural_training_data(p_name, p_value, game_stage, decision)

        smallBlind = 0.02
        bigBlind = 0.04
        maxValue = 2
        maxEquity = 1
        max_X = 1

        def check_if_below(equity, min_call, final_funds_change):
            x = np.array([float(equity)])
            d = Curvefitting(x, smallBlind, bigBlind, maxValue, minEquity, maxEquity, max_X, pw, pl=False)
            return (np.array([float(min_call)]) < d.y) * final_funds_change

        for pw in np.linspace(1, 5, 5):
            for minEquity in np.linspace(0.55, 0.65, 10):
                s = \
                    df.apply(lambda row: check_if_below(row['equity'], row['min_call'], row['final_funds_change']),
                             axis=1)[
                        'final_funds_change'].sum()
                print(round(minEquity, 2), pw, round(s, 2))

    def get_frequent_player_names(self):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {
                "$match":
                    {
                        "Template": {"$regex": '.*'}
                    },
            },
            {"$group": {
                "_id": {"GameID": "$GameID"},
                "PlayerNames": {"$last": "$rounds.round_values.PlayerNames"},
            }}
        ])
        player_list = list(cursor)

        from collections import Counter
        import operator

        player_list = list(map(lambda d: str(d['PlayerNames']).split(), player_list))
        flat_list = ([item for sublist in player_list for item in sublist])
        counted = Counter(flat_list)
        sorted_dict = sorted(counted.items(), key=operator.itemgetter(1))
        return sorted_dict

    def get_flop_frequency_of_player(self, player_name):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match":
                {
                    "rounds.round_values.PlayerNames": {"$regex": player_name},
                    "FinalStage": {"$ne": "PreFlop"},
                },
            },
            {"$group": {
                "_id": "$rounds.round_values.gameStage",
                "count": {"$sum": 1},
            }}
        ])

        presence = {d["_id"]: d['count'] for d in list(cursor)}
        try:
            flop_presence = presence['Flop'] / presence['PreFlop']
            if presence['PreFlop'] < 10:
                flop_presence = np.nan
        except:
            flop_presence = np.nan
        return flop_presence
