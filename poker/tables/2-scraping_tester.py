#!/usr/bin/env python

import os

import cv2
import numpy as np
import pandas as pd
from coordinates_merger import CoordinatesMerger
from poker.tools.mongo_manager import (StrategyHandler, UpdateChecker)
from poker import main
from table_tester import MyTableScreenBased


class ScrapingTester():
    def __init__(self, table):
        cm = CoordinatesMerger('../coordinates.json', 'templates/')

        os.chdir('..')

        h = main.History()
        u = UpdateChecker()
        cursor = u.mongodb.internal.find()
        c = cursor.next()
        preflop_url = c['preflop_url']
        h.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None)

        p = StrategyHandler()
        p.read_strategy('pokerstars')

        t = MyTableScreenBased(p)
        t.setCoordinates(cm.getCoordinates()['screen_scraping'])
        t.set_screenshot(table)

        testFunctions = [
            {'func':t.get_top_left_corner, 'params':{'p':p}},
            {'func':t.get_lost_everything, 'params':{'p':p}},
            {'func':t.check_for_imback, 'params':{}},
            {'func':t.get_my_cards, 'params':{}},
            {'func':t.get_my_funds, 'params':{'p':p}},
            {'func':t.get_table_cards, 'params':{}},
            # {'func':t.check_fast_fold, 'params':{'p':p, 'h':h}},
            {'func':t.check_for_button, 'params':{}},
            {'func':t.get_round_number, 'params':{}},
            {'func':t.init_get_other_players_info, 'params':{}},
            {'func':t.get_other_player_names, 'params':{'p':p}},
            {'func':t.get_other_player_funds, 'params':{'p':p}},
            {'func':t.get_other_player_pots, 'params':{}},
            {'func':t.get_total_pot_value, 'params':{}},
            {'func':t.get_round_pot_value, 'params':{}},
            {'func':t.get_other_player_status, 'params':{'p':p}},
            {'func':t.check_for_checkbutton, 'params':{}},
            {'func':t.check_for_call, 'params':{}},
            {'func':t.check_for_betbutton, 'params':{}},
            {'func':t.check_for_allincall, 'params':{}},
            {'func':t.get_current_call_value, 'params':{'p':p}},
            {'func':t.get_current_bet_value, 'params':{'p':p}},
            {'func':t.get_dealer_position, 'params':{}},
        ]


        for f in testFunctions:
            print()
            print('|============> '+f['func'].__name__+' <============ : ')
            result = f['func'](**f['params'])
            print('result ==> '+str(result))
            cv2.waitKey()
            cv2.destroyAllWindows()


        os.chdir(os.path.dirname(os.path.realpath(__file__)))


if __name__=='__main__':
    table = 'PS2'
    userTable = input("Which table do you want to test ? (PS2)")
    if len(userTable):
        table = userTable
    sc = ScrapingTester(table)