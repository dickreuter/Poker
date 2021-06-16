# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow


class TableSetupForm(QMainWindow):

    def __init__(self):
        super(TableSetupForm, self).__init__()
        uic.loadUi('gui/ui/table_setup_form.ui', self)

        self.show()


class StrategyEditorForm(QMainWindow):

    def __init__(self):
        super(StrategyEditorForm, self).__init__()
        uic.loadUi('gui/ui/strategy_manager_form.ui', self)

        self.show()
        
class MainForm(QMainWindow):
    
    def __init__(self):
        super(MainForm, self).__init__()
        uic.loadUi('gui/ui/main_form.ui', self)

        self.show()
        
class UiPokerbot(QMainWindow):

    def __init__(self):
        super(UiPokerbot, self).__init__()
        uic.loadUi('gui/ui/main_form.ui', self)

        self.show()
