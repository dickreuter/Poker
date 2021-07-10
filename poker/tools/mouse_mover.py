import logging
import random
import time

import numpy as np

from poker import pymouse
from poker.tools.helper import get_config
from poker.tools.vbox_manager import VirtualBoxController

log = logging.getLogger(__name__)


class MouseMover(VirtualBoxController):
    def __init__(self, vbox_mode):
        if vbox_mode:
            super().__init__()
        self.mouse = pymouse.PyMouse()
        self.vbox_mode = vbox_mode
        self.old_x = int(np.round(np.random.uniform(0, 500, 1)))
        self.old_y = int(np.round(np.random.uniform(0, 500, 1)))

    def click(self, x, y):
        if self.vbox_mode:
            self.mouse_move_vbox(x, y)
            self.mouse_click_vbox(x, y)
        else:
            # win32api.SetCursorPos((x, y))
            self.mouse.move(x, y)
            self.mouse.click(x, y)

        time.sleep(np.random.uniform(0.01, 0.1, 1)[0])

    def mouse_mover(self, x1, y1, x2, y2):
        speed = .5
        stepMin = 7
        stepMax = 20
        rd1 = int(np.round(np.random.uniform(stepMin, stepMax, 1)[0]))
        rd2 = int(np.round(np.random.uniform(stepMin, stepMax, 1)[0]))

        xa = list(range(x1, x2, rd1))
        ya = list(range(y1, y2, rd2))

        for k in range(0, max(0, len(xa) - len(ya))):
            ya.append(y2)
        for k in range(0, max(0, len(ya) - len(xa))):
            xa.append(x2)

        xTremble = 20
        yTremble = 20

        for i in range(len(max(xa, ya))):
            x = xa[i] + int(+random.random() * xTremble)
            y = ya[i] + int(+random.random() * yTremble)
            if self.vbox_mode:
                try:
                    self.mouse_move_vbox(x, y)
                except AttributeError:
                    raise RuntimeError("Virtual box not detected."
                                       "Switch to direct mouse control in setup or open VirtualBox")
                time.sleep(np.random.uniform(0.01 * speed, 0.03 * speed, 1)[0])
            else:
                self.mouse.move(x, y)
                time.sleep(np.random.uniform(0.01 * speed, 0.03 * speed, 1)[0])

        if self.vbox_mode:
            self.mouse_move_vbox(x2, y2)
        else:
            self.mouse.move(x2, y2)
            # win32api.SetCursorPos((x2, y2))

        self.old_x = x2
        self.old_y = y2

    def mouse_clicker(self, x2, y2, buttonToleranceX, buttonToleranceY):
        xrand = int(np.random.uniform(0, buttonToleranceX, 1)[0])
        yrand = int(np.random.uniform(0, buttonToleranceY, 1)[0])

        if self.vbox_mode:
            self.mouse_move_vbox(x2 + xrand, y2 + yrand)
        else:
            self.mouse.move(x2 + xrand, y2 + yrand)

        time.sleep(np.random.uniform(0.1, 0.2, 1)[0])

        self.click(x2 + xrand, y2 + yrand)
        log.debug("Clicked: {0} {1}".format(x2 + xrand, y2 + yrand))

        time.sleep(np.random.uniform(0.1, 0.5, 1)[0])


class MouseMoverTableBased(MouseMover):
    def __init__(self, table_dict):
        config = get_config()

        try:
            mouse_control = config.config.get('main', 'control')
            if mouse_control != 'Direct mouse control':
                self.vbox_mode = True
            else:
                self.vbox_mode = False
        except:
            self.vbox_mode = False

        super().__init__(self.vbox_mode)

        self.table_dict = table_dict

    def move_mouse_away_from_buttons(self):
        x2 = int(np.round(np.random.uniform(1700, 2000, 1), 0)[0])
        y2 = int(np.round(np.random.uniform(10, 200, 1), 0)[0])

        time.sleep(np.random.uniform(0.5, 1.2, 1)[0])
        if not self.vbox_mode:
            (x1, y1) = self.mouse.position()
        else:
            x1 = self.old_x
            y1 = self.old_y
        x1 = 10 if x1 > 2000 else x1
        y1 = 10 if y1 > 1000 else y1

        try:
            log.debug("Moving mouse away: " + str(x1) + "," + str(y1) + "," + str(x2) + "," + str(y2))
            self.mouse_mover(x1, y1, x2, y2)
        except Exception as e:
            log.warning("Moving mouse away failed")

    def move_mouse_away_from_buttons_jump(self):
        x2 = int(np.round(np.random.uniform(1700, 2000, 1), 0)[0])
        y2 = int(np.round(np.random.uniform(10, 200, 1), 0)[0])

        try:
            log.debug("Moving mouse away via jump: " + str(x2) + "," + str(y2))
            if self.vbox_mode:
                self.mouse_move_vbox(x2, y2)
            else:
                self.mouse.move(x2, y2)
        except Exception as e:
            log.warning("Moving mouse via jump away failed" + str(e))

    def mouse_action(self, decision, topleftcorner, options=None):
        if decision == 'Check Deception':
            decision = 'Check'
        if decision == 'Call Deception':
            decision = 'Call'

        tlx = int(topleftcorner[0])
        tly = int(topleftcorner[1])

        log.debug("Mouse moving to: " + decision)
        log.debug(f"Top left corner position: {tlx} {tly}")

        if decision == "Fold":
            coo = self.table_dict['mouse_fold']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Imback":
            time.sleep(np.random.uniform(0, 3, 1)[0])
            coo = self.table_dict['mouse_imback']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "resume_hand":
            time.sleep(np.random.uniform(0, 3, 1)[0])
            coo = self.table_dict['mouse_resume_hand']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Call":
            coo = self.table_dict['mouse_call']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Call2":
            coo = self.table_dict['mouse_call2']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Check":
            coo = self.table_dict['mouse_check']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Bet":
            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "BetPlus":
            for i in range(int(options['increases_num'])):
                coo = self.table_dict['mouse_increase']
                self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Bet Bluff":
            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Bet half pot":
            coo = self.table_dict['mouse_half_pot']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Bet pot":
            coo = self.table_dict['mouse_full_pot']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Bet max":
            coo = self.table_dict['mouse_all_in']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

            coo = self.table_dict['mouse_raise']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        time.sleep(0.2)
        self.move_mouse_away_from_buttons()

    def take_action(self, x1, y1, x2, y2):  #

        log.debug(f"Target position: {x1} {y1} {x2} {y2}")
        if not self.vbox_mode:
            (old_x1, old_y1) = self.mouse.position()
        else:
            old_x1 = self.old_x
            old_y1 = self.old_y

        self.mouse_mover(old_x1, old_y1, x1, y1)
        self.mouse_clicker(x1, y1, x2 - x1, y2 - y1)
