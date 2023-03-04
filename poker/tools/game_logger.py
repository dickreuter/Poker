import datetime
import json
import os
import threading
from collections.abc import Iterable

import pandas as pd
import requests
from fastapi.encoders import jsonable_encoder

from poker.tools.helper import COMPUTER_NAME, get_config
from poker.tools.mongo_manager import MongoManager
from poker.tools.singleton import Singleton

config = get_config()
URL = config.config.get('main', 'db')


class GameLogger(metaclass=Singleton):
    def __init__(self):
        self.d = {}  # TODO: refactor it
        self.FinalDataFrame = None

    def isIterable(self, x):
        # use str instead of basestring if Python3
        if isinstance(x, Iterable) and not isinstance(x, str):
            return x
        return [x]

    def get_played_strategy_list(self):
        config = get_config()
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        response = requests.post(
            URL + "get_played_strategy_list", params={"login": login,
                                                      "password": password,
                                                      "computer_name": COMPUTER_NAME})
        return response.json()

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
        del rec['logger']
        response = requests.post(
            URL + "insert_round", json={'rec': json.dumps(rec, default=str)})

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

            summary_dict = {'rounds': []}
            i = 0
            mongo = MongoManager()
            rounds = mongo.get_rounds(h.lastGameID)
            for _round in rounds:
                round_name_value = {
                    'round_number': str(i),
                    'round_values': _round
                }
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
                t_write_db = threading.Thread(name='write_mongo', target=self.insert_log,
                                              args=[summary_dict])
                t_write_db.daemon = True
                t_write_db.start()
                # result = self.mongodb.games.insert_one(summary_dict)

    def insert_log(self, rec):
        response = requests.post(
            URL + "insert_games", json={'rec': json.dumps(rec)})

    def insert_collusion(self, rec):
        response = requests.post(
            URL + "insert_collusion", params=jsonable_encoder(rec))

    def upload_collusion_data(self, gamenumber, mycards, p, gamestage):
        package = {'gamenumber': gamenumber, 'cards': mycards, 'computername': os.environ['COMPUTERNAME'],
                   'strategy': p.current_strategy, 'timestamp': datetime.datetime.utcnow(), 'gamestage': gamestage}
        t_write_db = threading.Thread(
            name='write_collusion', target=self.insert_collusion, args=[package])
        t_write_db.daemon = True
        t_write_db.start()

    def get_collusion_cards(self, gamenumber, gamestage):
        computername = os.environ['COMPUTERNAME']
        response = requests.post(URL + "get_collusion_cards", params={'gamenumber': gamenumber, 'gamestage': gamestage,
                                                                      'computrname': computername}).json()
        return response['collusion_cards'], response['player_dropped_out']

    def get_stacked_bar_data(self, p_name, p_value, chartType, last_stage='All', last_action='All'):

        response = requests.post(URL + "get_stacked_bar_data",
                                 params={'p_value': p_value, 'chartType': chartType,
                                         'last_stage': last_stage,
                                         'last_action': last_action}).json()
        data = json.loads(response['d'])
        k = data.keys()
        v = data.values()
        k1 = [eval(i) for i in k]  # pylint: disable=eval-used
        self.d = dict(zip(*[k1, v]))

        return response['final_data']

    def get_stacked_bar_data2(self, p_name, p_value, chartType, last_stage='All', last_action='All',
                              my_computer_only=False):

        computer_name = COMPUTER_NAME if my_computer_only else 'All'

        response = requests.post(URL + "get_stacked_bar_data2",
                                 params={'p_value': p_value, 'chartType': chartType,
                                         'last_stage': last_stage,
                                         'last_action': last_action,
                                         'computer_name': computer_name}).json()

        return pd.DataFrame(json.loads(response))

    def get_histrogram_data(self, p_name, p_value, game_stage, decision, my_computer_only=False):

        response = requests.post(URL + "get_histrogram_data", params={'p_value': p_value, 'game_stage': game_stage,
                                                                      'decision': decision}).json()

        return [response['equity_win'], response['equity_loss']]

    def get_game_count(self, strategy, my_computer_only=False):
        computer_name = COMPUTER_NAME if my_computer_only else 'All'
        response = requests.post(
            URL + "get_game_count", params={'strategy': strategy,
                                            'computer_name': computer_name}).json()
        return response

    def get_strategy_return(self, strategy, days, my_computer_only=False):
        computer_name = COMPUTER_NAME if my_computer_only else 'All'
        response = requests.post(URL + "get_strategy_return", params={'strategy': strategy,
                                                                      'days': days,
                                                                      'computer_name': computer_name}).json()
        return round(float(response), 2)

    def get_fundschange_chart(self, strategy, my_computer_only=False):
        computer_name = COMPUTER_NAME if my_computer_only else 'All'
        response = requests.post(
            URL + "get_fundschange_chart", params={'strategy': strategy,
                                                   'computer_name': computer_name}).json()
        return response

    def get_scatterplot_data(self, p_name, p_value, game_stage, decision):
        response = requests.post(URL + "get_scatterplot_data", params={'p_name': p_name, 'p_value': p_value,
                                                                       'game_stage': game_stage,
                                                                       'decision': decision}).json()

        return [pd.DataFrame(json.loads(response['wins'])), pd.DataFrame(json.loads(response['losses']))]

    def get_worst_games(self, strategy):
        response = requests.post(
            URL + "get_worst_games", params={'strategy': strategy}).json()
        return pd.DataFrame(response)
