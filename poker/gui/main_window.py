# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow


class UiPokerbot(QMainWindow):

    def __init__(self):
        super(UiPokerbot, self).__init__()
        uic.loadUi('gui/ui/main_form.ui', self)

        self.show()
