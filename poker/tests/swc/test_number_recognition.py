import os

import cv2
from PIL import Image

from poker.tools.screen_operations import swc_ocr as ocr

is_debug = False  # used for saving images for debug purposes

images = {
    0: {1: {"amount": 40.0},
        2: {"amount": 9.0},
        3: {"amount": 6000.0},
        4: {"amount": 1.0}},
    1: {1: {"amount": 1480.0}},
    2: {1: {"amount": 250.0},
        2: {"amount": 5000.0},
        3: {"amount": 8945.0},
        4: {"amount": 0.5}},
4: {1: {"amount": 2.5},
        "1_no_chips": {"amount": 2.5},
        2: {"amount": 150.0},
        3: {"amount": 2069.16}},
    5: {1: {"amount": 250.0},
        2: {"amount": 0.5}}
}

dirname = os.path.dirname(__file__)
img_dir = os.path.join(dirname, "images")


class TestNumberRecognition():
    def get_img(self, player, num):
        img_path = os.path.join(img_dir,
                                "player" + str(player),
                                str(num) + ".png")
        return Image.open(img_path)

    def test_player0(self):
        player = 0
        num = 1
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player0_2(self):
        player = 0
        num = 2
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player0_3(self):
        player = 0
        num = 3
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player0_4(self):
        player = 0
        num = 4
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player1(self):
        player = 1
        num = 1
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player2(self):
        player = 2
        num = 1
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player2_2(self):
        player = 2
        num = 2
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player2_3(self):
        player = 2
        num = 3
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]


    def test_player2_4(self):
        player = 2
        num = 4
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player4(self):
        player = 4
        num = 1
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player4_no_chips(self):
        player = 4
        num = "1_no_chips"
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player4_2(self):
        player = 4
        self.i = 2
        num = self.i
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player4_3(self):
        player = 4
        num = 3
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]

    def test_player5(self):
        player = 5
        num = 1
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]


    def test_player5_2(self):
        player = 5
        num = 2
        img = self.get_img(player, num)
        assert ocr(img) == images[player][num]["amount"]
