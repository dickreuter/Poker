"""Tests for tablbe setup"""
import os

import cv2
import numpy as np
from PIL import Image

from poker.scraper.recognize_table import TableScraper
from poker.tools.screen_operations import find_template_on_screen, get_table_template_image, \
    crop_screenshot_with_topleft_corner
from poker.tools.screen_operations import ocr
from poker.tools.helper import get_dir
from poker.tools.mongo_manager import MongoManager


def test_cropping():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), '173280759_PreFlop_0.png'))
    top_left_corner = get_table_template_image("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em", 'topleft_corner')
    img = cv2.cvtColor(np.array(entire_screen_pil), cv2.COLOR_BGR2RGB)
    count, points, bestfit, minimum_value = find_template_on_screen(top_left_corner, img, 0.01)


def test_crop_func():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), '173280759_PreFlop_0.png'))
    top_left_corner = get_table_template_image("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em", 'topleft_corner')
    cropped = crop_screenshot_with_topleft_corner(entire_screen_pil, top_left_corner)
    assert cropped


def test_table_scraper():
    mongo = MongoManager()
    table_dict = mongo.get_table("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '173280759_PreFlop_0.png'))
    table_scraper.crop_from_top_left_corner()
    table_scraper.is_my_turn()
    table_scraper.lost_everything()
    table_scraper.get_my_cards2()
    table_scraper.get_table_cards2()
    table_scraper.get_dealer_position2()
    table_scraper.get_players_in_game()
    table_scraper.get_pots()
    table_scraper.get_players_funds()
    table_scraper.get_call_value()
    table_scraper.get_raise_value()
    table_scraper.has_all_in_call_button()
    table_scraper.has_call_button()
    table_scraper.has_raise_button()


def test_ocr_pp1():
    mongo = MongoManager()
    table_dict = mongo.get_table("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '173280759_PreFlop_0.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.09

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.04

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.1

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.32


def test_ocr_pp2():
    mongo = MongoManager()
    table_dict = mongo.get_table("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '238170361_River_0.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.05

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.02

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.44


def test_ocr_pp3():
    mongo = MongoManager()
    table_dict = mongo.get_table("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '721575070_PreFlop_0.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.03

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.29
