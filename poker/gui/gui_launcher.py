from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QDialog


class AnalyserForm(QMainWindow):

    def __init__(self):
        super(AnalyserForm, self).__init__()
        uic.loadUi('gui/ui/analyser_form.ui', self)

        self.show()


class TableSetupForm(QMainWindow):

    def __init__(self):
        super(TableSetupForm, self).__init__()
        uic.loadUi('gui/ui/table_setup_form.ui', self)

        self.show()


class SetupForm(QMainWindow):
    def __init__(self):
        super(SetupForm, self).__init__()
        uic.loadUi('gui/ui/setup_form.ui', self)

        self.show()


class StrategyEditorForm(QMainWindow):

    def __init__(self):
        super(StrategyEditorForm, self).__init__()
        uic.loadUi('gui/ui/strategy_manager_form.ui', self)

        self.show()


class GeneticAlgo(QDialog):

    def __init__(self):
        super(GeneticAlgo, self).__init__()
        uic.loadUi('gui/ui/genetic_algo_form.ui', self)
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
