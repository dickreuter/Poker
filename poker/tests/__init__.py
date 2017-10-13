import inspect
import logging
import os
import sys
from unittest.mock import MagicMock

import pandas as pd
from PIL import Image

from poker.tools.mongo_manager import GameLogger
from poker.tools.mongo_manager import StrategyHandler
from poker.tools.mongo_manager import UpdateChecker

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
from poker import main


def init_table(file,round_number=0, strategy='Default1'):
    LOG_FILENAME = 'testing.log'
    logger = logging.getLogger('tester')
    gui_signals = MagicMock()
    p = StrategyHandler()
    p.read_strategy(strategy_override=strategy)
    h = main.History()
    u = UpdateChecker()
    cursor = u.mongodb.internal.find()
    c = cursor.next()
    preflop_url = c['preflop_url']
    h.preflop_sheet = pd.read_excel(preflop_url, sheetname=None)
    game_logger = GameLogger()
    t = main.TableScreenBased(p, gui_signals, game_logger, 0.0)
    t.entireScreenPIL = Image.open(file)
    t.get_top_left_corner(p)
    t.get_dealer_position()
    t.get_my_funds(h,p)
    t.get_my_cards_nn(h)
    t.get_table_cards_nn(h)
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
    t.totalPotValue = 0.5
    t.equity = 0.5
    return t,p,gui_signals,h,logger



