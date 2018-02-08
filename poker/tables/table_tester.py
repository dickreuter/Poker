#!/usr/bin/env python
import sys

import cv2
import numpy as np
import pytesseract
from PIL import Image
from unittest.mock import MagicMock
from poker.decisionmaker.montecarlo_python import MonteCarlo
from poker.main import ConfigObj
from poker.table_analysers.table_screen_based import (ImageFilter,
    TableScreenBased, copy, inspect)
from poker.tools.mongo_manager import GameLogger, re


class MyTableScreenBased(TableScreenBased):
    def __init__(self, p):
        self.dealer_position = -1
        self.big_blind_position_abs_op = -1
        self.position_utg_plus = -1
        game_logger = GameLogger()
        gui_signals = MagicMock()

        super(TableScreenBased, self).__init__(p, gui_signals, game_logger, '3.05')

    def setCoordinates(self, coordinates):
        self.coo = coordinates

    def set_screenshot(self, table):
        config = ConfigObj("config.ini")
        control = config['control']
        self.entireScreenPIL = Image.open('tables/backgrounds/'+table+'.png')

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
            print("debug : Top left corner found")
            return True
        else:
            print("debug : Top left corner NOT found -> stop")
            return False

    def check_for_button(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        cards = ' '.join(self.mycards)
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        count, points, bestfit, _ = self.find_template_on_screen(self.button, img, func_dict['tolerance'])

        if count > 0:
            print("info : Buttons Found, cards: " + str(cards))
            return True

        else:
            print("debug : No buttons found")
            return False

    def check_for_checkbutton(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Checking for check button")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        count, points, bestfit, minval = self.find_template_on_screen(self.check, img, func_dict['tolerance'])

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            print("debug : check button found")
        else:
            self.checkButton = False
            print("debug : no check button found")
        print("debug : Check: " + str(self.checkButton))
        return True

    def check_for_imback(self):
        if self.tbl == 'SN': return True
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        # Convert RGB to BGR
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, minvalue = self.find_template_on_screen(self.ImBack, img, func_dict['tolerance'])
        if count > 0:
            return False
        else:
            return True

    def check_for_call(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Check for Call")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        count, points, bestfit, _ = self.find_template_on_screen(self.call, img, func_dict['tolerance'])
        if count > 0:
            self.callButton = True
            print("debug : Call button found")
        else:
            self.callButton = False
            print("info : Call button NOT found")
            pil_image.save("pics/debug_nocall.png")
        return True

    def check_for_betbutton(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Check for betbutton")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        count, points, bestfit, min_val = self.find_template_on_screen(self.betbutton, img, func_dict['tolerance'])
        if count > 0:
            self.bet_button_found = True
            print("debug : Bet button found")
        else:
            self.bet_button_found = False
            print("info : Bet button NOT found")
        return True

    def check_for_allincall(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Check for All in call button")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        # Convert RGB to BGR
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
            print("debug : All in call button found")
        else:
            self.allInCallButton = False
            print("debug : All in call button not found")

        if not self.bet_button_found:
            self.allInCallButton = True
            print("debug : Assume all in call because there is no bet button")

        return True

    def get_table_cards(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Get Table cards")
        self.cardsOnTable = []
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
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
            print("critical : Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        print("info : ---")
        print("info : Gamestage: " + self.gameStage)
        print("info : Cards on table: " + str(self.cardsOnTable))
        print("info : ---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def get_table_cards_nn(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        self.cardsOnTable = []
        width = self.coo['card_sizes'][self.tbl][0]
        height = self.coo['card_sizes'][self.tbl][1]

        for i in range(5):
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict[i][0],
                                        self.tlc[1] + func_dict[i][1],
                                        self.tlc[0] + func_dict[i][0] + width, self.tlc[1] + func_dict[i][1] + height)
            cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
            cv2.waitKey()
            cv2.destroyAllWindows()

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
            print("critical : Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        print("info : ---")
        print("info : Gamestage: " + self.gameStage)
        print("info : Cards on table: " + str(self.cardsOnTable))
        print("info : ---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def get_my_cards(self):
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
                    # print(sdebug : tr(dic))

        self.mycards = []
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        # cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        # (thresh, img) = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY |
        # cv2.THRESH_OTSU)
        go_through_each_card(img, False)

        if len(self.mycards) == 2:
            print("info : My cards: " + str(self.mycards))
            return True
        else:
            print("debug : Did not find two player cards: " + str(self.mycards))
            go_through_each_card(img, True)
            return False

    def get_my_cards_nn(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.mycards = []
        width = self.coo['card_sizes'][self.tbl][0]
        height = self.coo['card_sizes'][self.tbl][1]
        pil_image1 = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                     self.tlc[0] + func_dict['x1'] + width, self.tlc[1] + func_dict['y1'] + height)
        pil_image2 = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'],
                                     self.tlc[0] + func_dict['x2'] + width, self.tlc[1] + func_dict['y2'] + height)

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
            print("info : My cards: " + str(self.mycards))
            return True
        else:
            print("debug : Did not find two player cards: " + str(self.mycards))
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

    def pre_process_text_image(self, pil_image):
        # re scale
        basewidth = 500
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)


        # to improve this, the variation should be used on HSV value component, image should be converted in HSV.
        # variation = 20
        # adds slight variation
        # textColorRange = [max(textColor - variation, 0), min(textColor + variation, 255)]
        # print('range : '+str(textColorRange))
        # textImage = cv2.inRange(opencvGrayscale, textColorRange[0], textColorRange[1])

        # remove noise
        opencvGrayscale = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2GRAY)
        kernel = np.ones((1, 1), np.uint8)
        opencvGrayscale = cv2.erode(opencvGrayscale, kernel, iterations=2)

        # textImage = cv2.GaussianBlur(opencvGrayscale, (5,5),0)
        ret3, textImage = cv2.threshold(opencvGrayscale, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        # textImage = cv2.adaptiveThreshold(opencvGrayscale, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,11,2)

        return textImage

    def get_other_player_names(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        for i, fd in enumerate(func_dict):
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd['x1'], self.tlc[1] + fd['y1'],
                                        self.tlc[0] + fd['x2'], self.tlc[1] + fd['y2'])
            basewidth = 500
            wpercent = (basewidth / float(pil_image.size[0]))
            hsize = int((float(pil_image.size[1]) * float(wpercent)))
            pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
            #pre_processed = self.pre_process_text_image(pil_image)


            #cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
            cv2.waitKey()

            try:
                recognizedText = (pytesseract.image_to_string(pil_image))
                recognizedText = re.sub(r'[\W+]', '', recognizedText)
                print("debug : Player name: " + recognizedText)
                self.other_players[i]['name'] = recognizedText
            except Exception as e:
                print("debug : Pyteseract error in player name recognition: " + str(e))

        return True

    def get_other_player_funds(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        for i, fd in enumerate(func_dict, start=0):
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd['x1'], self.tlc[1] + fd['y1'],
                                        self.tlc[0] + fd['x2'], self.tlc[1] + fd['y2'])
            cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
            value = self.get_ocr_float(pil_image, str(inspect.stack()[0][3]))
            value = float(value) if value != '' else ''
            self.other_players[i]['funds'] = value
            print('get '+self.other_players[i]['name']+' funds: '+str(value))
            cv2.waitKey()
        return True

    def get_other_player_pots(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        for n in range(5):
            fd = func_dict[n]
            pot_area_image = self.crop_image(self.entireScreenPIL, self.tlc[0] - 20 + fd['x1'], self.tlc[1] + fd['y1'] - 20,
                                             self.tlc[0] + fd['x2'] + 20, self.tlc[1] + fd['y2'] + 20)
            img = cv2.cvtColor(np.array(pot_area_image), cv2.COLOR_BGR2RGB)
            count, points, bestfit, minvalue = self.find_template_on_screen(self.smallDollarSign1, img,
                                                                            float(func_dict[5]))
            has_small_dollarsign = count > 0
            if has_small_dollarsign:
                pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd['x1'], self.tlc[1] + fd['y1'],
                                            self.tlc[0] + fd['x2'], self.tlc[1] + fd['y2'])
                method = func_dict[6]
                value = self.get_ocr_float(pil_image, str(inspect.stack()[0][3]), force_method=method)
                print(value)
                cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))

                try:
                    if not str(value) == '':
                        value = re.findall(r'\d{1}\.\d{1,2}', str(value))[0]
                except:
                    print("warning : Player pot regex problem: " + str(value))
                    value = ''
                value = float(value) if value != '' else ''
                print("debug : FINAL POT after regex: " + str(value))
                self.other_players[n]['pot'] = value
        return True

    def get_bot_pot(self, p):
        fd = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd['x1'], self.tlc[1] + fd['y1'], self.tlc[0] + fd['x2'],
                                    self.tlc[1] + fd['y2'])
        value = self.get_ocr_float(pil_image, str(inspect.stack()[0][3]), force_method=1)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        try:
            value = float(re.findall(r'\d{1}\.\d{1,2}', str(value))[0])
        except:
            print("debug : Assuming bot pot is 0")
            value = 0
        self.bot_pot = value
        return value

    def get_other_player_status(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        self.covered_players = 0
        for i, fd in enumerate(func_dict, start=0):
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd['x1'], self.tlc[1] + fd['y1'],
                                        self.tlc[0] + fd['x2'], self.tlc[1] + fd['y2'])
            img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
            cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))

            count, points, bestfit, minvalue = self.find_template_on_screen(self.coveredCardHolder, img, 0.01)
            print("debug : Player status: " + str(i) + ": " + str(count))
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
        print("debug : Other players in the game: " + str(self.other_active_players))
        print("debug : Players behind: " + str(self.playersBehind))
        print("debug : Players ahead: " + str(self.playersAhead))

        reference_pot = self.get_bot_pot(p)

        # get first raiser in (tested for preflop)
        self.first_raiser, \
        self.second_raiser, \
        self.first_caller, \
        self.first_raiser_utg, \
        self.second_raiser_utg, \
        self.first_caller_utg = \
        self.get_raisers_and_callers(p, reference_pot)

        self.other_player_has_initiative = True

        print("info : Other player has initiative: " + str(self.other_player_has_initiative))

        return True

    def get_round_number(self):
        return True

    def get_dealer_position(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + 0, self.tlc[1] + 0,
                                    self.tlc[0] + 950, self.tlc[1] + 700)

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit, _ = self.find_template_on_screen(self.dealer, img, 0.05)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
        try:
            point = points[0]
        except:
            print("debug : No dealer found")
            return False

        self.position_utg_plus = ''
        for n, fd in enumerate(func_dict, start=0):
            if point[0] > fd['x1'] and point[1] > fd['y1'] and point[0] < fd['x2'] and point[1] < fd['y2']:
                self.position_utg_plus = n
                self.dealer_position = (9 - n) % 6  # 0 is myself, 1 is player to the left
                print('info : Bot position is UTG+' + str(self.position_utg_plus))  # 0 mean bot is UTG

        if self.position_utg_plus == '':
            self.position_utg_plus = 0
            self.dealer_position = 3
            print('error : Could not determine dealer position. Assuming UTG')
        else:
            print('info : Dealer position (0 is myself and 1 is next player): ' + str(self.dealer_position))

        self.big_blind_position_abs_all = (self.dealer_position + 2) % 6  # 0 is myself, 1 is player to my left
        self.big_blind_position_abs_op = self.big_blind_position_abs_all - 1

        return True

    def get_total_pot_value(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Get TotalPot value")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        # pot_image = self.pre_process_text_image(pil_image)

        cv2.imshow(inspect.stack()[0][3],  cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        value = self.get_ocr_float(pil_image, 'TotalPotValue', force_method=1)

        if not isinstance(value, float) or value == 0:
            print("warning : Total pot regex problem: " + str(value))
            value = ''
            print("warning : unable to get pot value")
            pil_image.save("pics/ErrPotValue.png")

        if value == '':
            self.totalPotValue = 0
        else:
            self.totalPotValue = value

        print("info : Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_round_pot_value(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Get round pot value")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        value = self.get_ocr_float(pil_image, 'TotalPotValue', force_method=1)

        if not isinstance(value, float) or value == 0:
            print("warning : Round pot regex problem: " + str(value))
            value = ''
            print("warning : unable to get round pot value")
            pil_image.save("pics/ErrRoundPotValue.png")

        if value == '':
            self.round_pot_value = 0
        else:
            self.round_pot_value = value

        print("info : Final round pot Value: " + str(self.round_pot_value))
        return True

    def get_my_funds(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Get my funds")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        if p.selected_strategy['pokerSite'][0:2] == 'PP':
            basewidth = 200
            wpercent = (basewidth / float(pil_image.size[0]))
            hsize = int((float(pil_image.size[1]) * float(wpercent)))
            pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        pil_image_filtered = pil_image.filter(ImageFilter.ModeFilter)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        pil_image_filtered2 = pil_image.filter(ImageFilter.MedianFilter)

        self.myFundsError = False
        try:
            pil_image.save("pics/myFunds.png")
        except:
            print("info : Could not save myFunds.png")

        self.myFunds = self.get_ocr_float(pil_image, 'MyFunds')
        if self.myFunds == '':
            self.myFunds = self.get_ocr_float(pil_image_filtered, 'MyFunds')
        if self.myFunds == '':
            self.myFunds = self.get_ocr_float(pil_image_filtered2, 'MyFunds')

        if self.myFunds == '':
            self.myFundsError = True
            print("info : myFunds not regognised!")
            print("warning : Funds NOT recognised. See pics/FundsError.png to see why.")
            self.entireScreenPIL.save("pics/FundsError.png")
        print("debug : Funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]

        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        if not self.checkButton:
            self.currentCallValue = self.get_ocr_float(pil_image, 'CallValue')
        elif self.checkButton:
            self.currentCallValue = 0

        if self.currentCallValue != '':
            self.getCallButtonValueSuccess = True
        else:
            self.checkButton = True
            print("debug : Assuming check button as call value is zero")
            try:
                pil_image.save("pics/ErrCallValue.png")
            except:
                pass

        return True

    def get_current_bet_value(self, p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        print("debug : Get bet value")

        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        self.currentBetValue = self.get_ocr_float(pil_image, 'BetValue')

        if self.currentCallValue == '' and p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
            print("warning : Taking call value from button on the right")
            self.currentCallValue = self.currentBetValue
            self.currentBetValue = 9999999

        if self.currentBetValue == '':
            print("warning : No bet value")
            self.currentBetValue = 9999999.0

        if self.currentCallValue == '':
            print("error : Call Value was empty")
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

        print("info : Final call value: " + str(self.currentCallValue))
        print("info : Final bet value: " + str(self.currentBetValue))
        return True

    def get_lost_everything(self, p):
        if self.tbl == 'SN': return True
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        count, points, bestfit, _ = self.find_template_on_screen(self.lostEverything, img, 0.001)
        if count > 0:
            self.game_logger.mark_last_game(t, p)
            print("warning : Game over")
            sys.exit()
        else:
            return True


    def get_game_number_on_screen(self):
        try:
            func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        except KeyError:
            return True

        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        basewidth = 200
        cv2.imshow(inspect.stack()[0][3], cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR))
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        img_resized = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        img_min = img_resized.filter(ImageFilter.MinFilter)
        # img_med = img_resized.filter(ImageFilter.MedianFilter)
        img_mod = img_resized.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)

        return True
