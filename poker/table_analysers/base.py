import logging
import re
import sys
import time
import os

import cv2  # opencv 3.0
import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageGrab
from configobj import ConfigObj

from poker.decisionmaker.genetic_algorithm import GeneticAlgorithm
from poker.tools.vbox_manager import VirtualBoxController


class Table(object):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self, p, gui_signals, game_logger, version):
        self.version = version
        self.ip = ''
        self.load_templates(p)
        self.load_coordinates()
        self.logger = logging.getLogger('table')
        self.logger.setLevel(logging.DEBUG)
        self.gui_signals = gui_signals
        self.game_logger = game_logger

    def load_templates(self, p):
        self.cardImages = dict()
        self.img = dict()
        self.tbl = p.selected_strategy['pokerSite']
        values = "23456789TJQKA"
        suites = "CDHS"
        if self.tbl == 'SN': suites = suites.lower()

        for x in values:
            for y in suites:
                name = "pics/" + self.tbl[0:2] + "/" + x + y + ".png"
                if os.path.exists(name):
                    self.img[x + y.upper()] = Image.open(name)
                    # if self.tbl=='SN':
                    #     self.img[x + y.upper()]=self.crop_image(self.img[x + y.upper()], 5,5,20,45)

                    self.cardImages[x + y.upper()] = cv2.cvtColor(np.array(self.img[x + y.upper()]), cv2.COLOR_BGR2RGB)


                    # (thresh, self.cardImages[x + y]) =
                    # cv2.threshold(self.cardImages[x + y], 128, 255,
                    # cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                else:
                    self.logger.critical("Card template File not found: " + str(x) + str(y) + ".png")

        name = "pics/" + self.tbl[0:2] + "/button.png"
        template = Image.open(name)
        self.button = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/topleft.png"
        template = Image.open(name)
        self.topLeftCorner = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        if self.tbl[0:2] == 'SN':
            name = "pics/" + self.tbl[0:2] + "/topleft2.png"
            template = Image.open(name)
            self.topLeftCorner2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

            name = "pics/" + self.tbl[0:2] + "/topleft3.png"
            template = Image.open(name)
            self.topLeftCorner_snowieadvice1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

            name = "pics/" + self.tbl[0:2] + "/topleftLA.png"
            template = Image.open(name)
            self.topLeftCorner_snowieadvice2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/coveredcard.png"
        template = Image.open(name)
        self.coveredCardHolder = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/imback.png"
        template = Image.open(name)
        self.ImBack = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/check.png"
        template = Image.open(name)
        self.check = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/call.png"
        template = Image.open(name)
        self.call = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/smalldollarsign1.png"
        template = Image.open(name)
        self.smallDollarSign1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/allincallbutton.png"
        template = Image.open(name)
        self.allInCallButton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/lostEverything.png"
        template = Image.open(name)
        self.lostEverything = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/dealer.png"
        template = Image.open(name)
        self.dealer = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/betbutton.png"
        template = Image.open(name)
        self.betbutton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

    def load_coordinates(self):
        with open('coordinates.txt', 'r') as inf:
            c = eval(inf.read())
            self.coo = c['screen_scraping']

    def take_screenshot(self, initial, p):
        if initial:
            self.gui_signals.signal_status.emit("")
            self.gui_signals.signal_progressbar_reset.emit()
            if self.gui_signals.exit_thread == True: sys.exit()
            if self.gui_signals.pause_thread == True:
                while self.gui_signals.pause_thread == True:
                    time.sleep(1)
                    if self.gui_signals.exit_thread == True: sys.exit()

        time.sleep(0.1)
        config = ConfigObj("config.ini")
        control = config['control']
        if control == 'Direct mouse control':
            self.entireScreenPIL = ImageGrab.grab()

        else:
            try:
                vb = VirtualBoxController()
                self.entireScreenPIL = vb.get_screenshot_vbox()
                self.logger.debug("Screenshot taken from virtual machine")
            except:
                self.logger.warning("No virtual machine found. Press SETUP to re initialize the VM controller")
                # gui_signals.signal_open_setup.emit(p,L)
                self.entireScreenPIL = ImageGrab.grab()

        self.gui_signals.signal_status.emit(str(p.current_strategy))
        self.gui_signals.signal_progressbar_increase.emit(5)
        return True

    def find_template_on_screen(self, template, screenshot, threshold):
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
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            points.append(pt)
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        return count, points, bestFit, min_val

    # New function  
    def find_value(self, fund, pil_image, threshold_each ):
        numberImages = dict()
        img = dict()
        values ="0123456789."
        number_values = "0123456789"
        keyList = []
        x_value = []  

        if Fund == "game_number": #Beim Game_Number auslesen stört der "." (Punkt), deshalb wird er hier weggelassen
            values = number_values   

        for x in values:
            name = "pics/PP/"+ fund + "/" + x + ".png"
            img[x] = Image.open(name)
            numberImages[x] = cv2.cvtColor(np.array(img[x]), cv2.COLOR_BGR2RGB)

        def go_through_value(img_cv2, which_number):            
            if which_number == "all":
                for key, value in numberImages.items():
                    template_cv2 = value
                    res = cv2.matchTemplate(img_cv2 ,template_cv2 ,cv2.TM_CCOEFF_NORMED)

                    threshold = 0.9
                    loc = np.where( res >= threshold)

                    for pt in zip(*loc[::-1]):
                        x_value.append(pt[0])
                x_value.sort()

                return x_value

            if which_number == "each_one":
                for key, value in numberImages.items():
                    template_cv2 = value
                    method = eval('cv2.TM_SQDIFF_NORMED')
                    res_1 = cv2.matchTemplate(img_cv2 ,template_cv2 , method)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res_1)

                    if min_val < threshold_each:
                        keyList.append(key)

                return keyList

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)

        value = go_through_value(img, "all")
        
        width, height = pil_image.size  # Get dimensions

        for a, fd in enumerate(value):
            image_cut = self.crop_image(pil_image, fd, 0, fd + 11 , height)
            img = cv2.cvtColor(np.array(image_cut), cv2.COLOR_BGR2RGB)
            liste = go_through_value(img, "each_one")
        
        try:       
            Value = float(''.join(map(str, liste))) 

        except:
            Value = ""
        
        return Value

    def get_ocr_float(self, img_orig, name, force_method=0, binarize=False):
        def binarize_array(image, threshold=200):
            """Binarize a numpy array."""
            numpy_array = np.array(image)
            for i in range(len(numpy_array)):
                for j in range(len(numpy_array[0])):
                    if numpy_array[i][j] > threshold:
                        numpy_array[i][j] = 255
                    else:
                        numpy_array[i][j] = 0
            return Image.fromarray(numpy_array)

        def fix_number(t, force_method):
            t = t.replace("I", "1").replace("Â°lo", "").replace("O", "0").replace("o", "0") \
                .replace("-", ".").replace("D", "0").replace("I", "1").replace("_", ".").replace("-", ".") \
                .replace("B", "8").replace("..", ".")
            t = re.sub("[^0123456789\.]", "", t)
            try:
                if t[0] == ".": t = t[1:]
            except:
                pass
            try:
                if t[-1] == ".": t = t[0:-1]
            except:
                pass
            try:
                if t[-1] == ".": t = t[0:-1]
            except:
                pass
            try:
                if t[-1] == "-": t = t[0:-1]
            except:
                pass
            if force_method == 1:
                try:
                    t = re.findall(r'\d{1,3}\.\d{1,2}', str(t))[0]
                except:
                    t = ''
                if t == '':
                    try:
                        t = re.findall(r'\d{1,3}', str(t))[0]
                    except:
                        t = ''

            return t

        try:
            img_orig.save('pics/ocr_debug_' + name + '.png')
        except:
            self.logger.warning("Coulnd't safe debugging png file for ocr")

        basewidth = 300
        wpercent = (basewidth / float(img_orig.size[0]))
        hsize = int((float(img_orig.size[1]) * float(wpercent)))
        img_resized = img_orig.convert('L').resize((basewidth, hsize), Image.ANTIALIAS)
        if binarize:
            img_resized = binarize_array(img_resized, 200)

        img_min = img_resized.filter(ImageFilter.MinFilter)
        # img_med = img_resized.filter(ImageFilter.MedianFilter)
        img_mod = img_resized.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)

        lst = []
        # try:
        #    lst.append(pytesseract.image_to_string(img_orig, none, false,"-psm 6"))
        # except exception as e:
        #    self.logger.error(str(e))

        if force_method == 0:
            try:
                lst.append(pytesseract.image_to_string(img_min, None, False, "-psm 6"))
            except Exception as e:
                self.logger.warning(str(e))
                try:
                    self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
                except:
                    self.logger.warning("Coulnd't safe debugging png file for ocr")
                    # try:
                    #    lst.append(pytesseract.image_to_string(img_med, None, False, "-psm 6"))
                    # except Exception as e:
                    #    self.logger.error(str(e))

        try:
            if force_method == 1 or fix_number(lst[0], force_method=0) == '':
                lst.append(pytesseract.image_to_string(img_mod, None, False, "-psm 6"))
                lst.append(pytesseract.image_to_string(img_min, None, False, "-psm 6"))
        except UnicodeDecodeError:
            pass
        except Exception as e:
            self.logger.warning(str(e))
            try:
                self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
            except:
                self.logger.warning("Coulnd't safe debugging png file for ocr")

        try:
            final_value = ''
            for i, j in enumerate(lst):
                try:
                    self.logger.debug("OCR of " + name + " method {}: {} ".format(i, j))
                except:
                    self.logger.warning("OCR of " + name + " method failed")

                lst[i] = fix_number(lst[i], force_method) if lst[i] != '' else lst[i]
                final_value = lst[i] if final_value == '' else final_value

            self.logger.info(name + " FINAL VALUE: " + str(final_value))
            if final_value == '':
                return ''
            else:
                return float(final_value)

        except Exception as e:
            self.logger.warning("Pytesseract Error in recognising " + name)
            self.logger.warning(str(e))
            try:
                self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
            except:
                pass
            return ''

    def call_genetic_algorithm(self, p):
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Updating charts and work in background")
        n = self.game_logger.get_game_count(p.current_strategy)
        lg = int(p.selected_strategy['considerLastGames'])  # only consider lg last games to see if there was a loss
        f = self.game_logger.get_strategy_return(p.current_strategy, lg)
        self.gui_signals.signal_label_number_update.emit('gamenumber', str(int(n)))

        total_winnings = self.game_logger.get_strategy_return(p.current_strategy, 9999999)

        winnings_per_bb_100 = total_winnings / p.selected_strategy['bigBlind'] / n * 100 if n > 0 else 0

        self.logger.info("Total Strategy winnings: %s", total_winnings)
        self.logger.info("Winnings in BB per 100 hands: %s", np.round(winnings_per_bb_100, 2))
        self.gui_signals.signal_label_number_update.emit('winnings', str(np.round(winnings_per_bb_100, 2)))

        self.logger.info("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))

        if n % int(p.selected_strategy['strategyIterationGames']) == 0 and f < float(
                p.selected_strategy['minimumLossForIteration']):
            self.gui_signals.signal_status.emit("***Improving current strategy***")
            self.logger.info("***Improving current strategy***")
            # winsound.Beep(500, 100)
            GeneticAlgorithm(True, self.game_logger)
            p.read_strategy()
        else:
            pass
            # self.logger.debug("Criteria not met for running genetic algorithm. Recommendation would be as follows:")
            # if n % 50 == 0: GeneticAlgorithm(False, logger, L)

    def crop_image(self, original, left, top, right, bottom):
        # original.show()
        width, height = original.size  # Get dimensions
        cropped_example = original.crop((left, top, right, bottom))
        # cropped_example.show()
        return cropped_example

    def get_utg_from_abs_pos(self, abs_pos, dealer_pos):
        utg_pos = (abs_pos - dealer_pos + 4) % 6
        return utg_pos

    def get_abs_from_utg_pos(self, utg_pos, dealer_pos):
        abs_pos = (utg_pos + dealer_pos - 4) % 6
        return abs_pos

    def get_raisers_and_callers(self, p, reference_pot):
        first_raiser = np.nan
        second_raiser = np.nan
        first_caller = np.nan

        for n in range(5):  # n is absolute position of other player, 0 is player after bot
            i = (
                    self.dealer_position + n + 3 - 2) % 5  # less myself as 0 is now first other player to my left and no longer myself
            self.logger.debug("Go through pots to find raiser abs: {0} {1}".format(i, self.other_players[i]['pot']))
            if self.other_players[i]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if self.other_players[i]['pot'] > reference_pot:
                    # reference pot is bb for first round and bot for second round
                    if np.isnan(first_raiser):
                        first_raiser = int(i)
                        first_raiser_pot = self.other_players[i]['pot']
                    else:
                        if self.other_players[i]['pot'] > first_raiser_pot:
                            second_raiser = int(i)

        first_raiser_utg = self.get_utg_from_abs_pos(first_raiser, self.dealer_position)
        highest_raiser = np.nanmax([first_raiser, second_raiser])
        second_raiser_utg = self.get_utg_from_abs_pos(second_raiser, self.dealer_position)

        first_possible_caller = int(self.big_blind_position_abs_op + 1) if np.isnan(highest_raiser) else int(
            highest_raiser + 1)
        self.logger.debug("First possible potential caller is: " + str(first_possible_caller))

        # get first caller after raise in preflop
        for n in range(first_possible_caller, 5):  # n is absolute position of other player, 0 is player after bot
            self.logger.debug(
                "Go through pots to find caller abs: " + str(n) + ": " + str(self.other_players[n]['pot']))
            if self.other_players[n]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if (self.other_players[n]['pot'] == float(
                        p.selected_strategy['bigBlind']) and not n == self.big_blind_position_abs_op) or \
                                self.other_players[n]['pot'] > float(p.selected_strategy['bigBlind']):
                    first_caller = int(n)
                    break

        first_caller_utg = self.get_utg_from_abs_pos(first_caller, self.dealer_position)

        # check for callers between bot and first raiser. If so, first raiser becomes second raiser and caller becomes first raiser
        first_possible_caller = 0
        if self.position_utg_plus == 3: first_possible_caller = 1
        if self.position_utg_plus == 4: first_possible_caller = 2
        if not np.isnan(first_raiser):
            for n in range(first_possible_caller, first_raiser):
                if self.other_players[n]['status'] == 1 and \
                        not (self.other_players[n]['utg_position'] == 5 and p.selected_strategy['bigBlind']) and \
                        not (self.other_players[n]['utg_position'] == 4 and p.selected_strategy['smallBlind']) and \
                        not (self.other_players[n]['pot'] == ''):
                    second_raiser = first_raiser
                    first_raiser = n
                    first_raiser_utg = self.get_utg_from_abs_pos(first_raiser, self.dealer_position)
                    second_raiser_utg = self.get_utg_from_abs_pos(second_raiser, self.dealer_position)
                    break

        self.logger.debug("First raiser abs: " + str(first_raiser))
        self.logger.info("First raiser utg+" + str(first_raiser_utg))
        self.logger.debug("Second raiser abs: " + str(second_raiser))
        self.logger.info("Highest raiser abs: " + str(highest_raiser))
        self.logger.debug("First caller abs: " + str(first_caller))
        self.logger.info("First caller utg+" + str(first_caller_utg))

        return first_raiser, second_raiser, first_caller, first_raiser_utg, second_raiser_utg, first_caller_utg

    def derive_preflop_sheet_name(self, t, h, first_raiser_utg, first_caller_utg, second_raiser_utg):
        first_raiser_string = 'R' if not np.isnan(first_raiser_utg) else ''
        first_raiser_number = str(first_raiser_utg + 1) if first_raiser_string != '' else ''

        second_raiser_string = 'R' if not np.isnan(second_raiser_utg) else ''
        second_raiser_number = str(second_raiser_utg + 1) if second_raiser_string != '' else ''

        first_caller_string = 'C' if not np.isnan(first_caller_utg) else ''
        first_caller_number = str(first_caller_utg + 1) if first_caller_string != '' else ''

        round_string = '2' if h.round_number == 1 else ''

        sheet_name = str(t.position_utg_plus + 1) + \
                     round_string + \
                     str(first_raiser_string) + str(first_raiser_number) + \
                     str(second_raiser_string) + str(second_raiser_number) + \
                     str(first_caller_string) + str(first_caller_number)

        if h.round_number == 2:
            sheet_name = 'R1R2R1A2'

        self.preflop_sheet_name = sheet_name
        return self.preflop_sheet_name
