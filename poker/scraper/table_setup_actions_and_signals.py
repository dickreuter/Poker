"""Learn to read a table"""
import io
import logging
import os
import pathlib
import time

from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt, QObject, pyqtSlot, pyqtSignal, QTimer, QCoreApplication
from PyQt6.QtWidgets import QMessageBox, QSlider

from poker.tools import constants as const
from poker.scraper.table_scraper_nn import TRAIN_FOLDER
from poker.tools.helper import COMPUTER_NAME, get_config, get_dir
from poker.tools.mongo_manager import MongoManager
from poker.tools.screen_operations import get_table_template_image, get_ocr_float, take_screenshot, \
    crop_screenshot_with_topleft_corner, check_cropping, normalize_rect
from poker.tools.vbox_manager import VirtualBoxController

log = logging.getLogger(__name__)

mongo = MongoManager()

CARD_VALUES = "23456789TJQKA"
CARD_SUITES = "CDHS"


# pylint: disable=unnecessary-lambda


class TableSetupActionAndSignals(QObject):
    """Actions and signals for table logic for QT"""
    signal_update_screenshot_pic = pyqtSignal(int)
    signal_update_label = pyqtSignal(str, str)
    signal_flatten_button = pyqtSignal(str, bool)
    signal_check_box = pyqtSignal(str, int)
    signal_set_dropdown = pyqtSignal(str, int)

    def __init__(self, ui):
        """Initial"""
        super().__init__()
        self.ui = ui
        self.connect_signals_with_slots()
        self.screenshot_clicks = 0

        self.preview = None
        self.table_name = None
        self.screenshot_image = None
        self.x1 = None
        self.x2 = None
        self.y1 = None
        self.y2 = None
        self.top_left_corner_img = None
        self.tlc = None
        self.selected_player = '0'
        self.cropped = False
        self.nth_second = 1
        self.x_times = 1
        self.selected_screenshot_idx = -1
        self.is_recording = False
        self.append_screenshots = True
        available_tables = mongo.get_available_tables(COMPUTER_NAME)
        self.ui.table_name.addItems(available_tables)

        self.screenshot_list = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.take_screenshot_guard)

        self.ui.screenshot_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ui.screenshot_slider.setMinimum(-1)
        self.ui.screenshot_slider.setMaximum(-1)

    def connect_signals_with_slots(self):
        """Connect signals with slots"""
        self.signal_update_screenshot_pic.connect(self.update_screenshot_pic)
        self.signal_update_label.connect(self._update_label)
        self.signal_flatten_button.connect(self._flatten_button)
        self.signal_check_box.connect(self._check_box)
        self.signal_set_dropdown.connect(self._set_dropdown)
        self.ui.screenshot_label.mousePressEvent = self.get_position
        self.ui.screenshot_widget.dragEnterEvent = self.drag_enter_event
        self.ui.screenshot_widget.dragMoveEvent = self.drag_move_event
        self.ui.screenshot_widget.dropEvent = self.drop_event
        self.ui.take_screenshot_button.clicked.connect(lambda: self.take_screenshot_timed())
        self.ui.screenshot_slider.valueChanged.connect(lambda v: self.show_screenshot_at_slider_pos(v))
        self.ui.test_all_button.clicked.connect(lambda: self.test_all())
        self._connect_cards_with_save_slot()
        self._connect_range_buttons_with_save_coordinates()
        self.ui.blank_new.clicked.connect(lambda: self.blank_new())
        self.ui.copy_to_new.clicked.connect(lambda: self.copy_to_new())
        self.ui.crop.clicked.connect(lambda: self.crop())
        self.ui.load.clicked.connect(lambda: self.load())
        self.ui.train_model.clicked.connect(lambda: self.train_model())
        self.ui.button_delete.clicked.connect(lambda: self.delete())
        self.ui.tesseract.clicked.connect(lambda: self._recognize_number())
        self.ui.topleft_corner.clicked.connect(lambda: self.save_topleft_corner())
        self.ui.current_player.currentIndexChanged[int].connect(lambda: self._update_selected_player())
        self.ui.use_neural_network.clicked.connect(lambda: self._save_use_nerual_network_checkbox())
        self.ui.max_players.currentIndexChanged[int].connect(lambda: self._save_max_players())
        self.ui.spinBox_nthSecond.valueChanged.connect(lambda: self._update_nth_second())
        self.ui.spinBox_xTimes.valueChanged.connect(lambda: self._update_x_times())
        self.ui.load_screenshots_button.clicked.connect(lambda: self.load_screenshots())
        self.ui.save_screenshots_button.clicked.connect(lambda: self.save_screenshots())
        self.ui.append_checkbox.stateChanged.connect(lambda state: self.set_append(state))

    def load_screenshots(self):
        folder_str = QtWidgets.QFileDialog.getExistingDirectory(None, 'Select Folder')
        if folder_str != "":
            try:
                folder_path = pathlib.Path(folder_str)
                files = [pathlib.Path.joinpath(folder_path, f) for f in os.listdir(folder_str) if
                         os.path.isfile(pathlib.Path.joinpath(folder_path, f))]
                pngs = [f for f in files if pathlib.Path(f).suffix == ".png"]
                images = [Image.open(png) for png in pngs]

                self.load_topleft_corner()
                new_cropped = check_cropping(images, self.top_left_corner_img)
                
                if len(self.screenshot_list) == 0:
                    self.cropped =  new_cropped
                else:
                    self.cropped =  self.cropped and new_cropped

                if not self.cropped: 
                    log.info("Images are not cropped or do not fit to the loaded template.")

                if self.append_screenshots:
                    self.screenshot_list.extend(images)
                else:
                    self.screenshot_list = images
                    self.cropped = False

                

                self.update_ui_with_screenshot_amount(len(self.screenshot_list))
            except Exception as e:
                log.error("Error loading screenshots")
                log.exception(e)
                pop_up("Error", "Loading screenshots failed.")

    def save_screenshots(self):
        folder_str = QtWidgets.QFileDialog.getExistingDirectory(None, 'Select Folder')
        if folder_str != "":
            try:
                folder_path = pathlib.Path(folder_str)
                files = [pathlib.Path.joinpath(folder_path, f) for f in os.listdir(folder_str) if
                         os.path.isfile(pathlib.Path.joinpath(folder_path, f))]
                max_index = self.get_max_file_index(files)
                for i in range(0, len(self.screenshot_list)):
                    self.screenshot_list[i].save("{0}\\screenshot_{1:04}.png".format(folder_str, max_index + 1 + i))

                pop_up("Saving screenshots", "Saving screenshots finished.")
            except Exception as e:
                log.error("Error saving screenshots")
                log.exception(e)
                pop_up("Error", "Saving screenshots failed.")

    def int_try_parse(self, value):
        try:
            return int(value), True
        except ValueError:
            return value, False

    def get_max_file_index(self, files):
        pngs = [f for f in files if pathlib.Path(f).suffix == ".png"]
        if len(pngs) == 0: return 0

        names = [pathlib.Path(f).stem for f in pngs]
        split = [n.split("_") for n in names if len(n.split("_")) > 1]
        if len(split) == 0: return 0

        split = [pathlib.Path(s[1]).stem for s in split]
        indices = [int(i) for i in split if self.int_try_parse(i)]
        if len(indices) > 0:
            return max(indices)
        else:
            0

    def set_append(self, state):
        self.append_screenshots = state == 2

    @pyqtSlot(int)
    def show_screenshot_at_slider_pos(self, value):
        log.debug("Slider position: " + str(value))
        log.debug("screenshot_list length: " + str(len(self.screenshot_list)))

        self.selected_screenshot_idx = value

        if len(self.screenshot_list) > 0 \
           and self.selected_screenshot_idx < len(self.screenshot_list):
            self.signal_update_screenshot_pic.emit(self.selected_screenshot_idx)

    @pyqtSlot()
    def _update_x_times(self):
        self.x_times = self.ui.spinBox_xTimes.value()
        log.info("Amount of screenshots to take: " + str(self.x_times))

    @pyqtSlot()
    def _update_nth_second(self):
        self.nth_second = self.ui.spinBox_nthSecond.value()
        log.info("Take screenshot every " + str(self.nth_second) + "s")

    @pyqtSlot()
    def _update_selected_player(self):
        self.selected_player = self.ui.current_player.currentText()
        log.info(f"Updated selected player to {self.selected_player}")

    def _save_max_players(self):
        label = 'max_players'
        self.table_name = self.ui.table_name.currentText()
        owner = mongo.get_table_owner(self.table_name)
        if owner != COMPUTER_NAME:
            pop_up("Not authorized.",
                   "You can only edit your own tables. Please create a new copy or start with a new blank table")
            return
        log.info(f"Saving {label}")
        mongo.save_coordinates(self.table_name, label, {'value': int(self.ui.max_players.currentText())})
        log.info("Saving complete")

    def _save_use_nerual_network_checkbox(self):
        owner = mongo.get_table_owner(self.table_name)
        if owner != COMPUTER_NAME:
            pop_up("Not authorized.",
                   "You can only edit your own tables. Please create a new copy or start with a new blank table")
            return
        label = 'use_neural_network'
        is_set = self.ui.use_neural_network.checkState()
        log.info(f"Saving use neural network tickbox {is_set}")
        mongo.update_state(state=is_set, label=label, table_name=self.table_name)
        log.info("Saving complete")

    def _connect_cards_with_save_slot(self):
        # contains cards in the deck
        deck = [x.lower() + y.lower() for x in CARD_VALUES for y in CARD_SUITES]

        for card in deck:
            button_property = getattr(self.ui, 'card_' + card)
            button_property.clicked.connect(lambda state, x=card: self.save_image(x))

            button_show_property = getattr(self.ui, 'card_' + card + '_show')
            button_show_property.clicked.connect(lambda state, x=card: self.load_image(x))

        save_image_buttons = ['call_button', 'raise_button', 'bet_button', 'check_button', 'fold_button',
                              'fast_fold_button',
                              'all_in_call_button',
                              'my_turn',
                              'lost_everything', 'im_back', 'resume_hand', 'dealer_button', 'covered_card']
        for button in save_image_buttons:
            button_property = getattr(self.ui, button)
            button_property.clicked.connect(lambda state, x=button: self.save_image(x))

            button_show_property = getattr(self.ui, button + '_show')
            button_show_property.clicked.connect(lambda state, x=button: self.load_image(x))

        button_show_property = getattr(self.ui, 'dealer_button_show')
        button_show_property.clicked.connect(lambda state: self.load_image('dealer_button'))

        button_show_property = getattr(self.ui, 'covered_card_show')
        button_show_property.clicked.connect(lambda state: self.load_image('covered_card'))

    def _connect_range_buttons_with_save_coordinates(self):
        range_buttons = [
            'call_value', 'raise_value', 'all_in_call_value', 'game_number', 'current_round_pot',
            'total_pot_area', 'my_turn_search_area', 'lost_everything_search_area',
            'table_cards_area', 'my_cards_area', 'buttons_search_area',
            'mouse_fold', 'mouse_fast_fold', 'mouse_raise', 'mouse_full_pot', 'mouse_call',
            'mouse_increase', 'mouse_call2', 'mouse_check', 'mouse_imback',
            'mouse_half_pot', 'mouse_all_in', 'mouse_resume_hand',
            'left_card_area', 'right_card_area'
        ]

        for button in range_buttons:
            button_property = getattr(self.ui, button)
            button_property.clicked.connect(lambda state, x=button: self.save_coordinates(x))

            button_show_property = getattr(self.ui, button + '_show')
            button_show_property.clicked.connect(lambda state, x=button: self.show_coordinates(x))

        # range buttons for each players
        range_buttons = ['covered_card_area', 'player_name_area', 'player_funds_area', 'player_pot_area',
                         'button_search_area']
        for button in range_buttons:
            button_property = getattr(self.ui, button)
            button_property.clicked.connect(lambda state, x=button: self.save_coordinates(x, self.selected_player))

            button_show_property = getattr(self.ui, button + '_show')
            button_show_property.clicked.connect(lambda state, x=button: self.show_coordinates(x, self.selected_player))

    def save_topleft_corner(self):
        self.table_name = self.ui.table_name.currentText()
        log.info(f"Load top left corner for {self.table_name}")
        try:
            self.top_left_corner_img = get_table_template_image(self.table_name, 'topleft_corner')
            resp = pop_up("Are you sure?",
                          "You already defined a top left corner for this table before. "
                          "You will need to enter all buttons (but not images) again if you have already saved"
                          "coordinates for any other items.",
                          ok_cancel=True)
            if resp == 1024:
                self.save_image('topleft_corner')
        except KeyError:
            # no top left corner yet, continue
            self.save_image('topleft_corner')

    @pyqtSlot(object, str)
    def save_image(self, label):
        if not self.preview:
            pop_up("Mark an image first.",
                   "Before you can save an image, you need to take a screenshot (with the take screenshot button),"
                   "Then you need to mark the top left corner of the poker window (or load a previously saved one)"
                   "After that an image needs to be marked by clicking on the top left and then bottom right corner "
                   "of that image.")
            return

        log.info(f"flattening button {label}")
        self.signal_flatten_button.emit(label, True)

        self.table_name = self.ui.table_name.currentText()
        owner = mongo.get_table_owner(self.table_name)
        if owner != COMPUTER_NAME:
            pop_up("Not authorized.",
                   "You can only edit your own tables. Please create a new copy or start with a new blank table")
            return
        log.info(f"Saving {label}")
        mongo.update_table_image(pil_image=self.preview, label=label, table_name=self.table_name)
        log.info("Saving complete")

    @pyqtSlot(object, str)
    def load_image(self, label):
        self.table_name = self.ui.table_name.currentText()
        log.info(f"Loading {label}")
        self.preview = mongo.load_table_image(image_name=label, table_name=self.table_name)
        self._update_preview_label(self.preview)
        log.info("Loading complete")

    @pyqtSlot(str, bool)
    def _flatten_button(self, label, checked):
        self.flatten_button(label, checked)

    @pyqtSlot(str, int)
    def _check_box(self, label, checked):
        checkbox = getattr(self.ui, label)
        checkbox.setChecked(checked)

    @pyqtSlot(str, int)
    def _set_dropdown(self, label, index):
        dropdown = getattr(self.ui, label)
        dropdown.setCurrentIndex(index)

    def flatten_button(self, label, checked=True):
        if len(label) == 2:
            button_name = 'card_' + label
        else:
            button_name = label

        if label[0] != '_':
            try:
                button = getattr(self.ui, button_name)
                button.setFlat(checked)
            except AttributeError:
                log.info(f"Ignoring flattening of {button_name}")

            if button_name != 'use_neural_network':
                try:
                    button = getattr(self.ui, button_name + '_show')
                    button.setEnabled(checked)
                except:
                    pass

    def blank_new(self):
        ok = mongo.create_new_table(self.ui.new_name.text())
        if ok:
            self.ui.table_name.addItems([self.ui.new_name.text()])
            self.ui.table_name.setCurrentIndex(self.ui.table_name.count() - 1)
        else:
            pop_up("Unable to create new table with that name", "Please choose a different name.")

    def copy_to_new(self):
        ok = mongo.create_new_table_from_old(self.ui.new_name.text(), self.ui.table_name.currentText())
        if ok:
            self.ui.table_name.addItems([self.ui.new_name.text()])
            self.ui.table_name.setCurrentIndex(self.ui.table_name.count() - 1)
        else:
            pop_up("Unable to create new table with that name", "Please choose a different name.")

    @pyqtSlot(object, str, str)
    def show_coordinates(self, label, player=None):
        if not self.cropped:
            pop_up("Image not yet cropped",
                   "Before you can load image by coordinates, "
                   "you need to mark or load a top left corner, then crop the image.")
            return

        self.table_name = self.ui.table_name.currentText()
        table_dict = mongo.get_table(table_name=self.table_name)
        if player:
            try:
                search_area = table_dict[label][player]
            except KeyError:
                log.error(f"Missing table entry for {label} {player}. "
                          f"Please select it from the screenshot and press the corresponding button to add it to the "
                          f"table template. ")
                return
        else:
            search_area = table_dict[label]

        x1, y1, x2, y2 = search_area['x1'], search_area['y1'], search_area['x2'], search_area['y2']
        self.preview = self.screenshot_list[self.selected_screenshot_idx].crop((x1, y1, x2, y2))
        log.info("image cropped")
        self._update_preview_label(self.preview)

    @pyqtSlot(object, str, str)
    def save_coordinates(self, label, player=None):
        if not self.cropped:
            pop_up("Image not yet cropped",
                   "Before you can mark coordinates, you need to mark or load a top left corner, then crop the image.")
            return

        if self.x1 > self.x2 or self.y1 > self.y2:
            pop_up("Invalid coordinates",
                   "Top left corner of image is more to the right/bottom the lower right coordinates, try again.")
            return

        self.table_name = self.ui.table_name.currentText()

        log.info(f"Saving coordinates for {label} with coordinates {self.x1, self.y1, self.x2, self.y2}")
        owner = mongo.get_table_owner(self.table_name)

        if owner != COMPUTER_NAME:
            pop_up("Not authorized.",
                   "You can only edit your own tables. Please create a new copy or start with a new blank table")
            return

        if player:
            label = label + '.' + player
        mongo.save_coordinates(self.table_name, label, {'x1': self.x1, 'y1': self.y1, 'x2': self.x2, 'y2': self.y2})

    def take_screenshot_timed(self):
        if not self.is_recording:
            self.is_recording = True
        else:
            self.is_recording = False
            self.timer.stop()
            self.ui.take_screenshot_button.setText("Take screenshot")
            return

        # Take first screenshot immediately
        self.screenshot_list = []
        self.ui.screenshot_slider.setMinimum(-1)
        self.ui.screenshot_slider.setMaximum(-1)

        self.take_screenshot()
        if self.x_times == 1:
            self.is_recording = False
            pop_up("Information", "Screenshots finished")
            return

        log.info("Starting screenshot loop")
        self.timer.start(self.nth_second * 1000)

    def take_screenshot_guard(self):

        if len(self.screenshot_list) == self.x_times:
            self.timer.stop()
            self.ui.take_screenshot_button.setText("Take screenshot")
            self.is_recording = False
            pop_up("Information", "Screenshots finished")
        elif len(self.screenshot_list) < self.x_times:
            self.take_screenshot()
            self.ui.take_screenshot_button.setText("Cancel (" + str(self.x_times + 1 - len(self.screenshot_list)) + ")")
        else:
            # shouldn't be reached
            self.timer.stop()
            self.is_recording = False
            log.debug("Timer race condition?")

    def take_screenshot(self):
        """Take a screenshot"""
        log.info("Clearing window")

        # avoid having a screenshot of the form containing a screenshot of the poker window icon.
        self.ui.preview_label.clear()
        self.ui.screenshot_label.clear()
        QCoreApplication.processEvents()

        log.info("Taking screenshot")
        config = get_config()
        control = config.config.get('main', 'control')
        if control == 'Direct mouse control':
            self.screenshot_list.append(take_screenshot())
        else:
            try:
                vb = VirtualBoxController()
                self.screenshot_list.append(vb.get_screenshot_vbox())
                log.debug("Screenshot taken from virtual machine")
            except:
                log.warning("No virtual machine found. Press SETUP to re initialize the VM controller")
                self.screenshot_list.append(take_screenshot())

        # log.info("Screenshots taken: " + str(len(self.screenshot_list)))
        log.info("Emitting update signal")
        self.update_ui_with_screenshot_amount(len(self.screenshot_list))
        log.info("signal emission complete")

    @pyqtSlot(object)
    def take_screenshot_cropped(self):
        """Take a screenshot"""
        log.info("Clearing window")
        self.signal_update_screenshot_pic.emit(Image.new('RGB', (3, 3)))
        time.sleep(3)  # todo: this is not working, the screen is not cleared before the full function completes

        log.info("Taking screenshot")
        self.original_screenshot = take_screenshot()

        log.info("Emitting update signal")
        self.signal_update_screenshot_pic.emit(self.original_screenshot)
        log.info("signal emission complete")

        self.crop()

    @pyqtSlot(int)
    def update_screenshot_pic(self, index):
        """Update label with screenshot picture"""

        log.debug("Convert to to pixmap")
        qim = ImageQt(self.screenshot_list[index]).copy()
        self.screenshot_image = QtGui.QPixmap.fromImage(qim)
        log.debug("Update screenshot picture")
        self.ui.screenshot_label.setStyleSheet("")
        self.ui.screenshot_label.setPixmap(self.screenshot_image)

    @pyqtSlot(int)
    def update_ui_with_screenshot_amount(self, amount):
        log.debug("update_screenshot_slider: " + str(amount))
        self.ui.screenshot_slider.setMinimum(0)
        self.ui.screenshot_slider.setMaximum(amount - 1)
        self.ui.screenshot_slider.setValue(amount - 1)

    def crop(self):
        if len(self.screenshot_list) == 0:
            pop_up("No screenshot taken yet",
                   "Please take a screenshot first by pressing on the take screenshot button. Then mark a new top "
                   "left corner or load a previously saved one. After that you can crop the image.")
            return
        self.load_topleft_corner()

        log.info("Cropping top left corner of '" + str(len(self.screenshot_list)) + "' images")
        cropped_images = []
        for i in range(len(self.screenshot_list)):
            cropped, self.tlc = crop_screenshot_with_topleft_corner(self.screenshot_list[i],
                                                                    self.top_left_corner_img, False)
            if cropped != None:
                cropped_images.append(cropped)
        
        self.screenshot_list = cropped_images
        if self.tlc is None:
            log.warning("No (or multiple) top left corner found")
            pop_up("Top left corner problem: ",
                   "No or multiple top left corners visible. Please ensure only a single top left corner is visible.")
            return
        else:
            log.debug("Selected idx: " + str(self.selected_screenshot_idx))
            self.signal_update_screenshot_pic.emit(self.selected_screenshot_idx)
            self.cropped = True

    def load_topleft_corner(self):
        self.table_name = self.ui.table_name.currentText()
        log.info(f"Load top left corner for {self.table_name}")
        try:
            self.top_left_corner_img = get_table_template_image(self.table_name, 'topleft_corner')
        except KeyError:
            self.top_left_corner_img = None
            log.error("No top left corner saved yet. "
                      "Please mark a top left corner and click on the save newly selected top left corner.")

    @pyqtSlot()
    def drag_enter_event(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    @pyqtSlot()
    def drag_move_event(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    @pyqtSlot()
    def drop_event(self, event):
        if event.mimeData().hasImage:
            event.setDropAction(Qt.DropAction.CopyAction)
            file_path = event.mimeData().urls()[0].toLocalFile()
            image = Image.open(file_path)
            
            if not self.append_screenshots:
                self.screenshot_list = []

            self.load_topleft_corner()
            new_cropped = check_cropping([image], self.top_left_corner_img)
            
            if len(self.screenshot_list) == 0:
               self.cropped = new_cropped
            else:
               self.cropped = self.cropped and new_cropped
            
            if not self.cropped: 
                    log.info("Images are not cropped or do not fit to the loaded template.")
            
            self.screenshot_list.append(image)

            self.signal_update_screenshot_pic.emit(-1)
            self.update_ui_with_screenshot_amount(len(self.screenshot_list))
            event.accept()
        else:
            event.ignore()

    @pyqtSlot()
    def get_position(self, event):
        """Get position of mouse click"""
        x = event.pos().x()
        y = event.pos().y()
        # if self.cropped:
        #     log.info("Crop adjustment")
        #     y -= 15
        #
        # self.penRectangle = QtGui.QPen(QtCore.Qt.red)
        # self.penRectangle.setWidth(3)
        # self.painterInstance.setPen(self.penRectangle)
        # self.painterInstance.drawRect(x, y, 10, 10)
        # self.ui.screenshot_label.setPixmap(self.screenshot_image)
        # self.ui.screenshot_label.show()
        self.screenshot_clicks += 1
        if self.screenshot_clicks % 2 == 0:
            self.x1, self.y1, self.x2, self.y2 = normalize_rect(self.x1, self.y1, x, y)
            
            if self.x2 > self.x1 and self.y2 > self.y1:
                log.info(f"Clicked on {x}, {y}. Cropping... {(self.x1, self.y1, self.x2, self.y2)}")
                self.preview = self.screenshot_list[self.selected_screenshot_idx].crop(
                    (self.x1, self.y1, self.x2, self.y2))
                log.info("image cropped")
                self._update_preview_label(self.preview)
        else:
            self.x1 = x
            self.y1 = y
            log.info(f"Clicked on {x}, {y}")

    @pyqtSlot(object)
    def _update_preview_label(self, preview):
        """Update preview label with selected picture"""
        log.info("Convert to qim")
        qim = ImageQt(preview).copy()
        log.info("Convert to Qpixmap")
        preview_qim = QtGui.QPixmap.fromImage(qim)
        log.info("Update preview label")

        self.ui.preview_label.setPixmap(preview_qim)
        self.ui.preview_label.adjustSize()

    @pyqtSlot(object)
    def _recognize_number(self):
        self.recognized_number = get_ocr_float(self.preview)
        log.info(f"Recognized number is: {self.recognized_number}")
        self.signal_update_label.emit('tesseract_label', str(self.recognized_number))

    @pyqtSlot(str, str)
    def _update_label(self, item, value):
        func = getattr(self.ui, item)
        log.info(f"Updating label {item} with value {value}")
        func.setText(str(value))

    def delete(self):
        self.table_name = self.ui.table_name.currentText()
        owner = mongo.get_table_owner(self.table_name)
        if owner != COMPUTER_NAME:
            pop_up("Not authorized.",
                   "You can only delete the tables that you created")
            return

        resp = pop_up("Are you sure?",
                      f"Are you sure you want to delete the table {self.table_name}? This cannot be undone.",
                      ok_cancel=True)
        if resp == 1024:
            mongo.delete_table(table_name=self.table_name, owner=COMPUTER_NAME)

    def load(self):
        self.table_name = self.ui.table_name.currentText()

        # unflatten buttons and disable 'show' buttons
        # contains cards in the deck
        deck = [x.lower() + y.lower() for x in CARD_VALUES for y in CARD_SUITES]

        for card in deck:
            log.info(f"UnFlattening button {'card_' + card}")
            self.signal_flatten_button.emit('card_' + card, False)

        all_buttons = ['call_value', 'raise_value', 'all_in_call_value', 'game_number', 'current_round_pot',
                       'total_pot_area', 'my_turn_search_area', 'lost_everything_search_area', 'table_cards_area',
                       'my_cards_area', 'mouse_fold', 'mouse_fast_fold', 'mouse_raise', 'mouse_full_pot', 'mouse_call',
                       'mouse_increase', 'mouse_call2', 'mouse_check', 'mouse_imback', 'mouse_resume_hand',
                       'mouse_half_pot', 'mouse_all_in',
                       'buttons_search_area', 'call_button', 'raise_button', 'bet_button', 'check_button',
                       'fold_button',
                       'fast_fold_button', 'all_in_call_button', 'my_turn', 'lost_everything', 'im_back', 'resume_hand',
                       'dealer_button', 'covered_card', 'covered_card_area', 'player_name_area', 'player_funds_area',
                       'player_pot_area', 'button_search_area', 'covered_card_area', 'player_name_area',
                       'player_funds_area', 'player_pot_area', 'button_search_area', 'left_card_area',
                       'right_card_area']

        for key in all_buttons:
            log.info(f"UnFlattening button {key}")
            self.signal_flatten_button.emit(key, False)

        log.info(f"Loading table {self.table_name}")
        table = mongo.get_table(table_name=self.table_name)
        log.info(table.keys())

        # show topleft_corner image in preview
        self.preview = Image.open(io.BytesIO(table['topleft_corner']))
        self._update_preview_label(self.preview)
        self.load_topleft_corner()

        self.cropped = check_cropping(self.screenshot_list, self.top_left_corner_img)
        if not self.cropped: 
            log.info("Images are not cropped or do not fit to the loaded template.")

        check_boxes = ['use_neural_network']
        for check_box in check_boxes:
            try:
                if isinstance(table[check_box], int):
                    nn = 1 if table[check_box] > 0 else 0
                if isinstance(table[check_box], str):
                    nn = 1 if table[check_box] == 'CheckState.Checked' else 0
                self.signal_check_box.emit(check_box, int(nn))
            except KeyError:
                log.info(f"No available data for {check_box}")
                self.signal_check_box.emit(check_box, 0)

        try:
            all_values = [self.ui.max_players.itemText(i) for i in range(self.ui.max_players.count())]
            index = all_values.index(str(table['max_players']['value']))
            self.ui.max_players.setCurrentIndex(index)
        except KeyError:
            log.warning(f"No available data for 'max_players'")
            self.ui.max_players.setCurrentIndex(0)

        exceptions = ["table_name"]
        players_buttons = ['covered_card_area', 'player_name_area', 'player_funds_area', 'player_pot_area',
                           'button_search_area']

        for key, value in table.items():
            if key in exceptions:
                continue
            if key in players_buttons:
                if str(self.selected_player) in value.keys():
                    log.info(f"Flattening button {key}")
                    self.signal_flatten_button.emit(key, True)
                else:
                    log.info(f"UnFlattening button {key}")
                    self.signal_flatten_button.emit(key, False)
            else:
                log.info(f"Flattening button {key}")
                self.signal_flatten_button.emit(key, True)

    @pyqtSlot()
    def train_model(self):
        self.table_name = self.ui.table_name.currentText()
        log.info(f"Start trainig for {self.table_name}")
        from poker.scraper.table_scraper_nn import CardNeuralNetwork
        n = CardNeuralNetwork()
        log.info(f"Creating augmented images in {TRAIN_FOLDER}")
        n.create_augmented_images(self.table_name)
        log.info(f"You may add additional training images into {TRAIN_FOLDER}. "
                 f"Filename does not matter but make sure they are in the correct folder, "
                 f"so the network knows the correct label.")
        log.info("Note that to speed up training you may want to install cuda and cudnn drivers "
                 "so you can train on a GPU if you have one.")
        input("Press Enter to continue...")
        n.train_neural_network()
        n.save_model_to_disk()
        n.save_model_to_db(self.table_name)

    @pyqtSlot()
    def test_all(self):
        """Test table button"""
        self.table_name = self.ui.table_name.currentText()
        from poker.scraper.table_scraper import TableScraper
        table_dict = mongo.get_table(table_name=self.table_name)

        table_scraper = TableScraper(table_dict)
        table_scraper.nn_model = None

        if 'use_neural_network' in table_dict and (
                table_dict['use_neural_network'] == '2' or table_dict['use_neural_network'] == 'CheckState.Checked'):
            from tensorflow.keras.models import model_from_json
            table_scraper.nn_model = model_from_json(table_dict['_model'])
            mongo.load_table_nn_weights(self.table_name)
            table_scraper.nn_model.load_weights(get_dir('codebase') + '/loaded_model.h5')

        table_scraper.screenshot = self.screenshot_list[self.selected_screenshot_idx]
        table_scraper.crop_from_top_left_corner()
        table_scraper.is_my_turn()
        table_scraper.lost_everything()
        table_scraper.get_my_cards2()
        table_scraper.get_table_cards2()
        table_scraper.get_dealer_position2()
        table_scraper.get_players_in_game()
        table_scraper.get_pots()
        table_scraper.get_players_funds()
        table_scraper.get_player_pots()
        table_scraper.get_call_value()
        table_scraper.get_raise_value()
        table_scraper.has_all_in_call_button()
        table_scraper.has_call_button()
        table_scraper.has_raise_button()
        table_scraper.has_bet_button()
        table_scraper.has_check_button()
        log.info("Test finished.")


def pop_up(title, text, details=None, ok_cancel=False):
    msg = QMessageBox()
    msg.setWindowTitle(title)
    msg.setText(text)
    if ok_cancel:
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    if details:
        msg.setDetailedText(details)
    response = msg.exec()
    log.info(response)
    return response
