"""Operations to help identify items on screen"""
import io
import logging
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageGrab
from pytesseract import pytesseract

from poker.tools.helper import memory_cache
from poker.tools.mongo_manager import MongoManager
from poker.tools.vbox_manager import VirtualBoxController

log = logging.getLogger(__name__)
is_debug = False  # used for saving images for debug purposes


def find_template_on_screen(template, screenshot, threshold):
    """Find template on screen"""
    res = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED)
    loc = np.where(res <= threshold)
    log.debug(f"Looking for template with threshold {threshold}")
    min_val, _, min_loc, _ = cv2.minMaxLoc(res)

    bestFit = min_loc
    count = 0
    points = []
    for pt in zip(*loc[::-1]):
        # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
        count += 1
        points.append(pt)
    return count, points, bestFit, min_val


@memory_cache
def load_table_template_cached(table_name):
    """Load template from mongodb as cv2 image"""
    mongo = MongoManager()
    table = mongo.get_table(table_name=table_name)
    return table


def get_table_template_image(table_name='default', label='topleft_corner'):
    """Load template from mongodb as cv2 image"""
    mongo = MongoManager()
    table = mongo.get_table(table_name=table_name)
    template_pil = Image.open(io.BytesIO(table[label]))
    template_cv2 = cv2.cvtColor(np.array(template_pil), cv2.COLOR_BGR2RGB)
    return template_cv2


def get_ocr_float(img_orig):
    """Return float value from image. -1.0f when OCR failed"""
    return get_ocr_number(img_orig)


def prepareImage(img_orig, binarize=True):
    """Prepare image for OCR"""

    def binarize_array_opencv(image):
        """Binarize image from gray channel with 127 as threshold"""
        img = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2RGB)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, thresh2 = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)
        return Image.fromarray(thresh2)

    basewidth = 300
    wpercent = (basewidth / float(img_orig.size[0]))
    hsize = int((float(img_orig.size[1]) * float(wpercent)))
    img_resized = img_orig.convert('L').resize((basewidth, hsize), Image.ANTIALIAS)
    if binarize:
        img_resized = binarize_array_opencv(img_resized)

    if is_debug:
        pics_path = "log/pics"
        try:
            if not os.path.exists(pics_path):
                os.makedirs(pics_path)
        except OSError:
            log.error("Creation of the directory %s failed" % pics_path)
            sys.exit(1)

        img_orig.save('log/pics/img_orig.png')
        img_resized.save('log/pics/img_resized.png')

        log.debug("ocr images prepared")

    return img_resized


def get_ocr_number(img_orig):
    """Return float value from image. -1.0f when OCR failed"""
    img_resized = prepareImage(img_orig)
    lst = []
    config_ocr = '--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789.$£B'

    lst.append(
        pytesseract.image_to_string(img_resized, 'eng', config=config_ocr).
            strip().replace('$', '').replace('£', '').replace('B', ''))

    try:
        return float(lst[-1])
    except ValueError:
        images = [img_orig, img_resized]  # , img_min, img_mod, img_med, img_sharp]
        i = 0
        while i < 2:
            j = 0
            while j < len(images):
                lst.append(
                    pytesseract.image_to_string(images[j], 'eng', config=config_ocr).
                        strip().replace('$', '').replace('£', '').replace('B', ''))
                j += 1
            config_ocr = '--psm 8 --oem 1 -c tessedit_char_whitelist=0123456789.$£B'
            i += 1

    log.debug(lst)
    for element in lst:
        try:
            return float(element)
        except ValueError:
            pass
    return -1.0


def get_ocr_string(img_orig):
    """Return string value from image."""
    img_resized = prepareImage(img_orig)
    config_ocr = '--psm 7 --oem 1'

    return pytesseract.image_to_string(img_resized, 'eng', config=config_ocr).strip()


def take_screenshot(virtual_box=False):
    """
    Take screenshot directly from screen or via virtualbox

    Args:
        virtual_box: bool

    Returns:
        PIL screenshot

    """
    if not virtual_box:
        log.debug("Calling screen grabber")
        screenshot = ImageGrab.grab()
        log.debug("Direct screenshot successful")

    else:  # virtual_box
        try:
            vb = VirtualBoxController()
            screenshot = vb.get_screenshot_vbox()
            log.debug("Screenshot taken from virtual machine")
        except:
            log.warning("No virtual machine found. Press SETUP to re initialize the VM controller")
            # gui_signals.signal_open_setup.emit(p,L)
            screenshot = ImageGrab.grab()
    return screenshot


def crop_screenshot_with_topleft_corner(original_screenshot, topleft_corner):
    log.debug("Cropping top left corner")
    img = cv2.cvtColor(np.array(original_screenshot), cv2.COLOR_BGR2RGB)
    count, points, _, _ = find_template_on_screen(topleft_corner, img, 0.01)

    if count == 1:
        tlc = points[0]
        log.debug(f"Found to left corner at {tlc}")
        cropped_screenshot = original_screenshot.crop((tlc[0], tlc[1], tlc[0] + 800, tlc[1] + 600))
        return cropped_screenshot, tlc
    else:
        log.warning("No top left corner found")
        return None, None


def binary_pil_to_cv2(img):
    return cv2.cvtColor(np.array(Image.open(io.BytesIO(img))), cv2.COLOR_BGR2RGB)


def pil_to_cv2(img):
    return cv2.cvtColor(np.array(img), cv2.COLOR_BGR2RGB)


def cv2_to_pil(img):
    return Image.fromarray(img)


def check_if_image_in_range(img, screenshot, x1, y1, x2, y2):
    cropped_screenshot = screenshot.crop((x1, y1, x2, y2))
    cropped_screenshot = pil_to_cv2(cropped_screenshot)
    count, _, _, _ = find_template_on_screen(img, cropped_screenshot, 0.01)
    return count >= 1


def is_template_in_search_area(table_dict, screenshot, image_name, image_area, player=None):
    template_cv2 = binary_pil_to_cv2(table_dict[image_name])
    if player:
        search_area = table_dict[image_area][player]
    else:
        search_area = table_dict[image_area]
    return check_if_image_in_range(template_cv2, screenshot,
                                   search_area['x1'], search_area['y1'], search_area['x2'], search_area['y2'])


def ocr(screenshot, image_area, table_dict, player=None):
    """
    get ocr of area of screenshot

    Args:
        screenshot: pil image
        image_area: area name
        table_dict: table dict
        player: player number started from 0

    Returns:
        float

    """
    if player:
        try:
            search_area = table_dict[image_area][player]
        except KeyError:
            log.error(f"Missing table entry for {image_area} {player}. "
                      f"Please select it from the screenshot and press the corresponding button to add it to the "
                      f"table template. ")
            return 0
    else:
        search_area = table_dict[image_area]
    cropped_screenshot = screenshot.crop((search_area['x1'], search_area['y1'], search_area['x2'], search_area['y2']))
    return get_ocr_float(cropped_screenshot)
