pyside-uic GUI_QT_ui.ui -o GUI_QT_ui.py -x
pyside-uic GUI_QT_ui_analyser.ui -o GUI_QT_ui_analyser.py -x
pyside-uic gui_qt_ui_genetic_algorithm.ui -o gui_qt_ui_genetic_algorithm.py -x

sed -i -- 's/PySide/PyQt4/g' *.py
