# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow


class TableSetupForm(QMainWindow):

    def __init__(self):
        super(TableSetupForm, self).__init__()
        uic.loadUi('gui/ui/table_setup_form.ui', self)

        self.show()
