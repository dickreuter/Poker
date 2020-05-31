"""Tests for tablbe setup"""
import os

import cv2
import numpy as np
from PIL import Image

from poker.scraper.recognize_table import TableScraper
from poker.scraper.screen_operations import find_template_on_screen, get_table_template_image, \
    crop_screenshot_with_topleft_corner
from poker.tools.helper import get_dir
from poker.tools.mongo_manager import MongoManager


def test_cropping():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), 'screenshot1.png'))
    top_left_corner = get_table_template_image('default', 'topleft_corner')
    img = cv2.cvtColor(np.array(entire_screen_pil), cv2.COLOR_BGR2RGB)
    count, points, bestfit, minimum_value = find_template_on_screen(top_left_corner, img, 0.01)


def test_crop_func():
    entire_screen_pil = Image.open(os.path.join(get_dir('tests', 'screenshots'), 'screenshot1.png'))
    top_left_corner = get_table_template_image('default', 'topleft_corner')
    cropped = crop_screenshot_with_topleft_corner(entire_screen_pil, top_left_corner)
    assert cropped


def test_table_scraper():
    mongo = MongoManager()
    table_dict = mongo.get_table('default')
    table_scraper = TableScraper(table_dict)
    table_scraper.screenshot = Image.open(os.path.join(get_dir('tests', 'screenshots'), 'screenshot1.png'))
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
    table_scraper.get_game_number_on_screen2()
