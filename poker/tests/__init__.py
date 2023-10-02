import inspect
import json
import logging
import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import requests
from PIL import Image

from poker import main
from poker.tools.game_logger import GameLogger
from poker.tools.helper import COMPUTER_NAME, get_config
from poker.tools.mongo_manager import MongoManager
from poker.tools.strategy_handler import StrategyHandler
from poker.tools.update_checker import UpdateChecker

config = get_config()
URL = config.config.get('main', 'db')

currentdir = os.path.dirname(os.path.abspath(
    inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)


def init_table(file, round_number=0, strategy='Default1', table_scraper_name='Official GGPoker 6player'):
    # LOG_FILENAME = 'testing.log'
    logger = logging.getLogger('tester')
    gui_signals = MagicMock()
    p = StrategyHandler()
    p.read_strategy(strategy_override=strategy)
    h = main.History()
    u = UpdateChecker()
    c = requests.post(URL + "get_internal").json()[0]
    preflop_url = c['preflop_url']
    # preflop_url = 'decisionmaker/preflop.xlsx'
    h.preflop_sheet = pd.read_excel(
        preflop_url, sheet_name=None, engine='openpyxl')
    game_logger = GameLogger()
    mongo = MongoManager()
    table_dict = mongo.get_table(table_scraper_name)
    t = main.TableScreenBased(p, {}, gui_signals, game_logger, 0.0)

    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    adjusted_path = os.path.join(current_file_dir, 'screenshots', file)
    t.entireScreenPIL = Image.open(adjusted_path)
    t.get_top_left_corner(p)
    t.get_dealer_position()
    t.get_my_funds(h, p)
    t.get_my_cards_nn()
    # t.get_table_cards_nn(h)
    t.get_round_number(h)
    h.round_number = round_number
    t.init_get_other_players_info()
    t.get_other_player_names(p)
    t.get_other_player_funds(p)
    t.get_other_player_pots()
    t.get_other_player_status(p, h)
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
    return t, p, gui_signals, h, logger
