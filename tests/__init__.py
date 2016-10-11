import pandas as pd
from unittest.mock import MagicMock
from mongo_manager import StrategyHandler
import logging
from PIL import Image
import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
import main


def init_table(file,round_number=0):
    LOG_FILENAME = 'testing.log'
    logger = logging.getLogger('tester')
    gui_signals = MagicMock()
    p = StrategyHandler()
    p.read_strategy()
    h = main.History()
    h.preflop_sheet = pd.read_excel('https://www.dropbox.com/s/j7o2fje3u6vsu75/preflop.xlsx?dl=1', sheetname=None)
    t = main.TableScreenBased(gui_signals, logger)
    t.entireScreenPIL = Image.open(file)
    t.get_top_left_corner(p)
    t.get_dealer_position()
    t.get_my_funds(h,p)
    t.get_my_cards(h)
    t.get_table_cards(h)
    t.get_round_number(h)
    h.round_number=round_number
    t.init_get_other_players_info()
    t.get_other_player_names(p)
    t.get_other_player_funds(p)
    t.get_other_player_pots()
    t.get_other_player_status(p,h)
    t.check_for_checkbutton()
    t.check_for_call()
    t.check_for_betbutton()
    t.check_for_allincall()
    t.get_current_call_value(p)
    t.get_current_bet_value(p)
    p = MagicMock()
    gui_signals = MagicMock()
    return t,p,gui_signals,h,logger



