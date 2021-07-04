"""Tests for tablbe setup"""
import os

import cv2
import numpy as np
from PIL import Image

from poker.scraper.table_scraper import TableScraper
from poker.tools.helper import get_dir
from poker.tools.mongo_manager import MongoManager
from poker.tools.screen_operations import find_template_on_screen, get_table_template_image, \
    crop_screenshot_with_topleft_corner, get_ocr_float
from poker.tools.screen_operations import ocr


def test_cropping():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), '53269218_PreFlop_0.png'))
    top_left_corner = get_table_template_image("PartyPoker Old", 'topleft_corner')
    img = cv2.cvtColor(np.array(entire_screen_pil), cv2.COLOR_BGR2RGB)
    find_template_on_screen(top_left_corner, img, 0.01)


def test_crop_func():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), '53269218_PreFlop_0.png'))
    top_left_corner = get_table_template_image("PartyPoker Old", 'topleft_corner')
    cropped = crop_screenshot_with_topleft_corner(entire_screen_pil, top_left_corner)
    assert cropped


def test_table_scraper():
    mongo = MongoManager()
    table_dict = mongo.get_table("PartyPoker Old")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '53269218_PreFlop_0.png'))
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
    table_dict = mongo.get_table("Official Party Poker")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '53269218_PreFlop_0.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.03

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.98


def test_ocr_ps1():
    mongo = MongoManager()
    table_dict = mongo.get_table("Official Poker Stars")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), 'ps473830744_Flop_1.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.29

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.04

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.67


def test_ocr_pp4():
    mongo = MongoManager()
    table_dict = mongo.get_table("Official Party Poker")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), '988359671_PreFlop_0.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.03

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.01

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.04

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.95


def test_orc_problems1():
    """Tricky OCR situations"""
    img = Image.open(os.path.join(get_dir('codebase'), r"tests/ocr/num1.png"))
    result = get_ocr_float(img)
    assert result == 3.94


def test_orc_problems2():
    """Tricky OCR situations"""
    img = Image.open(os.path.join(get_dir('codebase'), r"tests/ocr/num2.png"))
    result = get_ocr_float(img)
    assert result == 3.94


def test_ocr_gg():
    mongo = MongoManager()
    table_dict = mongo.get_table("Official GG Poker")
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), 'ggpk6ocr.png'))
    table_scraper.crop_from_top_left_corner()

    result = ocr(table_scraper.screenshot, 'total_pot_area', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'call_value', table_scraper.table_dict)
    assert result == 0.05

    result = ocr(table_scraper.screenshot, 'raise_value', table_scraper.table_dict)
    assert result == 0.08

    result = ocr(table_scraper.screenshot, 'player_funds_area', table_scraper.table_dict, player='0')
    assert result == 1.78
