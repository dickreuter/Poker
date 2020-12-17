# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow


class AnalyserForm(QMainWindow):

    def __init__(self):
        super(AnalyserForm, self).__init__()
        uic.loadUi('gui/ui/analyser_form.ui', self)

        self.show()
