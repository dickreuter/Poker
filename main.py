import threading
from gui.gui_qt_logic import *
import matplotlib
matplotlib.use('Qt5Agg')
import operator
import os.path
import cv2  # opencv 3.0
import pytesseract
import re
from PIL import Image, ImageGrab, ImageDraw, ImageFilter
from decisionmaker.decisionmaker import *
from decisionmaker.montecarlo_python import *
from mouse_mover import *
import inspect
from captcha.captcha_manager import solve_captcha
from vbox_manager import VirtualBoxController

version=1.69
IP=''

class History(object):
    def __init__(self):
        # keeps values of the last round
        self.previousPot = 0
        self.previousCards = []
        self.myLastBet = 0
        self.histGameStage = ""
        self.myFundsHistory = [2.0]
        self.losses = 0
        self.wins = 0
        self.totalGames = 0
        self.GameID = int(np.round(np.random.uniform(0, 999999999), 0))  # first game ID
        self.lastRoundGameID = 0
        self.lastSecondRoundAdjustment = 0
        self.lastGameID = "0"
        self.histDecision = 0
        self.histEquity = 0
        self.histMinCall = 0
        self.histMinBet = 0
        self.histPlayerPots = 0
        self.first_raiser=np.nan
        self.previous_decision=0
        self.last_round_bluff=False
        self.uploader={}

class Table(object):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self,gui_signals,logger):
        self.version=version
        self.ip=IP
        self.load_templates()
        self.load_coordinates()
        self.logger=logger
        self.gui_signals=gui_signals

    def load_templates(self):
        self.cardImages = dict()
        self.img = dict()
        p = StrategyHandler()
        p.read_strategy()
        self.tbl=p.selected_strategy['pokerSite']
        values = "23456789TJQKA"
        suites = "CDHS"
        for x in values:
            for y in suites:
                name = "pics/" + self.tbl[0:2] + "/" + x + y + ".png"
                if os.path.exists(name) == True:
                    self.img[x + y] = Image.open(name)
                    self.cardImages[x + y] = cv2.cvtColor(np.array(self.img[x + y]), cv2.COLOR_BGR2RGB)
                    # (thresh, self.cardImages[x + y]) =
                    # cv2.threshold(self.cardImages[x + y], 128, 255,
                    # cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                else:
                    self.logger.critical("Card Temlate File not found: " + str(x) + str(y) + ".png")

        name = "pics/" + self.tbl[0:2] + "/button.png"
        template = Image.open(name)
        self.button = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/topleft.png"
        template = Image.open(name)
        self.topLeftCorner = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

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

        if self.tbl[0:2] == "PP":
            name = "pics/" + self.tbl[0:2] + "/smalldollarsign2.png"
            template = Image.open(name)
            self.smallDollarSign2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

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
        with open('coordinates.txt','r') as inf:
            c = eval(inf.read())
            self.coo=c['screen_scraping']

    def take_screenshot(self,initial,p):
        if initial:
            self.gui_signals.signal_status.emit("")
            self.gui_signals.signal_progressbar_reset.emit()
            if p.exit_thread == True: sys.exit()
            if p.pause == True:
                while p.pause == True:
                    time.sleep(1)
                    if p.exit_thread == True: sys.exit()

        time.sleep(0.1)
        config = ConfigObj("config.ini")
        control = config['control']
        if control=='Direct mouse control':
            self.entireScreenPIL = ImageGrab.grab()

        else:
            try:
                vb = VirtualBoxController()
                self.entireScreenPIL = vb.get_screenshot_vbox()
                self.logger.info("Screenshot taken from virtual machine")
            except:
                self.logger.warning("No virtual machine found")
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
        return count, points, bestFit

    def get_ocr_float(self, img_orig, name, force_method=0):
        def fix_number(t):
            t = t.replace("I", "1").replace("O", "0").replace("o", "0")\
                .replace("-", ".").replace("D", "0").replace("I","1").replace("_",".").replace("-", ".")
            t = re.sub("[^0123456789\.]", "", t)
            try:
                if t[0] == ".": t = t[1:]
            except: pass
            try:
                if t[-1] == ".": t = t[0:-1]
            except: pass
            try:
                if t[-1]==".": t = t[0:-1]
            except: pass
            try:
                if t[-1] == "-": t = t[0:-1]
            except: pass
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

        if force_method==0:
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
            if force_method==1 or fix_number(lst[0])== '':
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

    def call_genetic_algorithm(self):
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Updating charts and work in background")
        n = L.get_game_count(p.current_strategy)
        lg = int(
            p.selected_strategy['considerLastGames'])  # only consider lg last games to see if there was a loss
        f = L.get_strategy_return(p.current_strategy, lg)
        self.gui_signals.signal_lcd_number_update.emit('gamenumber',int(n))
        self.gui_signals.signal_lcd_number_update.emit('winnings', f)
        self.logger.info("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))
        if n % int(p.selected_strategy['strategyIterationGames']) == 0 and f < float(
                p.selected_strategy['minimumLossForIteration']):
            self.gui_signals.signal_status.emit("***Improving current strategy***")
            self.logger.info("***Improving current strategy***")
            #winsound.Beep(500, 100)
            GeneticAlgorithm(True, logger, L)
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

    def find_item_location_in_crop(self,x1,y1,x2,y2,template,screentho):
        pass

class TableScreenBased(Table):
    def get_top_left_corner(self,p):
        self.current_strategy = p.current_strategy # needed for mongo manager
        img = cv2.cvtColor(np.array(self.entireScreenPIL), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.topLeftCorner, img, 0.01)
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
        func_dict=self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        cards = ' '.join(self.mycards)
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1]+func_dict['y1'],self.tlc[0]+func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.button, img, func_dict['tolerance'])

        if count > 0:
            self.gui_signals.signal_status.emit("Buttons found, cards: " + str(cards))
            self.logger.info("Buttons Found, cards: " + str(cards))
            return True

        else:
            self.logger.debug("No buttons found")
            return False

    def check_for_checkbutton(self):
        func_dict=self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Check for Check")
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Checking for check button")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.check, img, func_dict['tolerance'])

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
        mouse.move_mouse_away_from_buttons(logger)
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.ImBack, img, func_dict['tolerance'])
        if count > 0:
            self.gui_signals.signal_status.emit("I am back found")
            mouse.mouse_action("Imback", self.tlc, logger)
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
        count, points, bestfit = self.find_template_on_screen(self.call, img, func_dict['tolerance'])
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
        count, points, bestfit = self.find_template_on_screen(self.betbutton, img, func_dict['tolerance'])
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
        count, points, bestfit = self.find_template_on_screen(self.allInCallButton, img, 0.01)
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

    def get_table_cards(self,h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Get Table cards")
        self.cardsOnTable = []
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)


        for key, value in self.cardImages.items():
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
            self.logger.critical("Table cards not recognised correctly")
            exit()

        self.logger.info("---")
        self.logger.info("Gamestage: " + self.gameStage)
        self.logger.info("Cards on table: " + str(self.cardsOnTable))
        self.logger.info("---")

        if h.histGameStage == self.gameStage and h.lastRoundGameID == h.GameID:
            h.round_number+=1
        else:
            h.round_number=0

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def get_my_cards(self,h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        def go_through_each_card(img, debugging):
            dic = {}
            for key, value in self.cardImages.items():
                template = value
                method = eval('cv2.TM_SQDIFF_NORMED')

                res = cv2.matchTemplate(img, template, method)

                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                dic={}
                if min_val < 0.01:
                    self.mycards.append(key)
                dic[key] = min_val

                ##dic = sorted(dic.items(), key=operator.itemgetter(1))
                #self.logger.debug(str(dic))

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
            self.myFundsChange = float(self.myFunds) - float(str(h.myFundsHistory[-1]).strip('[]'))
            self.logger.info("My cards: " + str(self.mycards))
            return True
        else:
            self.logger.debug("Did not find two player cards: " + str(self.mycards))
            # go_through_each_card(img,True)
            return False

    def init_get_other_players_info(self):
        other_player=dict()
        other_player['utg_position'] = ''
        other_player['name'] = ''
        other_player['status'] = ''
        other_player['funds'] = ''
        other_player['pot'] = ''
        self.other_players = []
        for i in range (5):
            op=copy(other_player)
            op['abs_position']=i
            self.other_players.append(op)


        return True

    def get_other_player_names(self,p):
        if p.selected_strategy['gather_player_names']==1:
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
                    self.logger.debug("Player name: "+recognizedText)
                    self.other_players[i]['name'] = recognizedText
                except Exception as e:
                    self.logger.debug("Pyteseract error in player name recognition: " + str(e))
        return True

    def get_other_player_funds(self,p):
        if p.selected_strategy['gather_player_names'] == 1:
            func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
            self.gui_signals.signal_status.emit("Get player funds")
            for i, fd in enumerate(func_dict, start=0):
                self.gui_signals.signal_progressbar_increase.emit(1)
                pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],self.tlc[0] + fd[2], self.tlc[1] + fd[3])
                #pil_image.show()
                value=self.get_ocr_float(pil_image,str(inspect.stack()[0][3]))
                value = float(value) if value != '' else ''
                self.other_players[i]['funds'] = value
        return True

    def get_other_player_pots(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get player pots")
        for n, fd in enumerate(func_dict, start=0):
            self.gui_signals.signal_progressbar_increase.emit(1)
            pot_area_image = self.crop_image(self.entireScreenPIL, self.tlc[0]-20 + fd[0], self.tlc[1] + fd[1]-20,self.tlc[0] + fd[2]+20, self.tlc[1] + fd[3]+20)
            img = cv2.cvtColor(np.array(pot_area_image), cv2.COLOR_BGR2RGB)
            count, points, bestfit = self.find_template_on_screen(self.smallDollarSign1, img, 0.2)
            has_small_dollarsign=count>0
            if has_small_dollarsign:
                pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],self.tlc[0] + fd[2], self.tlc[1] + fd[3])
                value = self.get_ocr_float(pil_image, str(inspect.stack()[0][3]), force_method=1)
                try:
                    value = re.findall(r'\d{1}\.\d{1,2}', str(value))[0]
                except:
                    self.logger.warning("Player pot regex problem: "+str(value))
                    value=''
                value=float(value) if value!='' else ''
                self.logger.debug("FINAL POT after regex: "+str(value))
                self.other_players[n]['pot'] = value
        return True

    def get_other_player_status(self,p,h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get other playsrs' status")

        self.covered_players=0
        for i, fd in enumerate(func_dict, start=0):
            self.gui_signals.signal_progressbar_increase.emit(1)
            pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],self.tlc[0] + fd[2], self.tlc[1] + fd[3])
            img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
            count, points, bestfit = self.find_template_on_screen(self.coveredCardHolder, img, 0.01)
            self.logger.debug("Player status: " + str(i)+": "+str(count))
            if count>0:
                self.covered_players+=1
                self.other_players[i]['status'] = 1
            else:
                self.other_players[i]['status'] = 0

            self.other_players[i]['utg_position'] = (self.other_players[i]['abs_position']-self.dealer_position+4) %6


        self.other_active_players=sum([v['status']  for v in self.other_players])
        if self.gameStage=="PreFlop":
            self.playersBehind=sum([v['status']  for v in self.other_players if v['abs_position']>=self.dealer_position+3-1])
        else:
            self.playersBehind = sum([v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position+1-1])
        self.playersAhead = self.other_active_players-self.playersBehind
        self.isHeadsUp=True if self.other_active_players<2 else False
        self.logger.debug("Other players in the game: "+str(self.other_active_players))
        self.logger.debug("Players behind: " + str(self.playersBehind))
        self.logger.debug("Players ahead: " + str(self.playersAhead))

        # get first raiser in (tested for preflop)
        self.first_raiser=np.nan
        self.second_raiser=np.nan
        self.first_caller = np.nan
        for n in range(5):
            i=(self.dealer_position+n+3-2)%5 #less mysself as 0 is now first other player to my left and no longer myself
            self.logger.debug("Go through pots to find raiser abs:: "+str(i)+": "+str(self.other_players[i]['pot']))
            if self.other_players[i]['pot']!='': # check if not empty (otherwise can't convert string)
                if self.other_players[i]['pot'] > float(p.selected_strategy['bigBlind']):
                    if np.isnan(self.first_raiser):
                        self.first_raiser=int(i)
                        self.first_raiser_pot = self.other_players[i]['pot']
                    else:
                        if self.other_players[i]['pot']>self.first_raiser_pot:
                            self.second_raiser = int(i)

        self.logger.debug("First raiser abs: " + str(self.first_raiser))
        self.first_raiser_utg=(self.first_raiser - self.dealer_position+4) % 6
        self.logger.info("First raiser utg+" + str(self.first_raiser_utg))
        self.highest_raiser = np.nanmax([self.first_raiser, self.second_raiser])

        self.logger.debug("Second raiser abs: " + str(self.second_raiser))
        self.logger.info("Highest raiser abs: " + str(self.highest_raiser))

        first_possible_caller=int(self.big_blind_position_abs_op+1 if np.isnan(self.highest_raiser) else self.highest_raiser+1)
        self.logger.debug("First possible potential caller is: "+str(first_possible_caller))

        # get first caller after raise in preflop
        for n in list(range(first_possible_caller,5)): # n is absolute position of other player, 0 is player to my left
            self.logger.debug("Go through pots to find caller abs: " + str(n) + ": " + str(self.other_players[n]['pot']))
            if self.other_players[n]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if (self.other_players[n]['pot'] == float(p.selected_strategy['bigBlind']) and not n==self.big_blind_position_abs_op) or \
                self.other_players[n]['pot'] > float(p.selected_strategy['bigBlind']):
                    self.first_caller = int(n)
                    break



        self.logger.debug("First caller abs: " + str(self.first_caller))
        self.first_caller_utg=(self.first_caller - self.dealer_position +4) % 6
        self.logger.info("First caller utg+" + str(self.first_caller_utg))

        if (h.previous_decision=="Call" or h.previous_decision=="Call2") and str(h.lastRoundGameID) == str(h.GameID):
            self.other_player_has_initiative=True
        else:
            self.other_player_has_initiative = False


        self.logger.debug("Other player has initiative: "+str(self.other_player_has_initiative))

        return True

    def get_dealer_position(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Analyse dealer position")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + 0, self.tlc[1] + 0,
                                    self.tlc[0] +800, self.tlc[1] + 500)

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.dealer, img, 0.01)
        point=points[0]

        self.position_utg_plus = ''
        for n, fd in enumerate(func_dict, start=0):
            if point[0]>fd[0] and point[1]>fd[1] and point[0]<fd[2] and point[1]<fd[3]:
                self.position_utg_plus=n
                self.dealer_position = (9-n)%6 #0 is myself, 1 is player to the left
                self.logger.info('Bot position is UTG+'+str(self.position_utg_plus)) # 0 mean bot is UTG

        if self.position_utg_plus=='':
            self.position_utg_plus=0
            self.dealer_position = 3
            self.logger.error('Could not determine dealer position. Assuming UTG')
        else:
            self.logger.info('Dealer position (0 is myself and 1 is to my left): '+str(self.dealer_position))

        self.big_blind_position_abs_all = (self.dealer_position+2)%6 #0 is myself, 1 is player to my left
        self.big_blind_position_abs_op=self.big_blind_position_abs_all-1

        return True

    def get_total_pot_value(self,h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Get Pot Value")
        self.logger.debug("Get TotalPot value")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.totalPotValue = self.get_ocr_float(pil_image, 'TotalPotValue')

        if self.totalPotValue=='': self.totalPotValue=0
        if self.totalPotValue < 0.01:
            self.logger.info("unable to get pot value")
            self.gui_signals.signal_status.emit("Unable to get pot value")
            time.sleep(1)
            pil_image.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        self.logger.info("Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_my_funds(self,h):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.debug("Get my funds")
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])


        if p.selected_strategy['pokerSite'][0:2]=='PP':
            basewidth = 200
            wpercent = (basewidth / float(pil_image.size[0]))
            hsize = int((float(pil_image.size[1]) * float(wpercent)))
            pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
            pil_image_filtered = pil_image.filter(ImageFilter.ModeFilter)
            pil_image_filtered2 = pil_image.filter(ImageFilter.MedianFilter)

        self.myFundsError = False
        try:
            pil_image.save("pics/myFunds.png")
        except:
            self.logger.info("Could not save myFunds.png")


        self.myFunds = self.get_ocr_float(pil_image, 'MyFunds')

        if self.myFunds == '':
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            self.logger.info("myFunds not regognised!")
            self.gui_signals.signal_status.emit("!!Funds NOT recognised!!")
            self.logger.warning("!!Funds NOT recognised!!")
            self.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)
        self.logger.info("Funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self,p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_status.emit("Get Call value")
        self.gui_signals.signal_progressbar_increase.emit(5)

        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        if not self.checkButton: self.currentCallValue = self.get_ocr_float(pil_image, 'CallValue')
        elif self.checkButton: self.currentCallValue=0


        if self.currentCallValue!='':  self.getCallButtonValueSuccess = True
        else:
            try:
                pil_image.save("pics/ErrCallValue.png")
            except:
                pass


        return True

    def get_current_bet_value(self,p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Get Bet Value")
        self.logger.debug("Get bet value")

        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])

        self.currentBetValue = self.get_ocr_float(pil_image, 'BetValue')

        if self.currentCallValue=='' and p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
            self.logger.warning("Taking call value from button on the right")
            self.currentCallValue = self.currentBetValue
            self.currentBetValue=9999999


        if self.currentBetValue == '':
            self.logger.warning("No bet value")
            self.currentBetValue = 9999999.0

        if self.currentCallValue=='':
            self.logger.error("Call Value was empty. ")
            if p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
                self.currentCallValue = self.currentBetValue
                self.currentBetValue=9999999
            try:
                self.entireScreenPIL.save('log/call_err_debug_fullscreen.png')
            except:
                pass

            self.currentCallValue=9999999.0

        if self.currentBetValue < self.currentCallValue:
            self.currentCallValue = self.currentBetValue / 2
            self.BetValueReadError = True
            self.entireScreenPIL.save("pics/BetValueError.png")

        self.logger.info("Final call value: " + str(self.currentCallValue))
        self.logger.info("Final bet value: " + str(self.currentBetValue))
        return True

    def get_lost_everything(self,h,t,p):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = self.find_template_on_screen(self.lostEverything, img, 0.001)
        if count > 0:
            h.lastGameID = str(h.GameID)
            self.myFundsChange = float(0) - float(str(h.myFundsHistory[-1]).strip('[]'))
            L.mark_last_game(t, h, p)
            self.gui_signals.signal_status.emit("Everything is lost. Last game has been marked.")
            self.gui_signals.signal_progressbar_reset.emit()
            #user_input = input("Press Enter for exit ")
            sys.exit()
        else:
            return True

    def get_new_hand(self, mouse, h, p):
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.get_game_number_on_screen()
        if h.previousCards != self.mycards:
            self.time_new_cards_recognised=datetime.datetime.utcnow()
            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            cards = ' '.join(self.mycards)
            self.gui_signals.signal_status.emit("New hand: " + str(cards))
            L.mark_last_game(self, h, p)

            t_algo = threading.Thread(name='Algo', target=self.call_genetic_algorithm)
            t_algo.daemon = True
            t_algo.start()

            self.gui_signals.signal_funds_chart_update.emit(L)
            self.gui_signals.signal_bar_chart_update.emit(L,p.current_strategy)

            h.myLastBet = 0
            h.myFundsHistory.append(str(self.myFunds))
            h.previousCards = self.mycards
            h.lastSecondRoundAdjustment = 0
            h.last_round_bluff = False  # reset the bluffing marker
            h.round_number = 0

            mouse.move_mouse_away_from_buttons(logger)

            self.take_screenshot(False,p)
        return True

    def upload_collusion_wrapper(self,p,h):
        if not (h.GameID,self.gameStage) in h.uploader:
            h.uploader[(h.GameID,self.gameStage)]=True
            L.upload_collusion_data(self.game_number_on_screen, self.mycards, p, self.gameStage)
            logging.debug("Updated db cards")
        return True

    def get_game_number_on_screen(self):
        func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1'], self.tlc[1] + func_dict['y1'],
                                    self.tlc[0] + func_dict['x2'], self.tlc[1] + func_dict['y2'])
        basewidth = 200
        wpercent = (basewidth / float(pil_image.size[0]))
        hsize = int((float(pil_image.size[1]) * float(wpercent)))
        img_resized = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)

        img_min = img_resized.filter(ImageFilter.MinFilter)
        #img_med = img_resized.filter(ImageFilter.MedianFilter)
        img_mod = img_resized.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)

        try:
            self.game_number_on_screen=pytesseract.image_to_string(img_mod, None, False, "-psm 6")
            self.logger.info("Game number on screen: "+str(self.game_number_on_screen))
        except:
            self.logger.info("Failed to get game number from screen")

        return True

class ThreadManager(threading.Thread):
    def __init__(self, threadID, name, counter):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.counter = counter

    def update_most_gui_items(self,t,d,h,gui_signals):
        gui_signals.signal_decision.emit(str(d.decision+" "+d.preflop_sheet_name))
        gui_signals.signal_status.emit(d.decision)

        gui_signals.signal_lcd_number_update.emit('equity', np.round(t.equity * 100, 2))
        gui_signals.signal_lcd_number_update.emit('required_minbet', t.currentBetValue)
        gui_signals.signal_lcd_number_update.emit('required_mincall', t.minCall)
        #gui_signals.signal_lcd_number_update.emit('potsize', t.totalPotValue)
        gui_signals.signal_lcd_number_update.emit('gamenumber', int(L.get_game_count(p.current_strategy)))
        gui_signals.signal_lcd_number_update.emit('assumed_players', int(t.assumedPlayers))
        gui_signals.signal_lcd_number_update.emit('calllimit', d.finalCallLimit)
        gui_signals.signal_lcd_number_update.emit('betlimit', d.finalBetLimit)
        #gui_signals.signa.l_lcd_number_update.emit('zero_ev', round(d.maxCallEV, 2))

        gui_signals.signal_pie_chart_update.emit(t.winnerCardTypeList)
        gui_signals.signal_curve_chart_update1.emit(h.histEquity, h.histMinCall, h.histMinBet, t.equity,
                                                              t.minCall, t.minBet,
                                                              'bo',
                                                              'ro')

        gui_signals.signal_curve_chart_update2.emit(t.power1, t.power2, t.minEquityCall, t.minEquityBet,
                                                              t.smallBlind, t.bigBlind,
                                                              t.maxValue,
                                                              t.maxEquityCall, t.max_X, t.maxEquityBet)

    def run(self):
            h = History()
            h.preflop_sheet=pd.read_excel(preflop_url, sheetname=None)

            while True:
                if p.pause:
                    while p.pause == True:
                        time.sleep(1)
                        if p.exit_thread == True: sys.exit()

                p.read_strategy()
                if p.selected_strategy['pokerSite'][0:2] == "PS":
                    t = TableScreenBased(gui_signals,logger)
                    mouse = MouseMoverTableBased(logger,p.selected_strategy['pokerSite'])
                elif p.selected_strategy['pokerSite'] == "PP":
                    t = TableScreenBased(gui_signals,logger)
                    mouse = MouseMoverTableBased(logger,p.selected_strategy['pokerSite'])
                elif p.selected_strategy['pokerSite'] == "F1":
                    # t = TableF1()
                    logger.critical("Pokerbot tournament not yet supported")
                    exit()

                ready = False
                while (not ready):
                    ready = t.take_screenshot(True,p) and \
                            t.get_top_left_corner(p) and \
                            t.check_for_captcha(mouse) and \
                            t.get_lost_everything(h,t,p) and \
                            t.check_for_imback(mouse) and \
                            t.get_my_funds(h) and \
                            t.get_my_cards(h) and \
                            t.get_new_hand(mouse,h,p) and \
                            t.get_table_cards(h) and \
                            t.upload_collusion_wrapper(p,h) and \
                            t.check_for_button() and \
                            t.get_dealer_position() and \
                            t.init_get_other_players_info() and \
                            t.get_other_player_names(p) and \
                            t.get_other_player_funds(p) and \
                            t.get_other_player_pots() and \
                            t.get_other_player_status(p,h) and \
                            t.get_total_pot_value(h) and \
                            t.check_for_checkbutton() and \
                            t.check_for_call() and \
                            t.check_for_betbutton() and \
                            t.check_for_allincall() and \
                            t.get_current_call_value(p) and \
                            t.get_current_bet_value(p)

                if not p.pause:
                    config = ConfigObj("config.ini")
                    run_montecarlo_wrapper(logger,p,gui_signals,config,ui,t,L)
                    d = Decision(t, h, p, logger, L)
                    d.make_decision(t, h, p, logger, L)
                    if p.exit_thread: sys.exit()

                    self.update_most_gui_items(t,d,h,gui_signals)

                    logger.info(
                        "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                            int(t.other_active_players)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
                    logger.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))
                    logger.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.currentBetValue))
                    logger.info("Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                    logger.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

                    mouse = MouseMoverTableBased(logger,p.selected_strategy['pokerSite'], p.selected_strategy['BetPlusInc'], t.currentBluff)
                    mouse_target=d.decision
                    if mouse_target=='Call' and t.allInCallButton:
                        mouse_target='Call2'
                    mouse.mouse_action(mouse_target, t.tlc, logger)

                    t.time_action_completed = datetime.datetime.utcnow()


                    filename=str(h.GameID)+"_"+str(t.gameStage)+"_"+str(h.round_number)+".png"
                    logger.debug("Saving screenshot: "+filename)
                    pil_image = t.crop_image(t.entireScreenPIL, t.tlc[0],t.tlc[1],t.tlc[0] + 950, t.tlc[1] + 650)
                    pil_image.save("log/screenshots/"+filename)

                    gui_signals.signal_status.emit("Logging data")

                    t_log_db = threading.Thread(name='t_log_db', target=L.write_log_file,args=[p, h, t, d])
                    t_log_db.daemon = True
                    t_log_db.start()
                    #L.write_log_file(p, h, t, d)

                    h.previousPot = t.totalPotValue
                    h.histGameStage = t.gameStage
                    h.histDecision = d.decision
                    h.histEquity = t.equity
                    h.histMinCall = t.minCall
                    h.histMinBet = t.minBet
                    h.hist_other_players=t.other_players
                    h.first_raiser=t.first_raiser
                    h.first_caller=t.first_caller
                    h.previous_decision=d.decision
                    h.lastRoundGameID = h.GameID
                    h.last_round_bluff = False if t.currentBluff==0 else True
                    logger.info("======================= THE END=======================")

# ==== MAIN PROGRAM =====
if __name__ == '__main__':
    print ("This is a testversion and error messages will appear here. The user interface has opened in a separate window.")
    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook
    u=UpdateChecker()
    u.check_update(version)
    preflop_url=u.get_preflop_sheet_url()

    def my_exception_hook(exctype, value, traceback):
        # Print the error and traceback
        print(exctype, value, traceback)
        logger.error(str(exctype))
        logger.error(str(value))
        logger.error(str(traceback))
        # Call the normal Exception hook after
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    # Set the exception hook to our wrapping function
    sys.excepthook = my_exception_hook

    # check for tesseract
    try:
        pytesseract.image_to_string(Image.open('pics/PP/3h.png'))
    except Exception as e:
        print (e)
        print ("Tesseract not installed. Please install it into the same folder as the pokerbot or alternatively set the path variable.")
        #subprocess.call(["start", 'tesseract-installer/tesseract-ocr-setup-3.05.00dev.exe'], shell=True)
        sys.exit()

    logger = debug_logger().start_logger('main')

    p = StrategyHandler()
    p.read_strategy()

    L = GameLogger()
    L.clean_database()

    p.exit_thread=False
    p.pause=True
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()

    ui = Ui_Pokerbot()
    ui.setupUi(MainWindow)
    MainWindow.setWindowIcon(QtGui.QIcon('icon.ico'))

    gui_signals = UIActionAndSignals(ui, p, L, logger) # global variable

    t1 = ThreadManager(1, "Thread-1", 1)
    t1.start()

    MainWindow.show()
    try:
        sys.exit(app.exec_())
    except:
        print("Preparing to exit...")
        p.exit_thread = True

