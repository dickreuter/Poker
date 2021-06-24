import datetime
import json
import logging
import re
import time

import requests

from poker.tools.helper import COMPUTER_NAME, get_config

config = get_config()
URL = config.config.get('main', 'db')

log = logging.getLogger(__name__)


class StrategyHandler:
    def __init__(self):
        self.current_strategy = None
        self.selected_strategy = None
        self.new_strategy_name = None
        self.modified = False

    def get_playable_strategy_list(self):
        config = get_config()
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        lst = requests.post(URL + "get_playable_strategy_list", params={"login": login,
                                                                        "password": password,
                                                                        "computer_name": COMPUTER_NAME}).json()
        return lst

    def check_defaults(self):
        if 'initialFunds2' not in self.selected_strategy:
            self.selected_strategy['initialFunds2'] = self.selected_strategy['initialFunds']
        if 'use_relative_equity' not in self.selected_strategy:
            self.selected_strategy['use_relative_equity'] = 0
        if 'use_pot_multiples' not in self.selected_strategy:
            self.selected_strategy['use_pot_multiples'] = 0
        if 'opponent_raised_without_initiative_flop' not in self.selected_strategy:
            self.selected_strategy['opponent_raised_without_initiative_flop'] = 1
        if 'opponent_raised_without_initiative_turn' not in self.selected_strategy:
            self.selected_strategy['opponent_raised_without_initiative_turn'] = 1
        if 'opponent_raised_without_initiative_river' not in self.selected_strategy:
            self.selected_strategy['opponent_raised_without_initiative_river'] = 1
        if 'always_call_low_stack_multiplier' not in self.selected_strategy:
            self.selected_strategy['always_call_low_stack_multiplier'] = 8
        if 'differentiate_reverse_sheet' not in self.selected_strategy:
            self.selected_strategy['differentiate_reverse_sheet'] = 1
        if 'range_of_range' not in self.selected_strategy:
            self.selected_strategy['range_of_range'] = 0
        if 'out_multiplier' not in self.selected_strategy:
            self.selected_strategy['out_multiplier'] = 0
        if 'FlopBluffMaxEquity' not in self.selected_strategy:
            self.selected_strategy['FlopBluffMaxEquity'] = 100
        if 'TurnBluffMaxEquity' not in self.selected_strategy:
            self.selected_strategy['TurnBluffMaxEquity'] = 100
        if 'RiverBluffMaxEquity' not in self.selected_strategy:
            self.selected_strategy['RiverBluffMaxEquity'] = 100
        if 'flop_betting_condidion_1' not in self.selected_strategy:
            self.selected_strategy['flop_betting_condidion_1'] = 1
        if 'turn_betting_condidion_1' not in self.selected_strategy:
            self.selected_strategy['turn_betting_condidion_1'] = 1
        if 'river_betting_condidion_1' not in self.selected_strategy:
            self.selected_strategy['river_betting_condidion_1'] = 1
        if 'flop_bluffing_condidion_1' not in self.selected_strategy:
            self.selected_strategy['flop_bluffing_condidion_1'] = 1
        if 'turn_bluffing_condidion_1' not in self.selected_strategy:
            self.selected_strategy['turn_bluffing_condidion_1'] = 0
        if 'turn_bluffing_condidion_2' not in self.selected_strategy:
            self.selected_strategy['turn_bluffing_condidion_2'] = 1
        if 'river_bluffing_condidion_1' not in self.selected_strategy:
            self.selected_strategy['river_bluffing_condidion_1'] = 0
        if 'river_bluffing_condidion_2' not in self.selected_strategy:
            self.selected_strategy['river_bluffing_condidion_2'] = 1
        if 'collusion' not in self.selected_strategy:
            self.selected_strategy['collusion'] = 1

        if 'max_abs_fundchange' not in self.selected_strategy:
            self.selected_strategy['max_abs_fundchange'] = 4
        if 'RiverCheckDeceptionMinEquity' not in self.selected_strategy:
            self.selected_strategy['RiverCheckDeceptionMinEquity'] = .1
        if 'TurnCheckDeceptionMinEquity' not in self.selected_strategy:
            self.selected_strategy['TurnCheckDeceptionMinEquity'] = .1
        if 'pre_flop_equity_reduction_by_position' not in self.selected_strategy:
            self.selected_strategy['pre_flop_equity_reduction_by_position'] = 0.01
        if 'pre_flop_equity_increase_if_bet' not in self.selected_strategy:
            self.selected_strategy['pre_flop_equity_increase_if_bet'] = 0.20
        if 'pre_flop_equity_increase_if_call' not in self.selected_strategy:
            self.selected_strategy['pre_flop_equity_increase_if_call'] = 0.10
        if 'preflop_override' not in self.selected_strategy:
            self.selected_strategy['preflop_override'] = 1
        if 'gather_player_names' not in self.selected_strategy:
            self.selected_strategy['gather_player_names'] = 0
        if 'range_utg0' not in self.selected_strategy:
            self.selected_strategy['range_utg0'] = 0.2
        if 'range_utg1' not in self.selected_strategy:
            self.selected_strategy['range_utg1'] = 0.2
        if 'range_utg2' not in self.selected_strategy:
            self.selected_strategy['range_utg2'] = 0.2
        if 'range_utg3' not in self.selected_strategy:
            self.selected_strategy['range_utg3'] = 0.2
        if 'range_utg4' not in self.selected_strategy:
            self.selected_strategy['range_utg4'] = 0.2
        if 'range_utg5' not in self.selected_strategy:
            self.selected_strategy['range_utg5'] = 0.2
        if 'range_multiple_players' not in self.selected_strategy:
            self.selected_strategy['range_multiple_players'] = 0.2
        if 'minimum_bet_size' not in self.selected_strategy:
            self.selected_strategy['minimum_bet_size'] = 3
        if 'antibluff_percentage' not in self.selected_strategy:
            self.selected_strategy['antibluff_percentage'] = 0
        if 'range_preflop' not in self.selected_strategy:
            self.selected_strategy['range_preflop'] = 100
        if 'increased_preflop_betting' not in self.selected_strategy:
            self.selected_strategy['increased_preflop_betting'] = 1

    def read_strategy(self, strategy_override=''):
        config = get_config()
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        last_strategy = config.config.get('main', 'last_strategy')
        self.current_strategy = last_strategy if strategy_override == '' else strategy_override
        try:
            output = requests.post(
                URL + "get_strategy", params={'name': self.current_strategy,
                                              "login": login,
                                              "password": password}).json()[0]
        except:
            log.error(f"This Strategy is not available for this user: {login}")
            time.sleep(1)
            output = requests.post(URL + "get_strategy",
                                   params={'name': 'Default',
                                           "login": 'guest',
                                           "password": 'guest'}).json()[0]
        self.selected_strategy = output

        self.check_defaults()
        return True

    def save_strategy_genetic_algorithm(self):
        config = get_config()
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')

        m = re.search(r'([a-zA-Z?-_]+)([0-9]+)', self.current_strategy)
        stringPart = m.group(1)
        numberPart = int(m.group(2))
        numberPart += 1
        suffix = "_" + str(datetime.datetime.now())
        self.new_strategy_name = stringPart + str(numberPart) + suffix
        self.selected_strategy['Strategy'] = self.new_strategy_name
        self.current_strategy = self.new_strategy_name
        del self.selected_strategy['_id']
        response = requests.post(
            URL + "save_strategy", json={'strategy': json.dumps(self.selected_strategy),
                                         'login': login, 'password': password}).json()
        if response:
            log.info("Saved")
        else:
            log.error("Not allowed to write strategies")

    def save_strategy(self, strategy_dict):
        config = get_config()
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        response = requests.post(
            URL + "save_strategy", json={'strategy': json.dumps(strategy_dict),
                                         'login': login, 'password': password}).json()
        if response:
            log.info("Saved")
            return True
        else:
            log.error("Not allowed to write strategies")
            return False

    def update_strategy(self, strategy):
        try:
            del strategy['_id']
        except:
            pass
        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        response = requests.post(
            URL + "update_strategy", json={'name': strategy['Strategy'],
                                           'strategy': json.dumps(strategy),
                                           'login': login, 'password': password}).json()
        if response:
            log.info("Saved")
            return True
        else:
            log.error("Not allowed to write strategies")
            return False

    def modify_strategy(self, elementName, change):
        self.selected_strategy[elementName] = str(
            round(float(self.selected_strategy[elementName]) + change, 2))
        self.modified = True
