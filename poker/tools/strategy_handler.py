import datetime
import json
import re
import urllib
from urllib.parse import urlencode

import requests
from configobj import ConfigObj
from fastapi.encoders import jsonable_encoder

from poker.tools.helper import CONFIG_FILENAME

config = ConfigObj(CONFIG_FILENAME)
URL = config['db']


class StrategyHandler:
    def __init__(self):
        self.current_strategy = None
        self.selected_strategy = None
        self.new_strategy_name = None
        self.modified = False

    def get_playable_strategy_list(self):
        lst = requests.post(URL + "get_playable_strategy_list").json()
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

    def read_strategy(self, strategy_override=''):
        config = ConfigObj(CONFIG_FILENAME)
        last_strategy = config['last_strategy']
        self.current_strategy = last_strategy if strategy_override == '' else strategy_override
        try:
            output = requests.post(URL + "find", params={'collection': 'strategies',
                                                         'search_dict': json.dumps({'Strategy':
                                                                                        self.current_strategy})}).json()[
                0]
        except:
            output = requests.post(URL + "find", params={'collection': 'strategies',
                                                         'search_dict': json.dumps({'Strategy':
                                                                                        'Default'})}).json()[0]
        self.selected_strategy = output

        self.check_defaults()
        return self.selected_strategy

    def save_strategy_genetic_algorithm(self):
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
            URL + "save_strategy", json={'strategy': json.dumps(self.selected_strategy)})

    def save_strategy(self, strategy_dict):
        response = requests.post(
            URL + "save_strategy", json={'strategy': json.dumps(strategy_dict)})

    def update_strategy(self, strategy):
        try:
            del strategy['_id']
        except:
            pass
        response = requests.post(
            URL + "update_strategy", json={'name': strategy['Strategy'],
                                             'strategy': json.dumps(strategy)})

    def modify_strategy(self, elementName, change):
        self.selected_strategy[elementName] = str(round(float(self.selected_strategy[elementName]) + change, 2))
        self.modified = True
