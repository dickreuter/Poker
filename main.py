import matplotlib

matplotlib.use('Qt4Agg')
import operator
import os.path
import winsound
import cv2  # opencv 3.0
import pytesseract
from PIL import Image, ImageGrab, ImageDraw, ImageFilter
from decisionmaker.decisionmaker1 import *
from decisionmaker.montecarlo_v3 import *
from mouse_mover import *
from configobj import ConfigObj
from gui.gui_qt_logic import *


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


class Tools(object):
    # General tools that are used to operate the pokerbot, such as moving the
    # mouse, clicking and routines that
    # call Opencv for image recognition
    def __init__(self):
        self.load_templates()

    def load_templates(self):

        self.cardImages = dict()
        self.img = dict()
        values = "23456789TJQKA"
        suites = "CDHS"
        for x in values:
            for y in suites:
                name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/" + x + y + ".png"
                if os.path.exists(name) == True:
                    self.img[x + y] = Image.open(name)
                    self.cardImages[x + y] = cv2.cvtColor(np.array(self.img[x + y]), cv2.COLOR_BGR2RGB)
                    # (thresh, self.cardImages[x + y]) =
                    # cv2.threshold(self.cardImages[x + y], 128, 255,
                    # cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                else:
                    logger.critical("Card Temlate File not found: " + str(x) + str(y) + ".png")

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/button.png"
        template = Image.open(name)
        self.button = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/topleft.png"
        template = Image.open(name)
        self.topLeftCorner = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/coveredcard.png"
        template = Image.open(name)
        self.coveredCardHolder = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/imback.png"
        template = Image.open(name)
        self.ImBack = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/check.png"
        template = Image.open(name)
        self.check = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/call.png"
        template = Image.open(name)
        self.call = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/smalldollarsign1.png"
        template = Image.open(name)
        self.smallDollarSign1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        if p.XML_entries_list1['pokerSite'].text == "PP":
            name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/smalldollarsign2.png"
            template = Image.open(name)
            self.smallDollarSign2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/allincallbutton.png"
        template = Image.open(name)
        self.allInCallButton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + p.XML_entries_list1['pokerSite'].text + "/lostEverything.png"
        template = Image.open(name)
        self.lostEverything = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

    def take_screenshot(self):
        if terminalmode == False:
            ui.status.setText("")
            #ui.progress_bar.setValue(0)
        time.sleep(0.1)
        self.entireScreenPIL = ImageGrab.grab()
        if terminalmode == False:
            ui.status.setText(str(p.current_strategy.text))
            #ui.progress_bar.setValue(10)
        if terminalmode == False and p.ExitThreads == True: sys.exit()
        if terminalmode == False and t1.pause == True:
            while t1.pause == True:
                time.sleep(1)
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

    def setup_get_item_location(self):
        topleftcorner = "pics/PP/topleft.png"
        name = "pics/screenshot11.png"
        findTemplate = "pics/half.png"

        setup = cv2.cvtColor(np.array(Image.open(name)), cv2.COLOR_BGR2RGB)
        tlc = cv2.cvtColor(np.array(Image.open(topleftcorner)), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(setup, tlc, 0.01)
        rel = tuple(-1 * np.array(bestfit))

        template = cv2.cvtColor(np.array(Image.open(findTemplate)), cv2.COLOR_BGR2RGB)

        count, points, bestfit = a.find_template_on_screen(setup, template, 0.01)
        print("Count: " + str(count) + " Points: " + str(points) + " Bestfit: " + str(bestfit))

        print(findTemplate + " Relative: ")
        print(str(tuple(map(sum, zip(points[0], rel)))))

    def get_ocr_float(self, img_orig, name):
        def fix_number(t):
            t = t.replace("I", "1").replace("O", "0").replace("o", "0").replace("-", ".").replace("D", "0").replace("I",
                                                                                                                    "1")
            t = re.sub("[^0123456789.]", "", t)
            try:
                if t[0] == ".": t = t[1:]
            except:
                pass
            return t

        img_orig.save('pics/ocr_debug_' + name + '.png')
        basewidth = 200
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
        #    logger.error(str(e))
        try:
            lst.append(pytesseract.image_to_string(img_min, None, False, "-psm 6"))
        except Exception as e:
            logger.error(str(e))
        # try:
        #    lst.append(pytesseract.image_to_string(img_med, None, False, "-psm 6"))
        # except Exception as e:
        #    logger.error(str(e))
        try:
            lst.append(pytesseract.image_to_string(img_mod, None, False, "-psm 6"))
        except Exception as e:
            logger.error(str(e))

        try:
            final_value = ''
            for i, j in enumerate(lst):
                logger.debug("OCR of " + name + " method " + str(i) + " :" + str(j))
                lst[i] = fix_number(lst[i]) if lst[i] != '' else lst[i]
                final_value = lst[i] if final_value == '' else final_value

            logger.info(name + " FINAL VALUE: " + str(final_value))
            return float(final_value)

        except Exception as e:
            logger.error("Pytesseract Error in recognising " + name)
            logger.error(str(e))
            return ''


class Table(object):
    # baseclass that is inherited by the different types of Tables (e.g.
    # Pokerstars of Party Poker Table)
    def call_genetic_algorithm(self):
        ui.status.setText("Checking for AI update")
        n = L.get_game_count(p.current_strategy.text)
        lg = int(
            p.XML_entries_list1['considerLastGames'].text)  # only consider lg last games to see if there was a loss
        f = L.get_strategy_total_funds_change(p.current_strategy.text, lg)
        if terminalmode == False:
            ui.gamenumber.display(str(n))
            ui.winnings.display(str(f))
        logger.info("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))
        if n % int(p.XML_entries_list1['strategyIterationGames'].text) == 0 and f < float(
                p.XML_entries_list1['minimumLossForIteration'].text):
            ui.status.setText("***Improving current strategy***")
            logger.info("***Improving current strategy***")
            winsound.Beep(500, 100)
            Genetic_Algorithm(True, logger)
            p.read_XML()
        else:
            logger.debug("Criteria not met for running genetic algorithm. Recommendation would be as follows:")
            Genetic_Algorithm(False, logger)

    def crop_image(self, original, left, top, right, bottom):
        # original.show()
        width, height = original.size  # Get dimensions
        cropped_example = original.crop((left, top, right, bottom))
        # cropped_example.show()
        return cropped_example


class TablePP(Table):
    def get_top_left_corner(self, scraped):
        img = cv2.cvtColor(np.array(a.entireScreenPIL), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.topLeftCorner, img, 0.01)
        if count == 1:
            self.topleftcorner = points[0]
            logger.debug("Top left corner found")
            t.timeout_start = time.time()
            return True
        else:

            if terminalmode == False:
                ui.status.setText(p.XML_entries_list1['pokerSite'].text + " not found yet")
                #ui.progress_bar.setValue(0)
            logger.debug("Top left corner NOT found")
            time.sleep(1)
            return False

    def check_for_button(self, scraped):
        cards = ' '.join(t.mycards)
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 540, self.topleftcorner[1] + 480,
                                    self.topleftcorner[0] + 700, self.topleftcorner[1] + 580)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.button, img, 0.01)

        if count > 0:
            if terminalmode == False:
                ui.status.setText("Buttons found, preparing Montecarlo with: " + str(cards))
            logger.info("Buttons Found, preparing for montecarlo")
            return True

        else:
            logger.debug("No buttons found")
            return False

    def check_for_checkbutton(self, scraped):
        if terminalmode == False:
            ui.status.setText("Check for Check")
        logger.debug("Checking for check button")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 560, self.topleftcorner[1] + 478,
                                    self.topleftcorner[0] + 670, self.topleftcorner[1] + 550)
        # pil_image.save("pics/getCheckButton.png")
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.check, img, 0.01)

        if count > 0:
            self.checkButton = True
            self.currentCallValue = 0.0
            logger.debug("check button found")
        else:
            self.checkButton = False
            logger.debug("no check button found")
        logger.debug("Check: " + str(self.checkButton))
        return True

    def check_for_captcha(self):
        # ChatWindow = self.crop_image(a.entireScreenPIL, self.topleftcorner[0]
        # + 3, self.topleftcorner[1] + 443,
        #                             self.topleftcorner[0] + 400,
        #                             self.topleftcorner[1] + 443 + 90)
        # basewidth = 500
        # wpercent = (basewidth / float(ChatWindow.size[0]))
        # hsize = int((float(ChatWindow.size[1]) * float(wpercent)))
        # ChatWindow = ChatWindow.resize((basewidth, hsize), Image.ANTIALIAS)
        # # ChatWindow.show()
        # try:
        #     t.chatText = (pytesseract.image_to_string(ChatWindow, None,
        #     False, "-psm 6"))
        #     t.chatText =
        #     re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\.]",
        #     "", t.chatText)
        #     keyword1 = 'disp'
        #     keyword2 = 'left'
        #     keyword3 = 'pic'
        #     keyword4 = 'key'
        #     keyword5 = 'lete'
        #     logger.debug( (recognizedText)
        #     if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2)
        #     > 0) or (
        #                 t.chatText.find(keyword3) > 0) or
        #                 (t.chatText.find(keyword4) > 0) or (
        #                 t.chatText.find(keyword5) > 0)):
        #         gui.statusbar.set("Captcha discovered!  Submitting...")
        #         captchaIMG = self.crop_image(a.entireScreenPIL,
        #         self.topleftcorner[0] + 5, self.topleftcorner[1] + 490,
        #                                     self.topleftcorner[0] + 335,
        #                                     self.topleftcorner[1] + 550)
        #         captchaIMG.save("pics/captcha.png")
        #         # captchaIMG.show()
        #         time.sleep(0.5)
        #         t.captcha = solve_captcha("pics/captcha.png")
        #         mouse.enter_captcha(t.captcha)
        #         logger.info("Entered captcha")
        #         logger.info(t.captcha)
        # except:
        #     logger.info("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, scraped):
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 402, self.topleftcorner[1] + 458,
                                    self.topleftcorner[0] + 442 + 400, self.topleftcorner[1] + 550)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.ImBack, img, 0.08)
        if count > 0:
            mouse.mouse_action("Imback", t.topleftcorner, 0, 0, logger)
            return False
            if terminalmode == False:
                ui.status.setText("I am back found")
        else:
            return True

    def check_for_call(self, scraped):
        logger.debug("Check for Call")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 575, self.topleftcorner[1] + 483,
                                    self.topleftcorner[0] + 575 + 100, self.topleftcorner[1] + 483 + 100)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.call, img, 0.05)
        if count > 0:
            self.callButton = True
            logger.debug("Call button found")
        else:
            self.callButton = False
            logger.info("Call button NOT found")
            pil_image.save("pics/debug_nocall.png")
        return True

    def check_for_allincall_button(self, scraped):
        logger.debug("Check for All in call button")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 557, self.topleftcorner[1] + 483,
                                    self.topleftcorner[0] + 670, self.topleftcorner[1] + 580)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.allInCallButton, img, 0.01)
        if count > 0:
            self.allInCallButton = True
            logger.debug("All in call button found")
        else:
            self.allInCallButton = False
            logger.debug("All in call button not found")

        return True

    def get_table_cards(self, scraped):
        logger.debug("Get Table cards")
        self.cardsOnTable = []
        pil_image = self.crop_image(a.entireScreenPIL, t.topleftcorner[0] + 206, t.topleftcorner[1] + 158,
                                    t.topleftcorner[0] + 600, t.topleftcorner[1] + 158 + 120)

        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        # (thresh, img) = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY |
        # cv2.THRESH_OTSU)

        for key, value in scraped.cardImages.items():
            template = value

            method = eval('cv2.TM_SQDIFF_NORMED')

            # Apply template Matching
            res = cv2.matchTemplate(img, template, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
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
            logger.critical("Table cards not recognised correctly")
            exit()

        logger.info("Gamestage: " + self.gameStage)
        logger.info("Cards on table: " + str(self.cardsOnTable))

        return True

    def get_my_cards(self, scraped):
        def go_through_each_card(img, debugging):
            dic = {}
            for key, value in scraped.cardImages.items():
                template = value
                method = eval('cv2.TM_SQDIFF_NORMED')

                # Apply template Matching
                # kernel = np.ones((5, 5), np.float32) / 25
                # img = cv2.filter2D(img, -1, kernel)
                # template = cv2.filter2D(template, -1, kernel)

                res = cv2.matchTemplate(img, template, method)

                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
                if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                    top_left = min_loc
                else:
                    top_left = max_loc
                if min_val < 0.01:
                    self.mycards.append(key)
                if debugging:
                    dic[key] = min_val

            if debugging:
                dic = sorted(dic.items(), key=operator.itemgetter(1))
                logger.error("Analysing cards: " + str(dic))

        self.mycards = []
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 450, self.topleftcorner[1] + 330,
                                    self.topleftcorner[0] + 450 + 80, self.topleftcorner[1] + 330 + 80)

        # pil_image.show()
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        # (thresh, img) = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY |
        # cv2.THRESH_OTSU)
        go_through_each_card(img, False)

        if len(self.mycards) == 2:
            t.myFundsChange = float(t.myFunds) - float(str(h.myFundsHistory[-1]).strip('[]'))
            logger.info("My cards: " + str(self.mycards))
            return True
        else:
            logger.warning("Did not find two player cards: " + str(self.mycards))
            # go_through_each_card(img,True)
            return False

    def get_covered_card_holders(self, scraped):
        if terminalmode == False: ui.status.setText("Analyse other players and position")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)
        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.coveredCardHolder, img, 0.0001)
        t.PlayerNames = []
        t.PlayerFunds = []

        t.PlayerNames.append("Myself")
        count = 0
        for pt in points:
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            playerNameImage = pil_image.crop((pt[0] - (955 - 890), pt[1] + 270 - 222, pt[0] + 20, pt[1] + +280 - 222))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerNameImage = playerNameImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerNameImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerNameImage, None, False, "-psm 6"))
                recognizedText = re.sub("[^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789]", "",
                                        recognizedText)
                t.PlayerNames.append(recognizedText)
            except:
                logger.debug("Pyteseract error in player name recognition")

            playerFundsImage = pil_image.crop(
                (pt[0] - (955 - 890) + 10, pt[1] + 270 - 222 + 20, pt[0] + 10, pt[1] + +280 - 222 + 22))
            basewidth = 500
            wpercent = (basewidth / float(playerNameImage.size[0]))
            hsize = int((float(playerNameImage.size[1]) * float(wpercent)))
            playerFundsImage = playerFundsImage.resize((basewidth, hsize), Image.ANTIALIAS)
            # playerFundsImage = playerFundsImage.filter(ImageFilter.MaxFilter)
            # playerFundsImage.show()
            try:
                recognizedText = (pytesseract.image_to_string(playerFundsImage, None, False, "-psm 6")).replace("-",
                                                                                                                ".")
                recognizedText = re.sub("[^0123456789.]", "",
                                        recognizedText)
                t.PlayerFunds.append(float(recognizedText))
            except:
                logger.debug("Pyteseract error in player name recognition")

        logger.debug("Player Names: " + str(t.PlayerNames))
        logger.debug("Player Funds: " + str(t.PlayerFunds))

        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        self.coveredCardHolders = np.round(count)

        logger.info("Covered cardholders:" + str(self.coveredCardHolders))

        if self.coveredCardHolders == 1:
            self.isHeadsUp = True
            logger.debug("HeadSUP detected!")
        else:
            self.isHeadsUp = False

        if self.coveredCardHolders > 0:
            return True
        else:
            logger.info("No other players found. Assuming 1 player")
            self.coveredCardHolders = 1
            return True

    def get_played_players(self, scraped):
        if terminalmode == False: ui.status.setText("Analyse past players")
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + 0, self.topleftcorner[1] + 0,
                                    self.topleftcorner[0] + 800, self.topleftcorner[1] + 500)

        im = pil_image
        x, y = im.size
        eX, eY = 280, 150  # Size of Bounding Box for ellipse

        bbox = (x / 2 - eX / 2, y / 2 - eY / 2, x / 2 + eX / 2, y / 2 + eY / 2 - 20)
        rectangle1 = (0, 0, 800, 130)
        rectangle2 = (0, 380, 800, 499)
        rectangle3 = (0, 1, 110, 499)
        rectangle4 = (690, 1, 800, 499)
        rectangle5 = (400, 300, 500, 400)
        draw = ImageDraw.Draw(im)
        draw.ellipse(bbox, fill=128)
        draw.rectangle(rectangle1, fill=128)
        draw.rectangle(rectangle2, fill=128)
        draw.rectangle(rectangle3, fill=128)
        draw.rectangle(rectangle4, fill=128)
        draw.rectangle(rectangle5, fill=128)
        del draw
        # im.show()
        pil_image_ellipsed = im

        # Convert RGB to BGR
        img = cv2.cvtColor(np.array(pil_image_ellipsed), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.smallDollarSign1, img, 0.05)

        self.PlayerPots = []
        for pt in points:
            x = pt[0] + 9
            y = pt[1] + 1
            modpt = (x, y)
            w = 40
            h = 15
            cv2.rectangle(img, modpt, (x + w, y + h), (0, 0, 255), 2)
            # cv2.imshow("Image",img)
            playerPotImage = pil_image_ellipsed.crop((x, y, x + w, y + h))

            basewidth = 100
            wpercent = (basewidth / float(playerPotImage.size[0]))
            hsize = int((float(playerPotImage.size[1]) * float(wpercent)))
            playerPotImage = playerPotImage.resize((basewidth, hsize), Image.ANTIALIAS)

            playerPotImage = playerPotImage.filter(ImageFilter.MinFilter)
            try:
                recognizedText = pytesseract.image_to_string(playerPotImage, None, False, "-psm 6")
                recognizedText = re.sub("[^0123456789.]", "", recognizedText)
                if recognizedText != "":
                    self.PlayerPots.append(recognizedText)
            except:
                logger.debug("Error in Pytesseract")

        self.PlayerPots.sort()

        try:
            t = [float(x) for x in self.PlayerPots]
            self.playerBetIncreases = [t[i + 1] - t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncrease = max(self.playerBetIncreases)

            self.playerBetIncreasesAsPotPercentage = [(x / self.totalPotValue) for x in self.playerBetIncreases]
            self.maxPlayerBetIncreasesAsPotPercentage = max(self.playerBetIncreasesAsPotPercentage)
        except:  # when no other players are around (avoid division by zero)
            self.maxPlayerBetIncrease = 0
            self.playerBetIncreasesAsPotPercentage = [0]
            self.maxPlayerBetIncreasesAsPotPercentage = 0

        try:
            self.playerBetIncreasesPercentage = [t[i + 1] / t[i] for i in range(len(t) - 1)]
            self.maxPlayerBetIncreasesPercentage = max(self.playerBetIncreasesPercentage)

            logger.debug("Player Pots:           " + str(self.PlayerPots))
            logger.debug("Player Pots increases: " + str(self.playerBetIncreases))
            logger.debug("Player increase as %:  " + str(self.playerBetIncreasesPercentage))

        except:
            self.playerBetIncreasesPercentage = [0]
            self.maxPlayerBetIncreasesPercentage = 0

        if self.isHeadsUp:
            try:
                self.maxPlayerBetIncreasesPercentage = (self.totalPotValue - h.previousPot - h.myLastBet) / h.myLastBet
                self.maxPlayerBetIncrease = (self.totalPotValue - h.previousPot - h.myLastBet) - h.myLastBet
                logger.info("Remembering last bet: " + str(self.myLastBet))
            except:
                logger.debug("Not remembering last bet")
                self.maxPlayerBetIncreasesPercentage = 0
                self.maxPlayerBetIncrease = 0

        # raw_input("Press Enter to continue...")
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()


        self.playersBehind = count

        self.playersAhead = int(np.round(self.coveredCardHolders - self.playersBehind))
        logger.debug("Player pots: " + str(self.PlayerPots))

        if p.XML_entries_list1['smallBlind'].text in self.PlayerPots:
            self.playersAhead += 1
            self.playersBehind -= 1
            logger.debug("Found small blind")

        self.playersAhead = int(max(self.playersAhead, 0))
        logger.debug(("Played players: " + str(self.playersBehind)))

        return True

    def get_total_pot_value(self):
        if terminalmode == False: ui.status.setText("Get Pot Value")
        logger.debug("Get TotalPot value")
        returnvalue = True
        x1 = 385
        y1 = 120
        x2 = 430
        y2 = 131
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        self.totalPotValue = a.get_ocr_float(pil_image, 'TotalPotValue')

        if self.totalPotValue < 0.01:
            logger.info("unable to get pot value")
            if terminalmode == False: ui.status.setText("Unable to get pot value")
            time.sleep(1)
            pil_image.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        logger.info("Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_my_funds(self):
        logger.debug("Get my funds")
        x1 = 469
        y1 = 403
        x2 = 469 + 38
        y2 = 403 + 11
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

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
            logger.info("Could not save myFunds.png")

        self.myFunds = a.get_ocr_float(pil_image, 'MyFunds')

        if self.myFunds == '':
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            logger.info("myFunds not regognised!")
            if terminalmode == False: ui.status.setText("!!Funds NOT recognised!!")
            logger.warning("!!Funds NOT recognised!!")
            a.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)
        logger.info("Funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self):
        if terminalmode == False: ui.status.setText("Get Call value")
        x1 = 585
        y1 = 516
        x2 = 585 + 70
        y2 = 516 + 17

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        if t.checkButton == False:

            try:
                self.currentCallValue = a.get_ocr_float(pil_image, 'CallValue')
                self.getCallButtonValueSuccess = True
                if self.allInCallButton == True and self.myFundsError == False and self.currentCallValue < self.myFunds:
                    self.getCallButtonValueSuccess = False
                    pil_image.save("pics/ErrCallValue.png")
                    self.currentCallValue = self.myFunds
            except:
                self.currentCallValue = 0
                self.CallValueReadError = True
                pil_image.save("pics/ErrCallValue.png")

        # if len(self.currentRoundPotValue)>0: return True
        # else: return False

        return True

    def get_current_bet_value(self):
        if terminalmode == False: ui.status.setText("Get Bet Value")
        logger.debug("Get bet value")
        x1 = 589 + 125
        y1 = 516
        x2 = 589 + 70 + 125
        y2 = 516 + 17

        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)

        self.currentBetValue = a.get_ocr_float(pil_image, 'BetValue')
        if self.currentBetValue == '':
            returnvalue = False
            self.currentBetValue = 9999999.0

        if self.currentBetValue < self.currentCallValue:
            self.currentCallValue = self.currentBetValue / 2
            self.BetValueReadError = True
            a.entireScreenPIL.save("pics/BetValueError.png")

        logger.info("Final call value: " + str(self.currentCallValue))
        logger.info("Final bet value: " + str(self.currentBetValue))
        return True

    def get_current_pot_value(self):
        x1 = 390
        y1 = 324
        x2 = 431
        y2 = 340
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        # pil_image.show()
        pil_image.save("pics/currenPotValue.png")
        # blurred = pil_image.filter(ImageFilter.SHARPEN)
        try:
            self.currentRoundPotValue = pytesseract.image_to_string(pil_image, None, False, "-psm 6").replace(" ",
                                                                                                              "").replace(
                "$", "")
        except:
            logger.warning("Error in pytesseract current pot value")

        if len(self.currentRoundPotValue) > 6: self.currentRoundPotValue = ""
        # else: return False

        return True

    def get_lost_everything(self, scraped):
        x1 = 100
        y1 = 100
        x2 = 590 + 50 + 125
        y2 = 511 + 14
        pil_image = self.crop_image(a.entireScreenPIL, self.topleftcorner[0] + x1, self.topleftcorner[1] + y1,
                                    self.topleftcorner[0] + x2, self.topleftcorner[1] + y2)
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_BGR2RGB)
        count, points, bestfit = a.find_template_on_screen(scraped.lostEverything, img, 0.001)

        if count > 0:
            if not terminalmode:
                #ui.progress_bar.setValue(15)
                pass
            h.lastGameID = str(h.GameID)
            t.myFundsChange = float(0) - float(str(h.myFundsHistory[-1]).strip('[]'))
            L.mark_last_game(t, h)
            if terminalmode == False: ui.status.setText("Everything is lost. Last game has been marked.")
            user_input = input("Press Enter for exit ")
            sys.exit()
        else:
            return True

    def get_new_hand(self):
        if h.previousCards != t.mycards:
            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            cards = ' '.join(t.mycards)
            ui.status.setText("New hand: " + str(cards))
            L.mark_last_game(t, h)

            self.call_genetic_algorithm()

            if terminalmode == False:
                gui_funds.drawfigure()
                gui_bar.drawfigure()

            h.myLastBet = 0
            h.myFundsHistory.append(str(t.myFunds))
            h.previousCards = t.mycards
            h.lastSecondRoundAdjustment = 0

            a.take_screenshot()

        return True

    def run_montecarlo_wrapper(self):
        # self.montecarlo_thread = Process(target=self.run_montecarlo, args=())
        # self.montecarlo_thread.start()
        self.run_montecarlo()
        return True

    def run_montecarlo(self):
        # Prepare for montecarlo simulation to evaluate equity (probability of winning with given cards)

        if t.gameStage == "PreFlop":
            # t.assumedPlayers = t.coveredCardHolders - int(
            #    round(t.playersAhead * (1 - float(p.XML_entries_list1['CoveredPlayersCallLikelihoodPreFlop'].text)))) + 1
            t.assumedPlayers = 2

        elif t.gameStage == "Flop":
            t.assumedPlayers = t.coveredCardHolders - int(
                round(t.playersAhead * (1 - float(p.XML_entries_list1['CoveredPlayersCallLikelihoodFlop'].text)))) + 1

        else:
            t.assumedPlayers = t.coveredCardHolders + 1

        t.assumedPlayers = min(max(t.assumedPlayers, 2), 3)

        t.PlayerCardList = []
        t.PlayerCardList.append(t.mycards)

        # add cards from colluding players (not yet implemented)
        col = Collusion()

        if t.gameStage == "PreFlop":
            maxRuns = 20000
        else:
            maxRuns = 10000

        if terminalmode == False: ui.status.setText("Running Monte Carlo: " + str(maxRuns))
        logger.debug("Running Monte Carlo")
        self.montecarlo_timeout = float(config['montecarlo_timeout'])
        timeout = t.timeout_start + self.montecarlo_timeout
        m = MonteCarlo()
        m.run_montecarlo(t.PlayerCardList, t.cardsOnTable, int(t.assumedPlayers), ui, maxRuns=maxRuns, timeout=timeout)
        if terminalmode == False: ui.status.setText("Monte Carlo completed successfully")
        logger.debug("Monte Carlo completed successfully with runs: " + str(m.runs))

        self.equity = np.round(m.equity, 3)
        self.winnerCardTypeList = m.winnerCardTypeList


# ==== MAIN PROGRAM =====
if __name__ == '__main__':
    def run_pokerbot(logger):
        global LogFilename, h, L, p, mouse, t, a, d

        LogFilename = 'log'
        h = History()
        L = Logging(LogFilename)
        a = Tools()

        if p.XML_entries_list1['pokerSite'].text == "PS":
            logger.critical("Pokerstars no longer supported")
            exit()
        elif p.XML_entries_list1['pokerSite'].text == "PP":
            mouse = MouseMoverPP()
        else:
            raise ("Invalid PokerSite")
        counter = 0

        while True:
            p.read_XML()
            if p.XML_entries_list1['pokerSite'].text == "PS":
                logger.critical("Pokerstars no longer supported")
                exit()
            elif p.XML_entries_list1['pokerSite'].text == "PP":
                t = TablePP()
            elif p.XML_entries_list1['pokerSite'].text == "F1":
                # t = TableF1()
                logger.critical("Pokerbot tournament not yet supported")
                exit()

            ready = False
            while (not ready):
                ready = a.take_screenshot() and \
                        t.get_top_left_corner(a) and \
                        t.check_for_captcha() and \
                        t.get_lost_everything(a) and \
                        t.check_for_imback(a) and \
                        t.get_my_funds() and \
                        t.get_my_cards(a) and \
                        t.get_new_hand() and \
                        t.check_for_button(a) and \
                        t.get_table_cards(a) and \
                        t.get_covered_card_holders(a) and \
                        t.get_total_pot_value() and \
                        t.get_played_players(a) and \
                        t.check_for_checkbutton(a) and \
                        t.check_for_call(a) and \
                        t.check_for_allincall_button(a) and \
                        t.get_current_call_value() and \
                        t.get_current_bet_value() and \
                        t.run_montecarlo_wrapper()

            d = Decision()
            d.make_decision(t, h, p, logger)
            # t.montecarlo_thread.join() # wait for montecarlo to finish

            if terminalmode == False:
                ui.last_decision.setText(d.decision)
                ui.equity.display(str(np.round(t.equity * 100, 2)))
                ui.required_minbet.display(str(t.currentBetValue))
                ui.required_mincall.display(str(t.minCall))
                ui.potsize.display(str((t.totalPotValue)))
                ui.gamenumber.display(str(L.get_game_count(p.current_strategy.text)))
                ui.assumed_players.display(str(int(t.assumedPlayers)))
                ui.calllimit.display(str(d.finalCallLimit))
                ui.betlimit.display(str(d.finalBetLimit))
                ui.zero_ev.display(str(round(d.maxCallEV, 2)))

                gui_pie.drawfigure(t.winnerCardTypeList)

                gui_curve.updatePlots(h.histEquity, h.histMinCall, h.histMinBet, t.equity, t.minCall, t.minBet, 'bo',
                                      'ro')
                gui_curve.updateLines(t.power1, t.power2, t.minEquityCall, t.minEquityBet, t.smallBlind, t.bigBlind,
                                      t.maxValue,
                                      t.maxEquityCall, t.maxEquityBet)

            logger.info(
                "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                    int(t.coveredCardHolders)) + "-" + str(int(t.playersAhead)) + "+1) Plr")

            logger.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))

            logger.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.currentBetValue))

            logger.info("Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))

            logger.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

            mouse.mouse_action(d.decision, t.topleftcorner, p.XML_entries_list1['BetPlusInc'].text, t.currentBluff,
                               logger)

            if terminalmode == False: ui.status.setText("Writing log file")

            L.write_log_file(p, h, t, d)

            h.previousPot = t.totalPotValue
            h.histGameStage = t.gameStage
            h.histDecision = d.decision
            h.histEquity = t.equity
            h.histMinCall = t.minCall
            h.histMinBet = t.minBet
            h.histPlayerPots = t.PlayerPots


    config = ConfigObj("config.ini")
    terminalmode = int(config['terminalmode'])
    setupmode = int(config['setupmode'])

    logger = debug_logger().start_logger()

    p = XMLHandler('strategies.xml')
    p.read_XML()

    if setupmode:
        a = Tools()
        a.setup_get_item_location()
        sys.exit()

    if not terminalmode:
        app = QtGui.QApplication(sys.argv)
        MainWindow = QtGui.QMainWindow()
        ui = Ui_Pokerbot()
        ui.setupUi(MainWindow)
        ui_action = UIAction()

        gui_funds = FundsPlotter(ui, p)
        gui_bar = BarPlotter(ui, p)
        gui_curve = CurvePlot(ui, p)
        gui_pie = PiePlotter(ui, p)

        p.ExitThreads = False
        t1 = threading.Thread(target=run_pokerbot, args=[logger])
        t1.setDaemon(True)

        # ui.button_options.clicked.connect()
        ui.button_log_analyser.clicked.connect(lambda: ui_action.open_strategy_analyser(p))
        # ui.button_strategy_editor.clicked.connect()
        # ui.button_options.clicked.connect()
        ui.button_pause.clicked.connect(lambda: ui_action.pause(ui, t1))
        ui.button_resume.clicked.connect(lambda: ui_action.resume(ui, t1))

        t1.pause = False
        t1.start()
        MainWindow.show()
        sys.exit(app.exec_())
        p.ExitThreads = True

    elif terminalmode:
        print("Terminal mode selected. To view GUI set terminalmode=False")
        run_pokerbot(logger)
