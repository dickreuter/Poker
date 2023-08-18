import logging
import sys
import time

import numpy as np

from poker.decisionmaker.genetic_algorithm import GeneticAlgorithm
from poker.scraper.table_scraper import TableScraper
from poker.tools.helper import get_config
from poker.tools.vbox_manager import VirtualBoxController


# pylint: disable=no-member,unused-variable,no-self-use

class Table(TableScraper):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self, p, table_dict, gui_signals, game_logger, version, nn_model=None):
        self.version = version
        self.ip = ''
        self.logger = logging.getLogger('table')
        self.logger.setLevel(logging.DEBUG)
        self.gui_signals = gui_signals
        self.game_logger = game_logger
        self.nn_model = nn_model
        super().__init__(table_dict)

    def take_screenshot(self, initial, p):
        if initial:
            self.gui_signals.signal_status.emit("")
            self.gui_signals.signal_progressbar_reset.emit()
            if self.gui_signals.exit_thread == True: sys.exit()
            if self.gui_signals.pause_thread == True:
                while self.gui_signals.pause_thread:
                    time.sleep(.2)
                    if self.gui_signals.exit_thread == True: sys.exit()

            time.sleep(0.1)
        config = get_config()
        control = config.config.get('main', 'control')
        if control == 'Direct mouse control':
            self.take_screenshot2()
            self.entireScreenPIL = self.screenshot

        else:
            try:
                vb = VirtualBoxController()
                self.entireScreenPIL = vb.get_screenshot_vbox()
                self.logger.debug("Screenshot taken from virtual machine")
            except:
                self.logger.warning("No virtual machine found. Press SETUP to re initialize the VM controller")
                # gui_signals.signal_open_setup.emit(p,L)
                self.take_screenshot2()
                self.entireScreenPIL = self.screenshot

        self.gui_signals.signal_status.emit(str(p.current_strategy))
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.logger.info("Screenshot taken")
        return True

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
        utg_pos = (abs_pos - dealer_pos + 4) % self.total_players
        return utg_pos

    def get_abs_from_utg_pos(self, utg_pos, dealer_pos):
        abs_pos = (utg_pos + dealer_pos - 4) % self.total_players
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
