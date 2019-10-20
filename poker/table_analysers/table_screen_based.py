import datetime
import inspect
import re
import sys
import threading
import time
from copy import copy

import cv2  # opencv 3.0
import numpy as np
import pytesseract
from PIL import Image, ImageFilter

from poker.decisionmaker.montecarlo_python import MonteCarlo
from .base import Table


class TableScreenBased(Table):
    def get_top_left_corner(self, p):
        self.current_strategy = p.current_strategy  # needed for mongo manager
        img = cv2.cvtColor(np.array(self.entireScreenPIL), cv2.COLOR_BGR2RGB)
        count, points, bestfit, minimum_value = self.find_template_on_screen(self.topLeftCorner, img, 0.01)
        try:
            count2, points2, bestfit2, _ = self.find_template_on_screen(self.topLeftCorner2, img, 0.01)
            if count2 == 1:
                count = 1
                points = points2
        except:
            pass

        if count == 1:
            self.tlc = points[0]
            self.logger.debug("Top left corner found")
            self.timeout_start = datetime.datetime.utcnow()
            self.mt_tm = time.time()
            return True
        else:

            self.gui_signals.signal_status.emit(self.tbl + " not found yet")
            self.gui_signals.signal_progressbar_reset.emit()
            self.logger.debug("Top left corner NOT found")
            time.sleep(1)
            return False

    def check_for_button(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        cards = ' '.join(self.mycards)
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.button, img, func_dict['tolerance'])

        if count > 0:
            self.gui_signals.signal_status.emit("Buttons found, cards: " + str(cards))
            self.logger.info("Buttons Found, cards: " + str(cards))
            return True

        else:
            self.logger.debug("No buttons found")
            return False

    def check_for_checkbutton(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Check for Check")
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Checking for check button")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, minval = self.find_template_on_screen(self.check, img, func_dict['tolerance'])

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            self.logger.debug("check button found")
        else:
            self.checkButton = False
            self.logger.debug("no check button found")
        self.logger.debug("Check: " + str(self.checkButton))
        return True

    def check_for_captcha(self, mouse):
        # func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        # if func_dict['active']:
        #     ChatWindow = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
        #                             self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        #     basewidth = 500
        #     wpercent = (basewidth / float(ChatWindow.size[0]))
        #     hsize = int((float(ChatWindow.size[1]) * float(wpercent)))
        #     ChatWindow = ChatWindow.resize((basewidth, hsize), Image.ANTIALIAS)
        #     # ChatWindow.show()
        #     try:
        #         t.chatText = (pytesseract.image_to_string(ChatWindow, None,
        #         False, "-psm 6"))
        #         t.chatText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]",
        #         "", t.chatText)
        #         keyword1 = 'disp'
        #         keyword2 = 'left'
        #         keyword3 = 'pic'
        #         keyword4 = 'key'
        #         keyword5 = 'lete'
        #         self.logger.debug("Recognised text: "+t.chatText)
        #
        #         if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2)
        #         > 0) or (
        #                     t.chatText.find(keyword3) > 0) or
        #                     (t.chatText.find(keyword4) > 0) or (
        #                     t.chatText.find(keyword5) > 0)):
        #             self.logger.warning("Submitting Captcha")
        #             captchaIMG = self.crop_image(self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1_2'], self.tlc[1] + func_dict['y1_2'],
        #                             self.tlc[0] + func_dict['x2_2'], self.tlc[1] + func_dict['y2_2']))
        #             captchaIMG.save("pics/captcha.png")
        #             # captchaIMG.show()
        #             time.sleep(0.5)
        #             t.captcha = solve_captcha("pics/captcha.png")
        #             mouse.enter_captcha(t.captcha)
        #             self.logger.info("Entered captcha: "+str(t.captcha))
        #     except:
        #         self.logger.warning("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, mouse):
        if self.tbl == 'SN': return True
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, minvalue = self.find_template_on_screen(self.ImBack, img, func_dict['tolerance'])
        if count > 0:
            self.gui_signals.signal_status.emit("I am back found")
            mouse.mouse_action("Imback", self.tlc)
            return False
        else:
            return True

    def check_for_call(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Check for Call")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.call, img, func_dict['tolerance'])
        if count > 0:
            self.callButton = True
            self.logger.debug("Call button found")
        else:
            self.callButton = False
            self.logger.info("Call button NOT found")
            pil_image.save("pics/debug_nocall.png")
        return True

    def check_for_betbutton(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Check for betbutton")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, min_val = self.find_template_on_screen(self.betbutton, img, func_dict['tolerance'])
        if count > 0:
            self.bet_button_found = True
            self.logger.debug("Bet button found")
        else:
            self.bet_button_found = False
            self.logger.info("Bet button NOT found")
        return True

    def check_for_allincall(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.logger.debug("Check for All in call button")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
            self.logger.debug("All in call button found")
        else:
            self.allInCallButton = False
            self.logger.debug("All in call button not found")

        if not self.bet_button_found:
            self.allInCallButton = True
            self.logger.debug("Assume all in call because there is no bet button")

        return True

    def get_table_cards(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Get Table cards")
        self.cardsOnTable = []
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)

        card_images = self.cardImages

        for key, value in card_images.items():
            template = value
            method = eval('cv2.TM_SQDIFF_NORMED')
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if min_val < 0.01:
                self.cardsOnTable.append(key)

        self.gameStage = ''

        if len(self.cardsOnTable) < 1:
            self.gameStage = "PreFlop"
        elif len(self.cardsOnTable) == 3:
            self.gameStage = "Flop"
        elif len(self.cardsOnTable) == 4:
            self.gameStage = "Turn"
        elif len(self.cardsOnTable) == 5:
            self.gameStage = "River"

        if self.gameStage == '':
            self.logger.critical("Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        self.logger.info("---")
        self.logger.info("Gamestage: " + self.gameStage)
        self.logger.info("Cards on table: " + str(self.cardsOnTable))
        self.logger.info("---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def get_table_cards_nn(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        self.gui_signals.signal_progressbar_increase.emit(5)
        self.cardsOnTable = []
        width = self.coo['card_sizes'][self.tbl][0]
        height = self.coo['card_sizes'][self.tbl][1]

        for i in range(5):
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict[i][0],
                                        self.tlc[1] + func_dict[i][1],
                                        self.tlc[0] + func_dict[i][0] + width, self.tlc[1] + func_dict[i][1] + height)

            card = h.n.recognize_card(pil_image)
            self.cardsOnTable.append(card)
            try:
                pil_image.save('pics/pp/' + card + '.png')
            except:
                pass

        for i in range(5):
            if 'empty' in self.cardsOnTable:
                self.cardsOnTable.remove('empty')
        self.gameStage = ''

        if len(self.cardsOnTable) < 1:
            self.gameStage = "PreFlop"
        elif len(self.cardsOnTable) == 3:
            self.gameStage = "Flop"
        elif len(self.cardsOnTable) == 4:
            self.gameStage = "Turn"
        elif len(self.cardsOnTable) == 5:
            self.gameStage = "River"

        if self.gameStage == '':
            self.logger.critical("Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        self.logger.info("---")
        self.logger.info("Gamestage: " + self.gameStage)
        self.logger.info("Cards on table: " + str(self.cardsOnTable))
        self.logger.info("---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def check_fast_fold(self, h, p, mouse):
        if self.gameStage == "PreFlop":
            m = MonteCarlo()
            crd1, crd2 = m.get_two_short_notation(self.mycards)
            crd1 = crd1.upper()
            crd2 = crd2.upper()
            sheet_name = str(self.position_utg_plus + 1)
            if sheet_name == '6': return True
            sheet = h.preflop_sheet[sheet_name]
            sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())
            handlist = set(sheet['Hand'].tolist())

            found_card = ''

            if crd1 in handlist:
                found_card = crd1
            elif crd2 in handlist:
                found_card = crd2
            elif crd1[0:2] in handlist:
                found_card = crd1[0:2]

            if found_card == '':
                mouse_target = "Fold"
                mouse.mouse_action(mouse_target, self.tlc)
                self.logger.info("-------- FAST FOLD -------")
                return False

        return True

    def get_my_cards(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        def go_through_each_card(img, debugging):
            dic = {}
            for key, value in self.cardImages.items():
                template = value
                method = eval('cv2.TM_SQDIFF_NORMED')

                res = cv2.matchTemplate(img, template, method)

                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                dic = {}
                if min_val < 0.01:
                    self.mycards.append(key)
                dic[key] = min_val

                if debugging:
                    pass
                    # dic = sorted(dic.items(), key=operator.itemgetter(1))
                    # self.logger.debug(str(dic))

        self.gui_signals.signal_progressbar_increase.emit(5)
        self.mycards = []
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        # pil_image.show()
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        # (thresh, img) = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY |
        # cv2.THRESH_OTSU)
        go_through_each_card(img, False)

        if len(self.mycards) == 2:
            self.logger.info("My cards: " + str(self.mycards))
            return True
        else:
            self.logger.debug("Did not find two player cards: " + str(self.mycards))
            go_through_each_card(img, True)
            return False

    def get_my_cards_nn(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.mycards = []
        width = self.coo['card_sizes'][self.tbl][0]
        height = self.coo['card_sizes'][self.tbl][1]
        pil_image1 = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict[0], self.tlc[1] + func_dict[1],
                                     self.tlc[0] + func_dict[0] + width, self.tlc[1] + func_dict[1] + height)
        pil_image2 = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict[2], self.tlc[1] + func_dict[3],
                                     self.tlc[0] + func_dict[2] + width, self.tlc[1] + func_dict[3] + height)

        card1 = h.n.recognize_card(pil_image1)
        card2 = h.n.recognize_card(pil_image2)
        self.mycards.append(card1)
        self.mycards.append(card2)

        try:
            pil_image1.save('pics/pp/' + card1 + '.png')
        except:
            pass
        try:
            pil_image2.save('pics/pp/' + card2 + '.png')
        except:
            pass

        for i in range(2):
            if 'empty' in self.mycards:
                self.mycards.remove('empty')

        if len(self.mycards) == 2:
            self.logger.info("My cards: " + str(self.mycards))
            return True
        else:
            self.logger.debug("Did not find two player cards: " + str(self.mycards))
            return False

    def init_get_other_players_info(self):
        other_player = dict()
        other_player['utg_position'] = ''
        other_player['name'] = ''
        other_player['status'] = ''
        other_player['funds'] = ''
        other_player['pot'] = ''
        other_player['decision'] = ''
        self.other_players = []
        for i in range(5):
            op = copy(other_player)
            op['abs_position'] = i
            self.other_players.append(op)

        return True

    def get_other_player_names(self, p):
        if p.selected_strategy['gather_player_names'] == 1:
            func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
            self.gui_signals.signal_status.emit("Get player names")

            for i, fd in enumerate(func_dict):
                self.gui_signals.signal_progressbar_increase.emit(2)
                pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],
                                            self.tlc[0] + fd[2], self.tlc[1] + fd[3])
                basewidth = 500
                wpercent = (basewidth / float(pil_image.size[0]))
                hsize = int((float(pil_image.size[1]) * float(wpercent)))
                pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
                try:
                    recognizedText = (pytesseract.image_to_string(pil_image, None, False, "-psm 6"))
                    recognizedText = re.sub(r'[\W+]', '', recognizedText)
                    self.logger.debug("Player name: " + recognizedText)
                    self.other_players[i]['name'] = recognizedText
                except Exception as e:
                    self.logger.debug("Pyteseract error in player name recognition: " + str(e))
        return True

    def get_other_player_funds(self, p):
        if p.selected_strategy['gather_player_names'] == 1:
            func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
            self.gui_signals.signal_status.emit("Get player funds")
            for i, fd in enumerate(func_dict, start=0):
                self.gui_signals.signal_progressbar_increase.emit(1)
                pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],
                                            self.tlc[0] + fd[2], self.tlc[1] + fd[3])
                # pil_image.show()
                value = self.get_ocr_float(pil_image, str(inspect.stack()[0][3]))
                value = float(value) if value != '' else ''
                self.other_players[i]['funds'] = value
        return True

    def get_other_player_pots(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get player pots")
        for n in range(5):
            fd = func_dict[n]
            self.gui_signals.signal_progressbar_increase.emit(1)
            screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] - 20 + fd[0], self.tlc[1] + fd[1] - 20,
                                             self.tlc[0] + fd[2] + 20, self.tlc[1] + fd[3] + 20)

            value = self.find_value("other_player_pots", screenshot_pilImage, 0.06) 

            if value != "":
                self.other_players[n]['pot'] = float(value)
                self.logger.debug("FINAL POT after regex: " + str(value))

            if value == "":
                value = ""

        return True

    def get_bot_pot(self, p):
        fd = self.coo[inspect.stack()[0][3]][self.tbl]
        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1], self.tlc[0] + fd[2],
                                    self.tlc[1] + fd[3])

        value = self.find_value("other_player_pots", screenshot_pilImage, 0.0112)                                            

        if value != "":
            self.bot_pot = float(value) 
            self.value = float(value)

        if value == "":
            self.bot_pot = 0
            self.logger.debug("Assuming bot pot is 0")

        return True

    def get_other_player_status(self, p, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get other playsrs' status")

        self.covered_players = 0
        for i, fd in enumerate(func_dict, start=0):
            self.gui_signals.signal_progressbar_increase.emit(1)
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],
                                        self.tlc[0] + fd[2], self.tlc[1] + fd[3])
            img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
            count, points, bestfit, minvalue = self.find_template_on_screen(self.coveredCardHolder, img, 0.01)
            self.logger.debug("Player status: " + str(i) + ": " + str(count))
            if count > 0:
                self.covered_players += 1
                self.other_players[i]['status'] = 1
            else:
                self.other_players[i]['status'] = 0

            self.other_players[i]['utg_position'] = self.get_utg_from_abs_pos(self.other_players[i]['abs_position'],
                                                                              self.dealer_position)

        self.other_active_players = sum([v['status'] for v in self.other_players])
        if self.gameStage == "PreFlop":
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 3 - 1])
        else:
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 1 - 1])
        self.playersAhead = self.other_active_players - self.playersBehind
        self.isHeadsUp = True if self.other_active_players < 2 else False
        self.logger.debug("Other players in the game: " + str(self.other_active_players))
        self.logger.debug("Players behind: " + str(self.playersBehind))
        self.logger.debug("Players ahead: " + str(self.playersAhead))

        if h.round_number == 0:
            reference_pot = float(p.selected_strategy['bigBlind'])
        else:
            reference_pot = self.get_bot_pot(p)

        # get first raiser in (tested for preflop)
        self.first_raiser, \
        self.second_raiser, \
        self.first_caller, \
        self.first_raiser_utg, \
        self.second_raiser_utg, \
        self.first_caller_utg = \
            self.get_raisers_and_callers(p, reference_pot)

        if ((h.previous_decision == "Call" or h.previous_decision == "Call2") and str(h.lastRoundGameID) == str(
                h.GameID)) and \
                not (self.checkButton == True and self.playersAhead == 0):
            self.other_player_has_initiative = True
        else:
            self.other_player_has_initiative = False

        self.logger.info("Other player has initiative: " + str(self.other_player_has_initiative))

        return True

    def get_round_number(self, h):
        if h.histGameStage == self.gameStage and h.lastRoundGameID == h.GameID:
            h.round_number += 1
        else:
            h.round_number = 0
        return True

    def get_dealer_position(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + 0, self.tlc[1] + 0,
                                    self.tlc[0] + 950, self.tlc[1] + 700)

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.dealer, img, 0.05)
        try:
            point = points[0]
        except:
            self.logger.debug("No dealer found")
            return False

        self.position_utg_plus = ''
        for n, fd in enumerate(func_dict, start=0):
            if point[0] > fd[0] and point[1] > fd[1] and point[0] < fd[2] and point[1] < fd[3]:
                self.position_utg_plus = n
                self.dealer_position = (9 - n) % 6  # 0 is myself, 1 is player to the left
                self.logger.info('Bot position is UTG+' + str(self.position_utg_plus))  # 0 mean bot is UTG

        if self.position_utg_plus == '':
            self.position_utg_plus = 0
            self.dealer_position = 3
            self.logger.error('Could not determine dealer position. Assuming UTG')
        else:
            self.logger.info('Dealer position (0 is myself and 1 is next player): ' + str(self.dealer_position))

        self.big_blind_position_abs_all = (self.dealer_position + 2) % 6  # 0 is myself, 1 is player to my left
        self.big_blind_position_abs_op = self.big_blind_position_abs_all - 1

        return True

    def get_total_pot_value(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Get Pot Value")
        self.logger.debug("Get TotalPot value")
        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.totalPotValue  = self.find_value("total_pot_value", screenshot_pilImage, 0.01)    

        if self.totalPotValue != "":
            self.totalPotValue = float(self.totalPotValue)

        if self.totalPotValue == "":           
            self.totalPotValue = 0
            self.logger.warning("Total pot regex problem: " + str(value))
            self.gui_signals.signal_status.emit("Unable to get pot value")
            screenshot_pilImage.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        self.logger.info("Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_round_pot_value(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(2)
        self.gui_signals.signal_status.emit("Get round pot value")
        self.logger.debug("Get round pot value")
        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.round_pot_value = self.find_value("round_pot_value", screenshot_pilImage, 0.06) 

        if self.round_pot_value != "":
            self.round_pot_value = float(self.round_pot_value)

        if self.round_pot_value == "":
            self.round_pot_value = 0
            self.gui_signals.signal_status.emit("Unable to get round pot value")
            self.logger.warning("unable to get round pot value")
            #self.round_pot_value = h.previous_round_pot_value
            screenshot_pilImage.save("pics/ErrRoundPotValue.png")
        return True

    def get_my_funds(self, h, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Get my funds")
        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.myFunds = self.find_value("my_funds", screenshot_pilImage, 0.01) 

        if self.myFunds != "":
            self.myFunds = float(self.myFunds)

        if self.myFunds == "":
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            self.logger.info("myFunds not regognised!")
            self.gui_signals.signal_status.emit("Funds NOT recognised")
            self.logger.warning("Funds NOT recognised. See pics/FundsError.png to see why.")
            self.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)

        self.logger.debug("my_funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get Call value")
        self.gui_signals.signal_progressbar_increase.emit(5)

        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        if not self.checkButton:

            self.currentCallValue = self.find_value("call_and_raise", screenshot_pilImage, 0.01)     

        elif self.checkButton:
            self.currentCallValue = 0

        if self.currentCallValue != "":
            self.getCallButtonValueSuccess = True
        else:
            self.checkButton = True
            self.logger.debug("Assuming check button as call value is zero")
        return True

    def get_current_bet_value(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Get Bet Value")
        self.logger.debug("Get bet value")

        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.currentBetValue = self.find_value("call_and_raise", screenshot_pilImage, 0.01) 

        if self.currentCallValue == '' and p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
            self.logger.warning("Taking call value from button on the right")
            self.currentCallValue = self.currentBetValue
            self.currentBetValue = 9999999

        if self.currentBetValue == '':
            self.logger.warning("No bet value")
            self.currentBetValue = 9999999.0

        if self.currentCallValue == '':
            self.logger.error("Call Value was empty")
            if p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
                self.currentCallValue = self.currentBetValue
                self.currentBetValue = 9999999
            try:
                self.entireScreenPIL.save('log/call_err_debug_fullscreen.png')
            except:
                pass

            self.currentCallValue = 9999999.0

        if self.currentBetValue < self.currentCallValue and not self.allInCallButton:
            self.currentCallValue = self.currentBetValue / 2
            self.BetValueReadError = True
            self.entireScreenPIL.save("pics/BetValueError.png")

        if self.currentBetValue < self.currentCallValue and self.allInCallButton:
            self.currentBetValue = self.currentCallValue + 0.01
            self.BetValueReadError = True
            self.entireScreenPIL.save("pics/BetValueError.png")

        self.logger.info("Final call value: " + str(self.currentCallValue))
        self.logger.info("Final bet value: " + str(self.currentBetValue))
        return True

    def get_lost_everything(self, h, t, p, gui_signals):
        if self.tbl == 'SN': return True
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.lostEverything, img, 0.001)
        if count > 0:
            h.lastGameID = str(h.GameID)
            self.myFundsChange = float(0) - float(h.myFundsHistory[-1])
            self.game_logger.mark_last_game(t, h, p)
            self.gui_signals.signal_status.emit("Everything is lost. Last game has been marked.")
            self.gui_signals.signal_progressbar_reset.emit()
            self.logger.warning("Game over")
            # user_input = input("Press Enter for exit ")
            # gui_signals.signal_curve_chart_update1.emit(h.histEquity, h.histMinCall, h.histMinBet, t.equity,
            #                                             t.minCall, t.minBet,
            #                                             'bo',
            #                                             'ro')
            #
            # gui_signals.signal_curve_chart_update2.emit(t.power1, t.power2, t.minEquityCall, t.minEquityBet,
            #                                             t.smallBlind, t.bigBlind,
            #                                             t.maxValue,
            #                                             t.maxEquityCall, t.max_X, t.maxEquityBet)
            sys.exit()
        else:
            return True

    def get_new_hand(self, mouse, h, p):
        self.gui_signals.signal_progressbar_increase.emit(5)
        if h.previousCards != self.mycards:
            self.logger.info("+++========================== NEW HAND ==========================+++")
            self.time_new_cards_recognised = datetime.datetime.utcnow()
            self.get_game_number_on_screen(h)
            self.get_my_funds(h, p)

            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            cards = ' '.join(self.mycards)
            self.gui_signals.signal_status.emit("New hand: " + str(cards))

            if not len(h.myFundsHistory) == 0:
                self.myFundsChange = float(self.myFunds) - float(h.myFundsHistory[-1])
                self.game_logger.mark_last_game(self, h, p)

            t_algo = threading.Thread(name='Algo', target=self.call_genetic_algorithm, args=(p,))
            t_algo.daemon = True
            t_algo.start()

            self.gui_signals.signal_funds_chart_update.emit(self.game_logger)
            self.gui_signals.signal_bar_chart_update.emit(self.game_logger, p.current_strategy)

            h.myLastBet = 0
            h.myFundsHistory.append(self.myFunds)
            h.previousCards = self.mycards
            h.lastSecondRoundAdjustment = 0
            h.last_round_bluff = False  # reset the bluffing marker
            h.round_number = 0

            mouse.move_mouse_away_from_buttons_jump()
            self.take_screenshot(False, p)
        else:
            self.logger.info("Game number on screen: " + str(h.game_number_on_screen))
            self.get_my_funds(h, p)

        return True

    def upload_collusion_wrapper(self, p, h):
        if not (h.GameID, self.gameStage) in h.uploader:
            h.uploader[(h.GameID, self.gameStage)] = True
            self.game_logger.upload_collusion_data(h.game_number_on_screen, self.mycards, p, self.gameStage)
        return True

    def get_game_number_on_screen(self, h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        screenshot_pilImage = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        #Bild vergrößern
        basewidth = 150
        hsize = 40
        screenshot_pilImage = screenshot_pilImage.resize((basewidth,hsize), Image.ANTIALIAS)
 
        self.Game_Number = int(self.find_value("game_number", screenshot_pilImage, 0.01)) 

        h.game_number_on_screen = self.Game_Number

        self.logger.info("Game Number: " + str(self.Game_Number))
 
        return True

    def get_snowie_advice(self, p, h):
        # if self.tbl == 'SN':
        #     func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        #     img = cv2.cvtColor(np.array(self.entireScreenPIL), cv2.COLOR_BGR2RGB)
        #     count1, points1, bestfit, minvalue = self.find_template_on_screen(self.topLeftCorner_snowieadvice1, img,
        #                                                                       0.07)
        #     # count2, points2, _ = self.find_template_on_screen(self.topLeftCorner_snowieadvice2, img, 0.07)
        #
        #     if count1 == 1:
        #         tlc_adv1 = points1[0]
        #         # tlc_adv2 = points2[0]
        #
        #         fd = func_dict['fold']
        #         fold_image = self.crop_image(self.entireScreenPIL, tlc_adv1[0] + fd['x1'], tlc_adv1[1] + fd['y1'],
        #                                      tlc_adv1[0] + fd['x2'], tlc_adv1[1] + fd['y2'])
        #         fd = func_dict['call']
        #         call_image = self.crop_image(self.entireScreenPIL, tlc_adv1[0] + fd['x1'], tlc_adv1[1] + fd['y1'],
        #                                      tlc_adv1[0] + fd['x2'], tlc_adv1[1] + fd['y2'])
        #         fd = func_dict['raise']
        #         raise_image = self.crop_image(self.entireScreenPIL, tlc_adv1[0] + fd['x1'], tlc_adv1[1] + fd['y1'],
        #                                       tlc_adv1[0] + fd['x2'], tlc_adv1[1] + fd['y2'])
        #         # fd=func_dict['betsize']
        #         # betsize_image = self.crop_image(self.entireScreenPIL, tlc_adv2[0] + fd['x1'], tlc_adv2[1] + fd['y1'],
        #         #                             tlc_adv2[0] + fd['x2'], tlc_adv2[1] + fd['y2'])
        #
        #         self.fold_advice = float(self.get_ocr_float(fold_image, str(inspect.stack()[0][3])))
        #         self.call_advice = float(self.get_ocr_float(call_image, str(inspect.stack()[0][3])))
        #         try:
        #             self.raise_advice = float(self.get_ocr_float(raise_image, str(inspect.stack()[0][3])))
        #         except:
        #             self.raise_advice = np.nan
        #         # self.betzise_advice = float(self.get_ocr_float(betsize_image, str(inspect.stack()[0][3])))
        #
        #         self.logger.info("Fold Advice: {0}".format(self.fold_advice))
        #         self.logger.info("Call Advice: {0}".format(self.call_advice))
        #         self.logger.info("Raise Advice: {0}".format(self.raise_advice))
        #         # logger.info("Betsize Advice: {0}".format(self.betzise_advice))
        #     else:
        #         self.logger.warning("Could not identify snowie advice window. minValue: {0}".format(minvalue))

        return True
