# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'setup.ui'
#
# Created by: PyQt5 UI code generator 5.5.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_setup_form(object):
    def setupUi(self, setup_form):
        setup_form.setObjectName("setup_form")
        setup_form.resize(240, 320)
        setup_form.setMinimumSize(QtCore.QSize(240, 320))
        setup_form.setMaximumSize(QtCore.QSize(240, 320))
        setup_form.setToolTip("")
        self.comboBox_vm = QtWidgets.QComboBox(setup_form)
        self.comboBox_vm.setGeometry(QtCore.QRect(10, 50, 221, 21))
        self.comboBox_vm.setToolTip("<html><head/><body><p>Choose if you want to have direct access to VirtualBox via API or whether the bot should simply move the mouse.</p><p>The dropdown will automatically show all available virtualbox virtualmachines.</p></body></html>")
        self.comboBox_vm.setStatusTip("Statustip")
        self.comboBox_vm.setAccessibleName("")
        self.comboBox_vm.setAccessibleDescription("")
        self.comboBox_vm.setObjectName("comboBox_vm")
        self.comboBox_2 = QtWidgets.QComboBox(setup_form)
        self.comboBox_2.setGeometry(QtCore.QRect(10, 150, 221, 21))
        self.comboBox_2.setToolTip("Shows after how many seconds of discovering the buttons a timeout will be triggered, assuming you have reached the montecarlo simulation by then. ")
        self.comboBox_2.setObjectName("comboBox_2")
        self.label = QtWidgets.QLabel(setup_form)
        self.label.setGeometry(QtCore.QRect(10, 30, 211, 16))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(setup_form)
        self.label_2.setGeometry(QtCore.QRect(10, 130, 111, 16))
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(setup_form)
        self.label_3.setGeometry(QtCore.QRect(10, 230, 81, 16))
        self.label_3.setObjectName("label_3")
        self.lineEdit = QtWidgets.QLineEdit(setup_form)
        self.lineEdit.setGeometry(QtCore.QRect(10, 250, 221, 21))
        self.lineEdit.setToolTip("")
        self.lineEdit.setToolTipDuration(10)
        self.lineEdit.setStatusTip("")
        self.lineEdit.setWhatsThis("More info available later")
        self.lineEdit.setObjectName("lineEdit")
        self.pushButton_save = QtWidgets.QPushButton(setup_form)
        self.pushButton_save.setGeometry(QtCore.QRect(160, 290, 75, 23))
        self.pushButton_save.setObjectName("pushButton_save")

        self.retranslateUi(setup_form)
        QtCore.QMetaObject.connectSlotsByName(setup_form)

    def retranslateUi(self, setup_form):
        _translate = QtCore.QCoreApplication.translate
        setup_form.setWindowTitle(_translate("setup_form", "Setup"))
        self.comboBox_vm.setWhatsThis(_translate("setup_form", "wahtst this"))
        self.label.setText(_translate("setup_form", "Direct Mouse control and Virtual Machines"))
        self.label_2.setText(_translate("setup_form", "Timeout"))
        self.label_3.setText(_translate("setup_form", "Activation Code"))
        self.pushButton_save.setText(_translate("setup_form", "Save"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    setup_form = QtWidgets.QWidget()
    ui = Ui_setup_form()
    ui.setupUi(setup_form)
    setup_form.show()
    sys.exit(app.exec_())

