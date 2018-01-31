#!/usr/bin/env python

import cv2
from PIL import Image
import numpy as np


class CornerFinder():
    @staticmethod
    def find_template_on_screen(template, screenshot, threshold):
        # 'cv2.TM_CCOEFF', 'cv2.TM_CCOEFF_NORMED', 'cv2.TM_CCORR',
        # 'cv2.TM_CCORR_NORMED', 'cv2.TM_SQDIFF', 'cv2.TM_SQDIFF_NORMED']
        method = eval('cv2.TM_SQDIFF_NORMED')
        # Apply template Matching
        res = cv2.matchTemplate(screenshot, template, method)
        loc = np.where(res <= threshold)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            bestFit = min_loc
        else:
            bestFit = max_loc

        count = 0
        points = []
        for pt in zip(*loc[::-1]):
            count += 1
            points.append(pt)
        return count, points, bestFit, min_val

    @staticmethod
    def findTopLeftCorner(topleftcorner_file, screenshot_file):
        screenshot = cv2.cvtColor(np.array(Image.open(screenshot_file)), cv2.COLOR_BGR2RGB)
        topLeftCorner = cv2.cvtColor(np.array(Image.open(topleftcorner_file)), cv2.COLOR_BGR2RGB)

        count, points, bestfit, _ = CornerFinder.find_template_on_screen(topLeftCorner, screenshot, 0.01)

        if count == 1:
            print ("top left corner found : "+str(points[0]))
            return points[0]
        else:
            print("Top left corner NOT found in "+screenshot_file)
            return False