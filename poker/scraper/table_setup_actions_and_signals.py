"""Learn to read a table"""
import io
import logging
import time

from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QObject, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from poker.scraper.table_scraper_nn import TRAIN_FOLDER
from poker.tools.helper import COMPUTER_NAME, get_config, get_dir
from poker.tools.mongo_manager import MongoManager
from poker.tools.screen_operations import get_table_template_image, get_ocr_float, take_screenshot, \
    crop_screenshot_with_topleft_corner
from poker.tools.vbox_manager import VirtualBoxController

log = logging.getLogger(__name__)

mongo = MongoManager()

CARD_VALUES = "23456789TJQKA"
CARD_SUITES = "CDHS"


# pylint: disable=unnecessary-lambda

class TableSetupActionAndSignals(QObject):
    """Actions and signals for table logic for QT"""
    signal_update_screenshot_pic = pyqtSignal(object)
    signal_update_label = pyqtSignal(str, str)
    signal_flatten_button = pyqtSignal(str, bool)
    signal_check_box = pyqtSignal(str, int)

    def __init__(self, ui):
        """Initial"""
        super().__init__()
        self.ui = ui
        self.connect_signals_with_slots()
        self.screenshot_clicks = 0

        self.preview = None
        self.table_name = None
        self.original_screenshot = None
        self.screenshot_image = None
        self.x1 = None
        self.x2 = None
        self.y1 = None
        self.y2 = None
        self.top_left_corner_img = None
        self.tlc = None
        self.selected_player = '0'
        self.cropped = False

        available_tables = mongo.get_available_tables(COMPUTER_NAME)
        self.ui.table_name.addItems(available_tables)

    def connect_signals_with_slots(self):
        """Connect signals with slots"""
        self.signal_update_screenshot_pic.connect(self.update_screenshot_pic)
        self.signal_update_label.connect(self._update_label)
        self.signal_flatten_button.connect(self._flatten_button)
        self.signal_check_box.connect(self._check_box)
        self.ui.screenshot_label.mousePressEvent = self.get_position
        self.ui.screenshot_widget.dragEnterEvent = self.drag_enter_event
        self.ui.screenshot_widget.dragMoveEvent = self.drag_move_event
        self.ui.screenshot_widget.dropEvent = self.drop_event
        self.ui.take_screenshot_button.clicked.connect(lambda: self.take_screenshot())
        # self.ui.take_screenshot_cropped_button.clicked.connect(lambda: self.take_screenshot_cropped())
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
        self.ui.current_player.currentIndexChanged[str].connect(lambda: self._update_selected_player())
        self.ui.use_neural_network.stateChanged[int].connect(lambda: self._save_use_nerual_network_checkbox())

    @pyqtSlot()
    def _update_selected_player(self):
        self.selected_player = self.ui.current_player.currentText()
        log.info(f"Updated selected player to {self.selected_player}")

    def _save_use_nerual_network_checkbox(self):
        owner = mongo.get_table_owner(self.table_name)
        if owner != COMPUTER_NAME:
            # pop_up("Not authorized.",
            #        "You can only edit your own tables. Please create a new copy or start with a new blank table")
            return
        label = 'use_neural_network'
        log.info("Saving use neural network tickbox")
        is_set = self.ui.use_neural_network.checkState()
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

    def flatten_button(self, label, checked=True):
        if len(label) == 2:
            button_name = 'card_' + label
        else:
            button_name = label

        if label[0] != '_':
            button = getattr(self.ui, button_name)
            try:
                button.setFlat(checked)
            except AttributeError:
                log.info(f"Ignoring flattening of {button_name}")

            if button_name != 'use_neural_network':
                button = getattr(self.ui, button_name + '_show')
                button.setEnabled(checked)

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
        self.preview = self.original_screenshot.crop((x1, y1, x2, y2))
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

    @pyqtSlot(object)
    def take_screenshot(self):
        """Take a screenshot"""
        log.info("Clearing window")
        self.signal_update_screenshot_pic.emit(Image.new('RGB', (3, 3)))

        log.info("Taking screenshot")
        config = get_config()
        control = config.config.get('main', 'control')
        if control == 'Direct mouse control':
            self.original_screenshot = take_screenshot()

        else:
            try:
                vb = VirtualBoxController()
                self.original_screenshot = vb.get_screenshot_vbox()
                log.debug("Screenshot taken from virtual machine")
            except:
                log.warning("No virtual machine found. Press SETUP to re initialize the VM controller")
                self.original_screenshot = take_screenshot()

        log.info("Emitting update signal")
        self.signal_update_screenshot_pic.emit(self.original_screenshot)
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

    @pyqtSlot(object)
    def update_screenshot_pic(self, screenshot):
        """Update label with screenshot picture"""
        log.info("Convert to to pixmap")
        qim = ImageQt(screenshot).copy()
        self.screenshot_image = QtGui.QPixmap.fromImage(qim)
        log.info("Update screenshot picture")

        self.ui.screenshot_label.setPixmap(self.screenshot_image)
        self.ui.screenshot_label.setStyleSheet('')
        self.ui.screenshot_label.adjustSize()

    def crop(self):
        if not self.original_screenshot:
            pop_up("No screenshot taken yet",
                   "Please take a screenshot first by pressing on the take screenshot button. Then mark a new top "
                   "left corner or load a previously saved one. After that you can crop the image.")
            return
        self.load_topleft_corner()
        log.debug("Cropping top left corner")
        self.original_screenshot, self.tlc = crop_screenshot_with_topleft_corner(self.original_screenshot,
                                                                                 self.top_left_corner_img)
        if self.original_screenshot is None:
            log.warning("No (or multiple) top left corner found")
            pop_up("Top left corner problem: ",
                   "No or multiple top left corners visible. Please ensure only a single top left corner is visible.")
            return
        else:
            self.signal_update_screenshot_pic.emit(self.original_screenshot)
            self.cropped = True

    def load_topleft_corner(self):
        self.table_name = self.ui.table_name.currentText()
        log.info(f"Load top left corner for {self.table_name}")
        try:
            self.top_left_corner_img = get_table_template_image(self.table_name, 'topleft_corner')
        except KeyError:
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
            event.setDropAction(Qt.CopyAction)
            file_path = event.mimeData().urls()[0].toLocalFile()

            self.original_screenshot = Image.open(file_path)
            self.signal_update_screenshot_pic.emit(self.original_screenshot)

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
            self.x2 = x
            self.y2 = y
            if self.x2 > self.x1 and self.y2 > self.y1:
                log.info(f"Clicked on {x}, {y}. Cropping... {(self.x1, self.y1, self.x2, self.y2)}")
                self.preview = self.original_screenshot.crop((self.x1, self.y1, self.x2, self.y2))
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

        check_boxes = ['use_neural_network']
        for check_box in check_boxes:
            try:
                self.signal_check_box.emit(check_box, table[check_box])
            except KeyError:
                log.info(f"No available data for {check_box}")
                self.signal_check_box.emit(check_box, 0)

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

        if 'use_neural_network' in table_dict and table_dict['use_neural_network'] == '2':
            from tensorflow.keras.models import model_from_json
            table_scraper.nn_model = model_from_json(table_dict['_model'])
            mongo.load_table_nn_weights(self.table_name)
            table_scraper.nn_model.load_weights(get_dir('codebase') + '/loaded_model.h5')

        table_scraper.screenshot = self.original_screenshot
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
        log.info("Test finished.")


def pop_up(title, text, details=None, ok_cancel=False):
    msg = QMessageBox()
    msg.setWindowTitle(title)
    msg.setText(text)
    if ok_cancel:
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    if details:
        msg.setDetailedText(details)
    response = msg.exec_()
    log.info(response)
    return response
