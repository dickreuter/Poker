#!/usr/bin/env python

import cv2
from PIL import Image
import numpy as np


class CornerFinder():
    @staticmethod
    def find_template_on_screen(template, screenshot, threshold):
        # 'cv2.TM_CCOEFF', 'cv2.TM_CCOEFF_NORMED', 'cv2.TM_CCORR',
        # 'cv2.TM_CCORR_NORMED', 'cv2.TM_SQDIFF', 'cv2.TM_SQDIFF_NORMED']
        method = eval('cv2.TM_CCOEFF')
        # Apply template Matching
        res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF)
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

        return count, points, bestFit

    @staticmethod
    def findTopLeftCorner(topleftcorner_file, screenshot_file):
        topLeftCorner = cv2.cvtColor(np.array(Image.open(topleftcorner_file)), cv2.COLOR_BGR2RGB)
        screenshot = cv2.imread(screenshot_file)
       
        if screenshot is None:
            print(screenshot_file+' doesn\'t exist')
            return False

        count, points, bestfit = CornerFinder.find_template_on_screen(topLeftCorner, screenshot, 0.1)
        
        if count == 0:
            print('top left corner not found on '+screenshot_file)
            return False
        else:
            return points[0]