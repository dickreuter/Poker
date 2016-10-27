import os.path
import os.path
import re
import sys
import time

import cv2  # opencv 3.0
import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageGrab
from configobj import ConfigObj

from decisionmaker.genetic_algorithm import GeneticAlgorithm
from tools.debug_logger import debug_logger
from tools.vbox_manager import VirtualBoxController


class Table(object):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self, p, gui_signals, game_logger, version):
        self.version = version
        self.ip = ''
        self.load_templates(p)
        self.load_coordinates()
        self.logger = debug_logger().start_logger('table_analysers')
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

    def get_ocr_float(self, img_orig, name, force_method=0):
        def fix_number(t):
            t = t.replace("I", "1").replace("Â°lo", "").replace("O", "0").replace("o", "0") \
                .replace("-", ".").replace("D", "0").replace("I", "1").replace("_", ".").replace("-", ".").replace("B",
                                                                                                                   "8")
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
            return t

        try:
            img_orig.save('pics/ocr_debug_' + name + '.png')
        except:
            self.logger.warning("Coulnd't safe debugging png file for ocr")

        basewidth = 300
        wpercent = (basewidth / float(img_orig.size[0]))
        hsize = int((float(img_orig.size[1]) * float(wpercent)))
        img_resized = img_orig.resize((basewidth, hsize), Image.ANTIALIAS)

        img_min = img_resized.filter(ImageFilter.MinFilter)
        img_med = img_resized.filter(ImageFilter.MedianFilter)
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
            if force_method == 1 or fix_number(lst[0]) == '':
                lst.append(pytesseract.image_to_string(img_mod, None, False, "-psm 6"))
        except Exception as e:
            self.logger.warning(str(e))
            try:
                self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
            except:
                self.logger.warning("Coulnd't safe debugging png file for ocr")

        try:
            final_value = ''
            for i, j in enumerate(lst):
                self.logger.debug("OCR of " + name + " method " + str(i) + ": " + str(j))
                lst[i] = fix_number(lst[i]) if lst[i] != '' else lst[i]
                final_value = lst[i] if final_value == '' else final_value

            self.logger.info(name + " FINAL VALUE: " + str(final_value))
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
        lg = int(
            p.selected_strategy['considerLastGames'])  # only consider lg last games to see if there was a loss
        f = self.game_logger.get_strategy_return(p.current_strategy, lg)
        self.gui_signals.signal_lcd_number_update.emit('gamenumber', int(n))
        self.gui_signals.signal_lcd_number_update.emit('winnings', f)
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

    def find_item_location_in_crop(self, x1, y1, x2, y2, template, screentho):
        pass

    def get_raisers_and_callers(self, p, reference_pot, relative_to_bot=0):
        first_raiser = np.nan
        second_raiser = np.nan
        first_caller = np.nan

        for n in range(5 - relative_to_bot):  # n is absolute position of other player, 0 is player after bot
            i = (
                    self.dealer_position + n + 3 - 2) % 5  # less myself as 0 is now first other player to my left and no longer myself
            self.logger.debug(
                "Go through pots to find raiser abs: " + str(i) + ": " + str(self.other_players[i]['pot']))
            if self.other_players[i]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if self.other_players[i][
                    'pot'] > reference_pot:  # reference pot is bb for first round and bot for second round
                    if np.isnan(first_raiser):
                        first_raiser = int(i)
                        first_raiser_pot = self.other_players[i]['pot']
                    else:
                        if self.other_players[i]['pot'] > first_raiser_pot:
                            second_raiser = int(i)

        self.logger.debug("First raiser abs: " + str(first_raiser))
        first_raiser_utg = (first_raiser - self.dealer_position + 4) % 6
        self.logger.info("First raiser utg+" + str(first_raiser_utg))
        highest_raiser = np.nanmax([first_raiser, second_raiser])

        self.logger.debug("Second raiser abs: " + str(second_raiser))
        second_raiser_utg = (second_raiser - self.dealer_position + 4) % 6
        self.logger.info("Highest raiser abs: " + str(highest_raiser))

        first_possible_caller = int(
            self.big_blind_position_abs_op + 1 if np.isnan(highest_raiser) else highest_raiser + 1)
        self.logger.debug("First possible potential caller is: " + str(first_possible_caller))

        # get first caller after raise in preflop
        for n in range(first_possible_caller,
                       5 - relative_to_bot):  # n is absolute position of other player, 0 is player after bot
            self.logger.debug(
                "Go through pots to find caller abs: " + str(n) + ": " + str(self.other_players[n]['pot']))
            if self.other_players[n]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if (self.other_players[n]['pot'] == float(
                        p.selected_strategy['bigBlind']) and not n == self.big_blind_position_abs_op) or \
                                self.other_players[n]['pot'] > float(p.selected_strategy['bigBlind']):
                    first_caller = int(n)
                    break

        self.logger.debug("First caller abs: " + str(first_caller))
        first_caller_utg = (first_caller - self.dealer_position + 4) % 6
        self.logger.info("First caller utg+" + str(first_caller_utg))

        return first_raiser, second_raiser, first_caller, first_raiser_utg, second_raiser_utg, first_caller_utg

    def get_reverse_sheet(self, position):
        sheet_name = ''
        sheet_name += self.other_players[position]['utg_position']
        pass

    def get_range_from_prefloop_sheet(self, sheet_name, action):
        pass

    def get_utg_from_abs_pos(self, abs_pos, dealer_pos):
        utg_pos = (abs_pos - dealer_pos + 4) % 6
        return utg_pos

    def get_abs_from_utg_pos(self, utg_pos, dealer_pos):
        abs_pos = (utg_pos + dealer_pos - 4) % 6
        return abs_pos

    def derive_preflop_sheet_name(self, t, h, first_raiser_utg, first_caller_utg, second_raiser_utg):
        first_raiser_string = 'R' if not np.isnan(first_raiser_utg) else ''
        first_raiser_number = str(first_raiser_utg + 1) if first_raiser_string != '' else ''

        first_caller_string = 'C' if not np.isnan(first_caller_utg) else ''
        first_caller_number = str(first_caller_utg + 1) if first_caller_string != '' else ''

        sheet_name = str(t.position_utg_plus + 1) + str(first_raiser_string) + str(first_raiser_number) + str(
            first_caller_string) + str(first_caller_number)
        if h.round_number == 1:
            round2_sheetname = str(t.position_utg_plus + 1) + "2" + str(first_raiser_string) + str(
                first_raiser_number) + str(first_caller_string) + str(first_caller_number)
            self.logger.info("Round 2 sheetname: " + round2_sheetname)
            if round2_sheetname in h.preflop_sheet:
                sheet_name = round2_sheetname
            else:
                self.logger.warning("Using backup round 2 sheetname R1R2 because sheet was not found: " + round2_sheetname)
                sheet_name = 'R1R2'
        if not np.isnan(second_raiser_utg):
            self.logger.warning("Using second raiser backup table_analysers R1R2")
            sheet_name = 'R1R2'
        if h.round_number == 2:
            sheet_name = 'R1R2R1A2'

        self.preflop_sheet_name = sheet_name
        return self.preflop_sheet_name