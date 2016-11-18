'''
Functions that are used to log and analyse present and past pokergames
'''
import pandas as pd
import numpy as np
from pymongo import MongoClient
from collections import Iterable
import os
from configobj import ConfigObj
import re
import datetime
import sys
import subprocess
import requests
import threading


class UpdateChecker():
    def __init__(self):
        self.mongoclient = MongoClient('mongodb://guest:donald@52.201.173.151:27017/POKER')
        self.mongodb = self.mongoclient.POKER

    def downloader(self):
        self.file_name = "Pokerbot_installer.exe"
        with open(self.file_name, "wb") as f:
            print("Downloading %s" % self.file_name)
            response = requests.get(self.dl_link, stream=True)
            total_length = response.headers.get('content-length')

            if total_length is None:  # no content length header
                f.write(response.content)
            else:
                dl = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    done = int(50 * dl / total_length)
                    sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50 - done)))
                    sys.stdout.flush()

    def check_update(self, version):
        cursor = self.mongodb.internal.find()
        c = cursor.next()
        current_version = c['current_version']
        self.dl_link = c['dl']
        latest_updates = c['latest_updates']
        if current_version > version:
            print("Downloading latest version of the DeepMind Pokerbot...")
            print("\n")
            print("Version changes:")
            for latest_update in latest_updates:
                print("* " + latest_update)
            print("\n")
            self.downloader()
            subprocess.call(["start", self.file_name], shell=True)
            sys.exit()

    def get_preflop_sheet_url(self):
        cursor = self.mongodb.internal.find()
        c = cursor.next()
        self.preflop_url = c['preflop_url']
        # self.preflop_url='decisionmaker/preflop.xlsx'
        return self.preflop_url


class StrategyHandler(object):
    def __init__(self):
        self.mongoclient = MongoClient('mongodb://guest:donald@52.201.173.151:27017/POKER')
        self.mongodb = self.mongoclient.POKER

    def get_playable_strategy_list(self):
        l = list(self.mongodb.strategies.distinct("Strategy"))[::-1]
        return l

    def check_defaults(self):
        if not 'initialFunds2' in self.selected_strategy: self.selected_strategy['initialFunds2'] =  self.selected_strategy['initialFunds']
        if not 'use_relative_equity' in self.selected_strategy: self.selected_strategy['use_relative_equity'] = 0
        if not 'use_pot_multiples' in self.selected_strategy: self.selected_strategy['use_pot_multiples'] = 0
        if not 'opponent_raised_without_initiative_flop' in self.selected_strategy: self.selected_strategy['opponent_raised_without_initiative_flop'] = 1
        if not 'opponent_raised_without_initiative_turn' in self.selected_strategy: self.selected_strategy['opponent_raised_without_initiative_turn'] = 1
        if not 'opponent_raised_without_initiative_river' in self.selected_strategy: self.selected_strategy['opponent_raised_without_initiative_river'] = 1
        if not 'always_call_low_stack_multiplier' in self.selected_strategy: self.selected_strategy[
            'always_call_low_stack_multiplier'] = 8
        if not 'differentiate_reverse_sheet' in self.selected_strategy: self.selected_strategy[
            'differentiate_reverse_sheet'] = 1
        if not 'out_multiplier' in self.selected_strategy: self.selected_strategy['out_multiplier'] = 0
        if not 'FlopBluffMaxEquity' in self.selected_strategy: self.selected_strategy['FlopBluffMaxEquity'] = 100
        if not 'TurnBluffMaxEquity' in self.selected_strategy: self.selected_strategy['TurnBluffMaxEquity'] = 100
        if not 'RiverBluffMaxEquity' in self.selected_strategy: self.selected_strategy['RiverBluffMaxEquity'] = 100
        if not 'flop_betting_condidion_1' in self.selected_strategy: self.selected_strategy[
            'flop_betting_condidion_1'] = 1
        if not 'turn_betting_condidion_1' in self.selected_strategy: self.selected_strategy[
            'turn_betting_condidion_1'] = 1
        if not 'river_betting_condidion_1' in self.selected_strategy: self.selected_strategy[
            'river_betting_condidion_1'] = 1
        if not 'flop_bluffing_condidion_1' in self.selected_strategy: self.selected_strategy[
            'flop_bluffing_condidion_1'] = 1
        if not 'turn_bluffing_condidion_1' in self.selected_strategy: self.selected_strategy[
            'turn_bluffing_condidion_1'] = 0
        if not 'turn_bluffing_condidion_2' in self.selected_strategy: self.selected_strategy[
            'turn_bluffing_condidion_2'] = 1
        if not 'river_bluffing_condidion_1' in self.selected_strategy: self.selected_strategy[
            'river_bluffing_condidion_1'] = 0
        if not 'river_bluffing_condidion_2' in self.selected_strategy: self.selected_strategy[
            'river_bluffing_condidion_2'] = 1
        if not 'collusion' in self.selected_strategy: self.selected_strategy['collusion'] = 1

        if not 'max_abs_fundchange' in self.selected_strategy: self.selected_strategy['max_abs_fundchange'] = 4
        if not 'RiverCheckDeceptionMinEquity' in self.selected_strategy: self.selected_strategy[
            'RiverCheckDeceptionMinEquity'] = .1
        if not 'TurnCheckDeceptionMinEquity' in self.selected_strategy: self.selected_strategy[
            'TurnCheckDeceptionMinEquity'] = .1
        if not 'pre_flop_equity_reduction_by_position' in self.selected_strategy: self.selected_strategy[
            'pre_flop_equity_reduction_by_position'] = 0.01
        if not 'pre_flop_equity_increase_if_bet' in self.selected_strategy: self.selected_strategy[
            'pre_flop_equity_increase_if_bet'] = 0.20
        if not 'pre_flop_equity_increase_if_call' in self.selected_strategy: self.selected_strategy[
            'pre_flop_equity_increase_if_call'] = 0.10
        if not 'preflop_override' in self.selected_strategy: self.selected_strategy['preflop_override'] = 1
        if not 'gather_player_names' in self.selected_strategy: self.selected_strategy['gather_player_names'] = 0
        if not 'range_utg0' in self.selected_strategy: self.selected_strategy['range_utg0'] = 0.2
        if not 'range_utg1' in self.selected_strategy: self.selected_strategy['range_utg1'] = 0.2
        if not 'range_utg2' in self.selected_strategy: self.selected_strategy['range_utg2'] = 0.2
        if not 'range_utg3' in self.selected_strategy: self.selected_strategy['range_utg3'] = 0.2
        if not 'range_utg4' in self.selected_strategy: self.selected_strategy['range_utg4'] = 0.2
        if not 'range_utg5' in self.selected_strategy: self.selected_strategy['range_utg5'] = 0.2
        if not 'range_multiple_players' in self.selected_strategy: self.selected_strategy[
            'range_multiple_players'] = 0.2
        if not 'minimum_bet_size' in self.selected_strategy: self.selected_strategy['minimum_bet_size'] = 3

    def read_strategy(self, strategy_override=''):
        config = ConfigObj("config.ini")
        last_strategy = (config['last_strategy'])
        self.current_strategy = last_strategy if strategy_override == '' else strategy_override
        try:
            cursor = self.mongodb.strategies.find({'Strategy': self.current_strategy})
            self.selected_strategy = cursor.next()
        except:
            cursor = self.mongodb.strategies.find({'Strategy': "Default"})
            self.selected_strategy = cursor.next()
        self.check_defaults()
        return self.selected_strategy

    def save_strategy_genetic_algorithm(self):
        r = re.compile("([a-zA-Z]+)([0-9]+)")
        m = r.match(self.current_strategy)
        stringPart = m.group(1)
        numberPart = int(m.group(2))
        numberPart += 1
        suffix = "_" + str(datetime.datetime.now())
        self.new_strategy_name = stringPart + str(numberPart) + suffix
        self.selected_strategy['Strategy'] = self.new_strategy_name
        self.current_strategy = self.new_strategy_name
        del self.selected_strategy['_id']
        result = self.mongodb.strategies.insert_one(self.selected_strategy)

    def save_strategy(self, strategy_dict):
        del strategy_dict['_id']
        result = self.mongodb.strategies.insert_one(strategy_dict)

    def update_strategy(self, strategy):
        try:
            del strategy['_id']
        except:
            pass
        result = self.mongodb.strategies.update_one(
            {"Strategy": strategy['Strategy']},
            {"$set": strategy}
        )

    def create_new_strategy(self, strategy):
        result = self.mongodb.strategies.insert_one(strategy)

    def modify_strategy(self, elementName, change):
        self.selected_strategy[elementName] = str(round(float(self.selected_strategy[elementName]) + change, 2))
        self.modified = True


class GameLogger(object):
    def __init__(self, connection='mongodb://guest:donald@52.201.173.151:27017/POKER'):
        self.mongoclient = MongoClient('mongodb://guest:donald@52.201.173.151:27017/POKER')
        self.mongodb = self.mongoclient.POKER

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
        result = self.mongodb.rounds.insert_one(rec)

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
            for round in cursor:
                round_name_value = dict()
                round_name_value['round_number'] = str(i)
                round_name_value['round_values'] = round
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
        package = {}
        package['gamenumber'] = gamenumber
        package['cards'] = mycards
        package['computername'] = os.environ['COMPUTERNAME']
        package['strategy'] = p.current_strategy
        package['timestamp'] = datetime.datetime.utcnow()
        package['gamestage'] = gamestage
        t_write_db = threading.Thread(name='write_collusion', target=self.mongodb.collusion.insert_one, args=[package])
        t_write_db.daemon = True
        t_write_db.start()

    def get_collusion_cards(self, gamenumber, gamestage):
        gamenumber_part = gamenumber[-7:]
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

    def get_neural_training_data(self, p_name, p_value, game_stage, decision):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match": {"Template": {"$regex": "snowie1"},
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

        self.d = dict()
        self.outcomes = ['Won', 'Lost']
        self.gameStages = ['PreFlop', 'Flop', 'Turn', 'River']
        self.decisions = ['Bet Bluff', 'Check Deception', 'Call Deception', 'Fold', 'Check', 'Call', 'Bet', 'BetPlus',
                          'Bet half pot', 'Bet pot']

        for outcome in self.outcomes:
            for gameStage in self.gameStages:
                for decision in self.decisions:
                    self.d[decision, gameStage, outcome] = 0

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
            self.d[e['_id']['ld'], e['_id']['gs'], e['_id']['fa']] = abs(e['Total'])

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
                         [self.d['Bet pot', 'PreFlop', 'Won'], self.d['Bet pot', 'PreFlop', 'Lost'], 0,
                          self.d['Bet pot', 'Flop', 'Won'], self.d['Bet pot', 'Flop', 'Lost'], 0,
                          self.d['Bet pot', 'Turn', 'Won'], self.d['Bet pot', 'Turn', 'Lost'], 0,
                          self.d['Bet pot', 'River', 'Won'], self.d['Bet pot', 'River', 'Lost']],
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
            {"$match": {"Template": {"$regex": strategy}}},
            {"$group": {
                "_id": "none",
                "count": {"$sum": 1}},
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
            {"$group": {
                "_id": "none",
                "FinalFundsChange": {"$sum": "$FinalFundsChange"}},
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
        l = list(self.mongodb.games.distinct("Template"))
        l.append('.*')
        return l

    def get_played_players(self):
        l = list(self.mongodb.games.distinct("ComputerName"))
        return l

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
        L = GameLogger()
        df = L.get_neural_training_data(p_name, p_value, game_stage, decision)

        from decisionmaker.curvefitting import Curvefitting

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
            {"$match":
                 {"Template": {"$regex": '.*'}},
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

    def get_flop_frequency_of_player(self, playername):
        cursor = self.mongodb.games.aggregate([
            {"$unwind": "$rounds"},
            {"$match":
                 {"rounds.round_values.PlayerNames": {"$regex": playername},
                  "FinalStage": {"$ne": "PreFlop"},
                  },
             },
            {"$group": {
                "_id": "$rounds.round_values.gameStage",
                "count": {"$sum": 1},
            }}
        ])

        precence = {d["_id"]: d['count'] for d in list(cursor)}
        try:
            flop_presence = precence['Flop'] / precence['PreFlop']
            if precence['PreFlop'] < 10:
                flop_presence = np.nan
        except:
            flop_presence = np.nan
        return flop_presence


if __name__ == '__main__':
    p_name = 'Template'
    p_value = '.*'
    # game_stage = 'Turn'
    # decision = 'Bet'
    # t1=(7, 15, 9)
    # t2=(0.5, 0.6, 10)
    game_stage = 'PreFlop'
    decision = 'Call'
    t1 = (1, 5, 5)
    t2 = (0.55, 0.65, 10)

    L = GameLogger()
    # #L.optimize_preflop_call_parameters(p_name, p_value, game_stage, decision)
    # player_list = L.get_frequent_player_names()
    # print (player_list[-10:])
    #
    # print(L.get_flop_frequency_of_player('MMHRIHM'))
    # print(L.get_flop_frequency_of_player('Mnanqn1no'))
    # print(L.get_flop_frequency_of_player('Annv'))
    # print(L.get_flop_frequency_of_player('7UDILI'))
    # print(L.get_flop_frequency_of_player('hfqq'))
    #
    #
    # worst_games=L.get_worst_games('.(')

    strategy_return = L.get_strategy_return('.*', 500)
    print("Return: " + str(strategy_return))
