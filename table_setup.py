#!/usr/bin/env python

import json
import cv2
from PIL import Image
import numpy as np
import sys
from random import randint

sys.setrecursionlimit(10 ** 9)

class Setup():
    def __init__(self, topleftcorner_file: object, screenshot_file: object, output_file: object) -> object:
        self.topLeftCorner = cv2.cvtColor(np.array(Image.open(topleftcorner_file)), cv2.COLOR_BGR2RGB)
        #screenshot = cv2.cvtColor(np.array(Image.open(screenshot_file)), cv2.COLOR_BGR2RGB)
        screenshot = cv2.imread(screenshot_file)
        if screenshot is None:
            raise Exception(screenshot_file+' doesn\'t exist')
        # cv2.imshow('img', screenshot)
        # cv2.waitKey()
        # cv2.imshow('img', cv2.imread(topleftcorner_file, 0))
        # cv2.waitKey()
        count, points, bestfit = self.find_template_on_screen(self.topLeftCorner, screenshot, 0.1)
        # Image.open(screenshot_file).show()
        # cv2.imshow("Image",screenshot)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        self.tlc = points[0]
        # print ("TLC: "+str(self.tlc))
        cropped_screenshoht=self.crop_image(Image.open(screenshot_file),self.tlc[0],self.tlc[1],self.tlc[0]+1000,self.tlc[1]+900)
        cropped_screenshoht.save(output_file)

        #
        # setup = cv2.cvtColor(np.array(Image.open(name)), cv2.COLOR_BGR2RGB)
        # tlc = cv2.cvtColor(np.array(Image.open(topleftcorner)), cv2.COLOR_BGR2RGB)
        # count, points, bestfit = self.find_template_on_screen(setup, tlc, 0.01)
        # rel = tuple(-1 * np.array(bestfit))
        #
        # template = cv2.cvtColor(np.array(Image.open(findTemplate)), cv2.COLOR_BGR2RGB)
        #
        # count, points, bestfit = self.find_template_on_screen(setup, template, 0.01)
        # print("Count: " + str(count) + " Points: " + str(points) + " Bestfit: " + str(bestfit))
        #
        # print(findTemplate + " Relative: ")
        # print(str(tuple(map(sum, zip(points[0], rel)))))

    def find_template_on_screen(self, template, screenshot, threshold):
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
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            points.append(pt)

        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()

        return count, points, bestFit

    def crop_image(self, original, left, top, right, bottom):
        # original.show()
        width, height = original.size  # Get dimensions
        cropped_example = original.crop((left, top, right, bottom))
        # cropped_example.show()
        return cropped_example

if __name__=='__main__':
    screenshot_file = 'poker/tables/backgrounds/PS2.png'
    output_file = 'poker/log/table_setup_output.png'
    top_left_corner_file = 'poker/pics/PS/topleft.png'
    coordinates_file = 'poker/coordinates.txt'
    tableNames = ['PP', 'SN', 'PS', 'PS2']
    table = 'PS2'

    s = Setup(topleftcorner_file=top_left_corner_file,
              screenshot_file=screenshot_file,
              output_file=output_file)

    with open(coordinates_file) as inf:
        c = json.load(inf)
        coo = c['screen_scraping']


    userTable = input("Choose a table to edit :{} (default : {})".format(tableNames, table))
    if userTable and userTable in tableNames:
        table = userTable

    img = cv2.imread(output_file)

    for key, item in coo.items():
        randomColor = [randint(0,255), randint(0, 255), randint(0, 255)]
        try:
            for c in item[table]:
                try:
                    cv2.rectangle(img, (c[0], c[1]), (c[2], c[3]), randomColor)
                except:
                    pass
        except:
            pass
        try:
            cv2.rectangle(img, (int(item[table]['x1']), int(item[table]['y1'])), (int(item[table]['x2']), int(item[table]['y2'])), randomColor)
        except Exception as e:
            pass

    windowName = 'display results'

    cv2.imshow(windowName, img)
    cv2.waitKey()