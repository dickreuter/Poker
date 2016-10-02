from unittest.mock import MagicMock
from mongo_manager import StrategyHandler
import logging
from PIL import Image
import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
import main


def init_table(file):
    LOG_FILENAME = 'testing.log'
    logger = logging.getLogger('tester')
    gui_signals = MagicMock()
    p = StrategyHandler()
    p.read_strategy()
    h = main.History()
    t = main.TableScreenBased(gui_signals, logger)
    t.entireScreenPIL = Image.open(file)
    t.get_top_left_corner(p)
    t.get_dealer_position()
    t.get_table_cards(h)
    t.init_get_other_players_info()
    t.get_other_player_names(p)
    t.get_other_player_funds(p)
    t.get_other_player_pots()
    t.get_other_player_status(p,h)
    p = MagicMock()
    gui_signals = MagicMock()
    return t,p,gui_signals,h,logger



