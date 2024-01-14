import datetime
import logging
import sys
import threading
import time
from copy import copy

import numpy as np

from poker.decisionmaker.montecarlo_python import MonteCarlo
from poker.scraper.table import Table

log = logging.getLogger(__name__)

# pylint: disable=unused-argument,f-string-without-interpolation,bare-except

class TableScreenBased(Table):

    def get_top_left_corner(self, p):

        self.current_strategy = p.current_strategy  # needed for mongo manager
        self.screenshot = self.entireScreenPIL
        self.crop_from_top_left_corner()

        if self.screenshot:
            log.debug("Top left corner found")
            self.timeout_start = datetime.datetime.utcnow()
            self.mt_tm = time.time()
            return True
        else:

            self.gui_signals.signal_status.emit("Table not found yet")
            self.gui_signals.signal_progressbar_reset.emit()
            log.debug("Top left corner NOT found")
            time.sleep(1)
            return False

    def check_for_button_if_slow_table(self, slow_table):
        """For slow tables wich animations such as GG Poker ensure buttons appear before checking for cards"""
        if slow_table:
            return self.is_my_turn()
        else:
            return True

    def check_for_button(self):
        return self.is_my_turn()

    def check_for_checkbutton(self):
        self.checkButton = self.has_check_button()
        if self.checkButton:
            log.debug("Check button found")
        else:
            log.info("Check button NOT found")
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
        #         log.debug("Recognised text: "+t.chatText)
        #
        #         if ((t.chatText.find(keyword1) > 0) or (t.chatText.find(keyword2)
        #         > 0) or (
        #                     t.chatText.find(keyword3) > 0) or
        #                     (t.chatText.find(keyword4) > 0) or (
        #                     t.chatText.find(keyword5) > 0)):
        #             log.warning("Submitting Captcha")
        #             captchaIMG = self.crop_image(self.crop_image(self.entireScreenPIL, self.tlc[0] + func_dict['x1_2'], self.tlc[1] + func_dict['y1_2'],
        #                             self.tlc[0] + func_dict['x2_2'], self.tlc[1] + func_dict['y2_2']))
        #             captchaIMG.save("pics/captcha.png")
        #             # captchaIMG.show()
        #             time.sleep(0.5)
        #             t.captcha = solve_captcha("pics/captcha.png")
        #             mouse.enter_captcha(t.captcha)
        #             log.info("Entered captcha: "+str(t.captcha))
        #     except:
        #         log.warning("CheckingForCaptcha Error")
        return True

    def check_for_imback(self, mouse):
        imback = self.im_back()

        if imback:
            self.gui_signals.signal_status.emit("I am back found")
            mouse.mouse_action("Imback", self.tlc)
            return False
        else:
            return True

    def check_for_resume_hand(self, mouse):
        try:
            resume_hand = self.resume_hand()
        except:
            return True

        if resume_hand:
            log.info("Resume hand found. Clicking resume hand button...")
            self.gui_signals.signal_status.emit("Resume hand")
            mouse.mouse_action("resume_hand", self.tlc)
            return False
        else:
            return True

    def check_for_call(self):
        self.callButton = self.has_call_button()
        self.gui_signals.signal_progressbar_increase.emit(5)

        if self.callButton:
            log.debug("Call button found")
        else:
            log.info("Call button NOT found")
        return True

    def check_for_betbutton(self):
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.bet_button_found = self.has_raise_button()

        if not self.bet_button_found:
            # check for second version of bet button
            try:
                self.bet_button_found = self.has_bet_button()
            except:
                self.bet_button_found = False

        if self.bet_button_found:
            log.debug("Bet button found")
        else:
            log.info("Bet button NOT found")
        return True

    def check_for_allincall(self):
        self.allInCallButton = self.has_all_in_call_button()
        if self.allInCallButton:
            log.debug("All in call button found")
        else:
            log.debug("All in call button not found")

        if not self.bet_button_found:
            self.allInCallButton = True
            log.debug("Assume all in call because there is no bet button")
        return True

    def get_table_cards(self, h):
        if not self.get_table_cards2():
            return False  # in case of 1 or 2 table cards are seen only

        self.cardsOnTable = self.table_cards

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
            log.critical("Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        log.info("---")
        log.info("Gamestage: " + self.gameStage)
        log.info("Cards on table: " + str(self.cardsOnTable))
        log.info("---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.95

        return True

    def check_fast_fold(self, h, p, mouse):
        # temporarily deactivated
        self.gui_signals.signal_status.emit("Check for fast fold")
        self.gui_signals.signal_progressbar_reset.emit()
        if self.gameStage == "PreFlop":
            m = MonteCarlo()
            crd1, crd2 = m.get_two_short_notation(self.mycards)
            crd1 = crd1.upper()
            crd2 = crd2.upper()
            sheet_name = str(self.position_utg_plus + 1)
            try:
                if sheet_name == '6': return True
                if int(sheet_name[0]) > 6:
                    old = sheet_name[0]
                    sheet_name = sheet_name.replace(old, '6', 1)
                        
                sheet = h.preflop_sheet[sheet_name]
                sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())
                handlist = set(sheet['Hand'].tolist())
            except KeyError:
                log.warning("Fastfold ignored: No preflop sheet found for position: " + str(sheet_name))
                return True

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
                log.info("-------- FAST FOLD -------")
                return False

        return True

    def get_my_cards(self):
        self.get_my_cards2()
        self.mycards = self.my_cards

        if len(self.mycards) == 2:
            return True
        else:
            log.debug("Did not find two player cards: " + str(self.mycards))
            return False

    def init_get_other_players_info(self):
        other_player = {
            'utg_position': '',
            'name': '',
            'status': '',
            'funds': '',
            'pot': '',
            'decision': ''
        }
        self.other_players = []
        for i in range(self.total_players - 1):
            self.gui_signals.signal_status.emit(f"Check other players {i}")
            self.gui_signals.signal_progressbar_increase.emit(1)
            op = copy(other_player)
            op['abs_position'] = i
            self.other_players.append(op)

        return True

    def get_other_player_names(self, p):
        # if p.selected_strategy['gather_player_names'] == 1:
        #     func_dict = self.coo[inspect.stack()[0][3]][self.tbl]
        #     self.gui_signals.signal_status.emit("Get player names")
        #
        #     for i, fd in enumerate(func_dict):
        #         self.gui_signals.signal_progressbar_increase.emit(2)
        #         pil_image = self.crop_image(self.entireScreenPIL, self.tlc[0] + fd[0], self.tlc[1] + fd[1],
        #                                     self.tlc[0] + fd[2], self.tlc[1] + fd[3])
        #         basewidth = 500
        #         wpercent = (basewidth / float(pil_image.size[0]))
        #         hsize = int((float(pil_image.size[1]) * float(wpercent)))
        #         pil_image = pil_image.resize((basewidth, hsize), Image.ANTIALIAS)
        #         try:
        #             recognizedText = (pytesseract.image_to_string(pil_image, None, False, "-psm 6"))
        #             recognizedText = re.sub(r'[\W+]', '', recognizedText)
        #             log.debug("Player name: " + recognizedText)
        #             self.other_players[i]['name'] = recognizedText
        #         except Exception as e:
        #             log.debug("Pyteseract error in player name recognition: " + str(e))
        return True

    def get_other_player_funds(self, p):
        if p.selected_strategy['gather_player_names'] == 1:
            for i in range(1, self.total_players - 1):
                self.gui_signals.signal_status.emit(f"Check other players funds {i}")
                self.gui_signals.signal_progressbar_increase.emit(1)
                value = self.player_funds[i]
                value = float(value) if value != '' else ''
                self.other_players[i]['funds'] = value

        return True

    def get_other_player_pots(self):
        self.gui_signals.signal_status.emit(f"Get table pots")
        self.gui_signals.signal_progressbar_increase.emit(2)
        self.get_pots()

        exclude = set(range(self.total_players)) - set(self.players_in_game)
        self.gui_signals.signal_status.emit(f"Get player pots of players in game {self.players_in_game}")
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.get_player_pots(skip=list(exclude.union({0})))

        for n in range(1, self.total_players):
            if self.player_pots[n] != "":
                try:
                    self.other_players[n - 1]['pot'] = float(self.player_pots[n])
                except:
                    self.other_players[n - 1]['pot'] = 0

                log.debug("FINAL POT after regex: " + str(self.other_players[n - 1]))

        return True

    def get_bot_pot(self, p):
        self.gui_signals.signal_status.emit("Get bot pot")
        from poker.tools.screen_operations import ocr
        value = ocr(self.screenshot, 'player_pot_area', self.table_dict, str(0))

        if value != "":
            self.bot_pot = float(value)
            self.value = float(value)

        if value == "":
            self.bot_pot = 0
            log.debug("Assuming bot pot is 0")

        return True

    def get_other_player_status(self, p, h):
        self.gui_signals.signal_status.emit("Get other playsrs' status")
        self.gui_signals.signal_progressbar_increase.emit(2)
        self.get_players_in_game()

        self.covered_players = 0
        for i in range(1, self.total_players):
            if i in self.players_in_game:
                self.covered_players += 1
                self.other_players[i - 1]['status'] = 1
            else:
                self.other_players[i - 1]['status'] = 0

            self.other_players[i - 1]['utg_position'] = self.get_utg_from_abs_pos(
                self.other_players[i - 1]['abs_position'],
                self.dealer_position)

        self.other_active_players = sum([v['status'] for v in self.other_players])
        if self.gameStage == "PreFlop":
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 3 - 1])
        else:
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 1 - 1])
        self.playersAhead = self.other_active_players - self.playersBehind
        self.isHeadsUp = True if self.other_active_players < 2 else False  # pylint: disable=simplifiable-if-expression
        log.debug("Other players in the game: " + str(self.other_active_players))
        log.debug("Players behind: " + str(self.playersBehind))
        log.debug("Players ahead: " + str(self.playersAhead))

        if h.round_number == 0:
            reference_pot = float(p.selected_strategy['bigBlind'])
        else:
            reference_pot = self.get_bot_pot(p)

        self.get_other_player_pots()
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
                not (self.checkButton is True and self.playersAhead == 0):
            self.other_player_has_initiative = True
        else:
            self.other_player_has_initiative = False

        log.info("Other player has initiative: " + str(self.other_player_has_initiative))

        return True

    def get_round_number(self, h):
        self.gui_signals.signal_status.emit(f"Get round number")
        self.gui_signals.signal_progressbar_increase.emit(1)
        if h.histGameStage == self.gameStage and h.lastRoundGameID == h.GameID:
            h.round_number += 1
        else:
            h.round_number = 0
        return True

    def get_dealer_position(self):
        self.gui_signals.signal_status.emit(f"Get dealer position")
        self.gui_signals.signal_progressbar_increase.emit(1)
        self.get_dealer_position2()
        self.position_utg_plus = (self.total_players + 3 - self.dealer_position) % self.total_players

        log.info('Bot position is UTG+' + str(self.position_utg_plus))  # 0 mean bot is UTG

        if self.position_utg_plus == '':
            self.position_utg_plus = 0
            self.dealer_position = 3
            log.error('Could not determine dealer position. Assuming UTG')
        else:
            log.info('Dealer position (0 is myself and 1 is next player): ' + str(self.dealer_position))

        self.big_blind_position_abs_all = (self.dealer_position + 2) % 6  # 0 is myself, 1 is player to my left
        self.big_blind_position_abs_op = self.big_blind_position_abs_all - 1
        self.gui_signals.signal_progressbar_increase.emit(5)

        return True

    def get_total_pot_value(self, h):
        self.totalPotValue = self.total_pot

        if self.totalPotValue != "":
            try:
                self.totalPotValue = float(self.totalPotValue)
            except:
                self.totalPotValue = 0

        if self.totalPotValue == "" or self.totalPotValue < 0:
            self.totalPotValue = 0
            log.warning("Total pot regex problem: " + str(self.totalPotValue))
            self.gui_signals.signal_status.emit("Unable to get pot value")
            self.screenshot.save("pics/ErrPotValue.png")
            self.totalPotValue = h.previousPot

        log.info("Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_round_pot_value(self, h):

        self.round_pot_value = self.current_round_pot

        if self.round_pot_value != "":
            try:
                self.round_pot_value = float(self.round_pot_value)
            except:
                self.round_pot_value = 0

        if self.round_pot_value == "":
            self.round_pot_value = 0
            self.gui_signals.signal_status.emit("Unable to get round pot value")
            log.warning("unable to get round pot value")
            # self.round_pot_value = h.previous_round_pot_value
            self.screenshot.save("pics/ErrRoundPotValue.png")

        self.gui_signals.signal_progressbar_increase.emit(5)
        return True

    def get_my_funds(self, h, p):
        self.gui_signals.signal_status.emit(f"Get my funds")
        self.gui_signals.signal_progressbar_increase.emit(1)
        self.get_my_funds2()
        self.myFunds = self.player_funds[0]
        if self.myFunds != "":
            try:
                self.myFunds = float(self.myFunds)
            except:
                self.myFunds = ""

        if self.myFunds == "":
            self.myFundsError = True
            self.myFunds = float(h.myFundsHistory[-1])
            log.info("myFunds not regognised! Taking last value")
            self.gui_signals.signal_status.emit("Funds NOT recognised")
            log.warning("Funds NOT recognised. See pics/FundsError.png to see why.")
            self.entireScreenPIL.save("pics/FundsError.png")
            time.sleep(0.5)

        log.info("my_funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self, p):
        self.gui_signals.signal_status.emit(f"Get call value")
        self.gui_signals.signal_progressbar_increase.emit(1)
        if not self.checkButton:

            self.currentCallValue = self.get_call_value()

        elif self.checkButton:
            self.currentCallValue = 0

        if self.currentCallValue != "":
            self.getCallButtonValueSuccess = True
        else:
            self.checkButton = True
            log.debug("Assuming check button as call value is zero")
        self.gui_signals.signal_progressbar_increase.emit(5)
        return True

    def get_current_bet_value(self, p):
        self.gui_signals.signal_status.emit(f"Get raise value")
        self.gui_signals.signal_progressbar_increase.emit(1)

        self.currentBetValue = self.get_raise_value()

        # if self.currentCallValue == '' and p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
        #     log.warning("Taking call value from button on the right")
        #     self.currentCallValue = self.currentBetValue
        #     self.currentBetValue = 9999999

        if self.currentBetValue == '':
            log.warning("No bet value")
            self.currentBetValue = 9999999.0

        if self.currentCallValue == '':
            log.error("Call Value was empty")
            # if p.selected_strategy['pokerSite'][0:2] == "PS" and self.allInCallButton:
            #     self.currentCallValue = self.currentBetValue
            #     self.currentBetValue = 9999999
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

        log.info("Final call value: " + str(self.currentCallValue))
        log.info("Final bet value: " + str(self.currentBetValue))
        self.gui_signals.signal_progressbar_increase.emit(5)
        return True

    def get_lost_everything(self, h, t, p, gui_signals):
        lost_everything = self.lost_everything()
        if lost_everything:
            h.lastGameID = str(h.GameID)
            self.myFundsChange = float(0) - float(h.myFundsHistory[-1])
            self.game_logger.mark_last_game(t, h, p)
            self.gui_signals.signal_status.emit("Everything is lost. Last game has been marked.")
            self.gui_signals.signal_progressbar_reset.emit()
            log.warning("Game over")
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
        self.gui_signals.signal_status.emit(f"Check if new hand")
        self.gui_signals.signal_progressbar_increase.emit(1)
        self.gui_signals.signal_progressbar_increase.emit(5)
        if h.previousCards != self.mycards:
            log.info("+++========================== NEW HAND ==========================+++")
            self.time_new_cards_recognised = datetime.datetime.utcnow()
            if p.selected_strategy['collusion'] == 1:
                self.get_game_number_on_screen(h)
            else:
                self.Game_Number = 0
                h.game_number_on_screen = 0
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
            log.debug("Game number on screen: " + str(h.game_number_on_screen))
            self.get_my_funds(h, p)

        return True

    def upload_collusion_wrapper(self, p, h):
        if p.selected_strategy['collusion'] == 1:
            if not (h.GameID, self.gameStage) in h.uploader:
                h.uploader[(h.GameID, self.gameStage)] = True
                self.game_logger.upload_collusion_data(h.game_number_on_screen, self.mycards, p, self.gameStage)
        return True

    def get_game_number_on_screen(self, h):
        self.Game_Number = self.get_game_number_on_screen2()
        h.game_number_on_screen = self.Game_Number
        log.debug("Game Number: " + str(self.Game_Number))
        return True
