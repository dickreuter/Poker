# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow


class SetupForm(QMainWindow):
    def __init__(self):
        super(SetupForm, self).__init__()
        uic.loadUi('gui/ui/setup_form.ui', self)

        self.show()
