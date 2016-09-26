from unittest import TestCase
from . import main
from PIL import Image
from mongo_manager import StrategyHandler
from unittest.mock import MagicMock
import numpy as np
import logging

class TestTableScreenBased(TestCase):
    def test_game_number(self):
        t=main.TableScreenBased(gui_signals,logger)
        t.entireScreenPIL=Image.open('tests/1773793_PreFlop_0.png')
        t.get_top_left_corner(p)
        t.get_game_number_on_screen()
        self.assertEqual(t.game_number_on_screen,"15,547,039,153")

    def test_other_players1(self):
        p = StrategyHandler()
        p.read_strategy()
        t = main.TableScreenBased(gui_signals,logger)
        t.entireScreenPIL = Image.open('tests/1773793_PreFlop_0.png')
        t.get_top_left_corner(p)
        t.get_dealer_position()
        t.init_get_other_players_info()
        t.get_other_player_names()
        t.get_other_player_funds()
        t.get_other_player_pots()
        t.get_other_player_status(p)

        self.assertEqual(t.position_utg_plus,0)
        self.assertEqual(t.dealer_position, 3)
        self.assertEqual(np.isnan(t.first_raiser), True)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players['0']['utg_position'], 1)
        self.assertEqual(t.other_players['1']['utg_position'], 2)
        self.assertEqual(t.other_players['2']['utg_position'], 3)
        self.assertEqual(t.other_players['3']['utg_position'], 4)
        self.assertEqual(t.other_players['4']['utg_position'], 5)

    def test_other_players2(self):
        p = StrategyHandler()
        p.read_strategy()
        t = main.TableScreenBased(gui_signals,logger)
        t.entireScreenPIL = Image.open('tests/751235173_PreFlop_0.png')
        t.get_top_left_corner(p)
        t.get_dealer_position()
        t.init_get_other_players_info()
        t.get_other_player_names()
        t.get_other_player_funds()
        t.get_other_player_pots()
        t.get_other_player_status(p)

        self.assertEqual(t.position_utg_plus, 5)
        self.assertEqual(t.dealer_position, 4)
        self.assertEqual(t.first_raiser, 3)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players['0']['utg_position'], 0)
        self.assertEqual(t.other_players['1']['utg_position'], 1)
        self.assertEqual(t.other_players['2']['utg_position'], 2)
        self.assertEqual(t.other_players['3']['utg_position'], 3)
        self.assertEqual(t.other_players['4']['utg_position'], 4)


    def test_other_players3(self):
        gui_signals = MagicMock()
        p = StrategyHandler()
        p.read_strategy()
        t = main.TableScreenBased(gui_signals,logger)
        t.entireScreenPIL = Image.open('tests/691119677_PreFlop_0.png')
        t.get_top_left_corner(p)
        t.get_dealer_position()
        t.init_get_other_players_info()
        t.get_other_player_names()
        t.get_other_player_funds()
        t.get_other_player_pots()
        t.get_other_player_status(p)

        self.assertEqual(t.position_utg_plus, 2)
        self.assertEqual(t.dealer_position, 1)
        self.assertEqual(t.first_raiser_utg, 0)
        self.assertEqual(t.first_caller_utg, 1)

        self.assertEqual(t.other_players['0']['utg_position'], 3)
        self.assertEqual(t.other_players['1']['utg_position'], 4)
        self.assertEqual(t.other_players['2']['utg_position'], 5)
        self.assertEqual(t.other_players['3']['utg_position'], 0)
        self.assertEqual(t.other_players['4']['utg_position'], 1)

LOG_FILENAME = 'testing.log'
logger=logger = logging.getLogger('tester')
p = MagicMock()
gui_signals = MagicMock()