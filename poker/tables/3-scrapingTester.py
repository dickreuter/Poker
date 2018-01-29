#!/usr/bin/env python

import os

import cv2
import numpy as np
from coordinates_merger import CoordinatesMerger
from poker.tools.mongo_manager import StrategyHandler
from table_tester import MyTableScreenBased


class ScrapingTester():
    def __init__(self, table):
        cm = CoordinatesMerger('../coordinates.json', 'templates/')

        os.chdir('..')

        p = StrategyHandler()
        p.read_strategy('pokerstars')

        t = MyTableScreenBased(cm.getCoordinates()['screen_scraping'], p)
        t.set_screenshot(table)

        testFunctions = {
            t.get_top_left_corner : {'p':p},
            t.get_lost_everything : {'p':p},
            t.check_for_imback : {},
            t.get_my_cards : {},
            t.get_table_cards : {},
            t.check_fast_fold : {'p':p},
            t.check_for_button : {},
            t.get_round_number : {},
            t.init_get_other_players_info : {},
            t.get_other_player_names : {'p':p},
            t.get_other_player_funds : {'p':p},
            t.get_other_player_pots : {},
            t.get_total_pot_value : {},
            t.get_round_pot_value : {},
            t.get_other_player_status : {'p':p},
            t.check_for_checkbutton : {},
            t.check_for_call : {},
            t.check_for_betbutton : {},
            t.check_for_allincall : {},
            t.get_current_call_value : {'p':p},
            t.get_current_bet_value : {'p':p},
            t.get_dealer_position : {},
        }

        for f, parameters in testFunctions.items():
            result = f(**parameters)
            print('|============> '+f.__name__+' <============ : ' +str(result))
            cv2.waitKey()
            cv2.destroyAllWindows()


        os.chdir(os.path.dirname(os.path.realpath(__file__)))


if __name__=='__main__':
    sc = ScrapingTester('PS2')