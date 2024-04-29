import logging
import os
import sys

import cv2
import numpy as np
from PIL import Image
from tesserocr import PyTessBaseAPI, PSM, OEM

from poker.tools.helper import get_dir, pil_to_cv2, cv2_to_pil

log = logging.getLogger(__name__)

is_debug = False  # used for saving images for debug purposes

selection_contour_thickness = 6
DIGIT_HEIGHT_TOLERANCE = 2
THRESHOLD = 175
FINAL_SELECTION_CROP_PADDING = 2
OCR_MODE = PSM.SINGLE_COLUMN

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    tesserpath = os.path.join(get_dir('codebase'), 'tessdata')
else:
    tesserpath = os.path.join(get_dir('codebase'), '..', 'tessdata')


api = PyTessBaseAPI(path=tesserpath,
                    psm=OCR_MODE,
                    oem=OEM.LSTM_ONLY)


def get_ocr_number(img_orig, fast=False):
    """New OCR based on tesserocr rather than pytesseract, should be much faster"""
    api.SetVariable("tessedit_char_whitelist", "0123456789.,$£B")
    api.SetImage(img_orig)
    result = api.GetUTF8Text()

    if result.count(".") != 1:
        return None
    if len(result.strip()) < 3:
        return None
    return result


def color():
    array = np.random.choice(range(256), size=3)
    return list(map(int, array))


def in_range(low, high, x):
    return low <= x <= high


def get_number(position, cnts_ordered_by_height, image):
    img3 = pil_to_cv2(image)

    c = cnts_ordered_by_height[position]
    (x, y, w, h) = cv2.boundingRect(c)
    similar_heights = [c]
    d = DIGIT_HEIGHT_TOLERANCE
    for cnt_compare in cnts_ordered_by_height:
        (_, y2, _, h2) = cv2.boundingRect(cnt_compare)
        if in_range(y-d, y+h+d, y2) and in_range(y-d, y+h+d, y2+h2):
            similar_heights.append(cnt_compare)
            if is_debug:
                cv2.drawContours(img3, [cnt_compare], -1, color(), 4)
    l = x
    r = x + w
    t = y
    b = y + h
    for cnt in similar_heights:
        (x2, y2, w2, h2) = cv2.boundingRect(cnt)
        if x2 < l: l = x2
        if y2 < t: t = y2
        if x2 + w2 > r: r = x2 + w2
        if y2 + h2 > b: b = y2 + h2

    d2 = FINAL_SELECTION_CROP_PADDING
    l = l-d2
    t = t-d2
    r = r+d2
    b = b+d2

    img = pil_to_cv2(image)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, img = cv2.threshold(img, THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    img_pil = cv2_to_pil(img)
    im = img_pil.crop((l, t, r, b))

    if is_debug:
        pics_path = "log/pics"
        try:
            if not os.path.exists(pics_path):
                os.makedirs(pics_path)
        except OSError:
            log.error("Creation of the directory %s failed" % pics_path)
            sys.exit(1)

        image.save('log/pics/img_orig.png')
        im.save('log/pics/img_cropped.png')
        Image.fromarray(img3).save('log/pics/img_debug.png')

        log.debug("ocr images prepared")
        im.show()
        cv2.imshow("debug - img3", img3)
        cv2.waitKey()
        cv2.destroyAllWindows()

    return get_ocr_number(im)


def by_height(c):
    (x, y, w, h) = cv2.boundingRect(c)
    return h


# We assume that the height of the contours will let us know which contours are numbers or not.
# We start with the contour of greatest height
# We then add the width for all of the next largest contours that are inbetween a delta.
# Once we have all contours in that delta, we can get the location to crop for ocr.
# If ocr fails because we got something else instead e.g chipstack, then remove this contour, and try the next largest
def swc_ocr(img_orig):
    basewidth = 300
    wpercent = (basewidth / float(img_orig.size[0]))
    hsize = int((float(img_orig.size[1]) * float(wpercent)))
    image = img_orig.convert('L').resize((basewidth, hsize), Image.LANCZOS)

    img = pil_to_cv2(image)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blurred = cv2.GaussianBlur(img, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200, 255)

    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    cv2.drawContours(img, cnts, -1, (255, 0, 0), SELECTION_CONTOUR_THICKNESS)

    if is_debug:
        img2 = pil_to_cv2(image)
        img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    blurred = cv2.GaussianBlur(img, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200, 255)

    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if is_debug:
        cv2.drawContours(img2, cnts, -1, (0, 255, 0), 3)
        cv2.imshow("debug - img2", img2)
        cv2.waitKey()
        cv2.destroyAllWindows()

    sorted_cnts = list(sorted(cnts, key=by_height, reverse=True))  # Highest to lowest

    for i, _ in enumerate(sorted_cnts):
        num = get_number(i, sorted_cnts, image)
        if num:
            prepped = num.strip() \
                .replace('$', '') \
                .replace('£', '') \
                .replace('€', '') \
                .replace('B', '') \
                .replace(',', '')
            return float(prepped)
    else:
        return -1
