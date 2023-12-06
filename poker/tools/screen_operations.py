"""Operations to help identify items on screen"""
import io
import logging
import os
import sys
from time import sleep

import cv2
import numpy as np
from PIL import Image, ImageGrab
from tesserocr import PyTessBaseAPI, PSM, OEM

from poker.tools.helper import memory_cache, get_dir
from poker.tools import constants as const
from poker.tools.mongo_manager import MongoManager
from poker.tools.vbox_manager import VirtualBoxController

log = logging.getLogger(__name__)
is_debug = False  # used for saving images for debug purposes

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    tesserpath = os.path.join(get_dir('codebase'), 'tessdata')
else:
    tesserpath = os.path.join(get_dir('codebase'), '..', 'tessdata')

api = PyTessBaseAPI(path=tesserpath,
                    psm=PSM.SINGLE_LINE,
                    oem=OEM.LSTM_ONLY)


def find_template_on_screen(template, screenshot, threshold, extended=False):
    """Find template on screen"""
    res = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED)
    loc = np.where(res <= threshold)
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


def get_ocr_float(img_orig, fast=False):
    """Return float value from image. -1.0f when OCR failed"""
    return get_ocr_number(img_orig, fast)


def prepareImage(img_orig, binarize=True, threshold=76):
    """Prepare image for OCR"""

    def binarize_array_opencv(image, threshold):
        """Binarize image from gray channel with 76 as threshold"""
        img = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2RGB)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, thresh2 = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
        return Image.fromarray(thresh2)

    basewidth = 300
    wpercent = (basewidth / float(img_orig.size[0]))
    hsize = int((float(img_orig.size[1]) * float(wpercent)))
    img_resized = img_orig.convert('L').resize(
        (basewidth, hsize), Image.LANCZOS)
    if binarize:
        img_resized = binarize_array_opencv(img_resized, threshold)

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


def get_ocr_number2(img_orig, fast=False):
    """New OCR based on tesserocr rather than pytesseract, should be much faster"""
    api.SetVariable("tessedit_char_whitelist", "0123456789.$£B")
    api.SetImage(img_orig)
    result = api.GetUTF8Text()
    return result


def get_ocr_number(img_orig, fast=False):
    """Return float value from image. -1.0f when OCR failed"""
    img_resized = prepareImage(img_orig, binarize=True)
    img_resized2 = prepareImage(img_orig, binarize=True, threshold=125)
    lst = []

    lst.append(
        get_ocr_number2(img_resized).
        strip().replace('$', '').replace('£', '').replace('€', '').replace('B', '').replace(',', '.').replace('\n', '').replace(':',
                                                                                                                                ''))
    lst.append(
        get_ocr_number2(img_resized2).
        strip().replace('$', '').replace('£', '').replace('€', '').replace('B', '').replace(',', '.').replace('\n', '').replace(':',
                                                                                                                      ''))
    try:
        return float(lst[-1])
    except ValueError:
        if fast:
            return -1
        # , img_min, img_mod, img_med, img_sharp]
        images = [img_orig, img_resized]
        i = 0
        while i < 2:
            j = 0
            while j < len(images):
                lst.append(
                    get_ocr_number2(images[j]).
                    strip().replace('$', '').replace('£', '').replace('€', '').replace('B', '').replace('\n', '').replace(':', ''))
                j += 1
            i += 1

    log.debug(lst)
    for element in lst:
        try:
            return float(element)
        except ValueError:
            pass
            # log.warning(f"Not recognized: {element}")
    return -1.0


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
            log.warning(
                "No virtual machine found. Press SETUP to re initialize the VM controller")
            # gui_signals.signal_open_setup.emit(p,L)
            screenshot = ImageGrab.grab()
    return screenshot

def normalize_rect(x1, y1, x2, y2):
    x1_ = min(x1, x2)
    x2_ = max(x1, x2)
    
    y1_ = min(y1,y2)
    y2_ = max(y1,y2)

    return x1_, y1_, x2_, y2_

def check_cropping(screenshot_list, top_left_corner_img):
    """Checks if screenshots are cropped and match the template 'icon'"""
    try:
        log.info("Checking cropping for '" + str(len(screenshot_list)) + "' images.")
        
        if len(screenshot_list) == 0: return False
        if top_left_corner_img.size == 0: return False

        any_too_big = any((s.width > const.CROP_WIDTH and s.height > const.CROP_HEIGHT) for s in screenshot_list)
        if any_too_big: return False
        
        for screenshot in screenshot_list:
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2RGB)
            count, _, _, _ = find_template_on_screen(top_left_corner_img, img, 0.01)
            if count != 1: return False
    except Exception as e:
        log.exception(e)
        return False
    finally:
        log.info("Done.")

    return True

def crop_screenshot_with_topleft_corner(original_screenshot, topleft_corner, useSleep = True):
    log.debug("Cropping top left corner")
    img = cv2.cvtColor(np.array(original_screenshot), cv2.COLOR_BGR2RGB)
    count, points, _, _ = find_template_on_screen(topleft_corner, img, 0.01)

    if count == 1:
        tlc = points[0]
        log.debug(f"Found to left corner at {tlc}")
        cropped_screenshot = original_screenshot.crop(
            (tlc[0], tlc[1], tlc[0] + const.CROP_WIDTH, tlc[1] + const.CROP_HEIGHT))
        return cropped_screenshot, tlc
    elif count > 1:
        log.warning(
            "Multiple top left corners found. That doesn't work unfortunately at this point. Make sure only one table is visible.")
        return None, None
    else:
        log.warning("No top left corner found")
        if useSleep: sleep(5)
        return None, None


def binary_pil_to_cv2(img):
    return cv2.cvtColor(np.array(Image.open(io.BytesIO(img))), cv2.COLOR_BGR2RGB)


def pil_to_cv2(img):
    return cv2.cvtColor(np.array(img), cv2.COLOR_BGR2RGB)


def cv2_to_pil(img):
    return Image.fromarray(img)


def rotate_image(image, angle):
    image_center = tuple(np.array(image.shape[1::-1]) / 2)
    rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
    result = cv2.warpAffine(
        image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
    return result


def check_if_image_in_range(img, screenshot, x1, y1, x2, y2, extended=False):
    cropped_screenshot = screenshot.crop((x1, y1, x2, y2))
    cropped_screenshot = pil_to_cv2(cropped_screenshot)
    count, _, _, _ = find_template_on_screen(
        img, cropped_screenshot, 0.01, extended=extended)
    return count >= 1


def is_template_in_search_area(table_dict, screenshot, image_name, image_area, player=None, extended=False):
    template_cv2 = binary_pil_to_cv2(table_dict[image_name])
    if player:
        try:
            search_area = table_dict[image_area][player]
        except KeyError as exc:
            raise KeyError(f"The table mapping is missing data for player {player} and {image_area}."
                           "Please fix the table mapping.") from exc
    else:
        search_area = table_dict[image_area]
    try:
        is_in_range = check_if_image_in_range(template_cv2, screenshot,
                                              search_area['x1'], search_area['y1'], search_area['x2'], search_area['y2'],
                                              extended=extended)
    except Exception as exc:
        x = search_area['x2'] - search_area['x1']
        y = search_area['y2'] - search_area['y1']
        xt = template_cv2.shape[1]
        yt = template_cv2.shape[0]
        if x < xt or y < yt:
            raise RuntimeError(f"Search area for {image_name} {player} is too small. It is {x}x{y} but the template is {xt}x{yt}."
                               ) from exc
        raise RuntimeError(f"The table has an missing template for {image_name}."
                           ) from exc

    return is_in_range


def ocr(screenshot, image_area, table_dict, player=None, fast=False):
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
    cropped_screenshot = screenshot.crop(
        (search_area['x1'], search_area['y1'], search_area['x2'], search_area['y2']))
    return get_ocr_float(cropped_screenshot, fast)
