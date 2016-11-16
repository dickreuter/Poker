# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'help.ui'
#
# Created by: PyQt5 UI code generator 5.5.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_help_form(object):
    def setupUi(self, help_form):
        help_form.setObjectName("help_form")
        help_form.resize(427, 355)
        self.textBrowser = QtWidgets.QTextBrowser(help_form)
        self.textBrowser.setEnabled(False)
        self.textBrowser.setGeometry(QtCore.QRect(10, 30, 401, 301))
        self.textBrowser.setObjectName("textBrowser")

        self.retranslateUi(help_form)
        QtCore.QMetaObject.connectSlotsByName(help_form)

    def retranslateUi(self, help_form):
        _translate = QtCore.QCoreApplication.translate
        help_form.setWindowTitle(_translate("help_form", "Form"))
        self.textBrowser.setHtml(_translate("help_form", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">For a start please make sure of the following:</p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><br /></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- Use Partypoker standard setup. Currently the bot only works on tables with 6 people and where the bot is always sat at the bottom right.</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- Put the partypoker client (inside the VM) and the bot outside the VM. Put them next to each other so that the bot can see the full table of Partypoker.</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- In setup choose Direct Mouse Control. It will then take direct screenshots and move the mouse. If that works, you can try with direct VM control.</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- Start with a table like Supersonic2 on Partypoker where the stakes are low</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- In the stragegy editor create a copy of a Supersonic2 strategy and edit it yourself so that you win.</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">- The bot may not work with playmoney as it\'s optomised on small stakes to read the numbers correctly.</p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><br /></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">Please contact me on google hangout under dickreuter@gmail.com if you want to contribute to the project.</p></body></html>"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    help_form = QtWidgets.QWidget()
    ui = Ui_help_form()
    ui.setupUi(help_form)
    help_form.show()
    sys.exit(app.exec_())

