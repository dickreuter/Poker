import logging
import random

import numpy as np
from poker.captcha.key_press_vbox import *
from configobj import ConfigObj

from poker import pymouse
from poker.tools.vbox_manager import VirtualBoxController


class MouseMover(VirtualBoxController):
    def __init__(self, vbox_mode):
        self.logger = logging.getLogger('mouse')
        self.logger.setLevel(logging.DEBUG)
        if vbox_mode:
            super().__init__()
        self.mouse= pymouse.PyMouse()
        self.vbox_mode=vbox_mode
        self.old_x=int(np.round(np.random.uniform(0, 500, 1)))
        self.old_y=int(np.round(np.random.uniform(0, 500, 1)))

    def click(self, x, y):
        if self.vbox_mode:
            self.mouse_move_vbox(x, y)
            self.mouse_click_vbox(x, y)
        else:
            #win32api.SetCursorPos((x, y))
            self.mouse.move(x, y)
            self.mouse.click(x, y)

        time.sleep(np.random.uniform(0.2, 0.3, 1)[0])

    def mouse_mover(self, x1, y1, x2, y2):
        speed = .6
        stepMin = 7
        stepMax = 50
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
                self.mouse_move_vbox(x, y)
                time.sleep(np.random.uniform(0.01 * speed, 0.03 * speed, 1)[0])
            else:
                self.mouse.move(x, y)
                time.sleep(np.random.uniform(0.01 * speed, 0.03 * speed, 1)[0])

        if self.vbox_mode:
            self.mouse_move_vbox(x2, y2)
        else:
            self.mouse.move(x2, y2)
            #win32api.SetCursorPos((x2, y2))

        self.old_x=x2
        self.old_y=y2



    def mouse_clicker(self, x2, y2, buttonToleranceX, buttonToleranceY):
        xrand = int(np.random.uniform(0, buttonToleranceX, 1)[0])
        yrand = int(np.random.uniform(0, buttonToleranceY, 1)[0])

        if self.vbox_mode:
            self.mouse_move_vbox(x2 + xrand, y2 + yrand)
        else:
            self.mouse.move(x2 + xrand, y2 + yrand)

        time.sleep(np.random.uniform(0.1, 0.2, 1)[0])

        self.click(x2 + xrand, y2 + yrand)
        self.logger.debug("Clicked: {0} {1}".format(x2 + xrand, y2 + yrand))

        time.sleep(np.random.uniform(0.1, 0.5, 1)[0])

class MouseMoverTableBased(MouseMover):
    def __init__(self, pokersite):
        config = ConfigObj("config.ini")
        self.logger = logging.getLogger('mouse')


        try:
            mouse_control = config['control']
            if mouse_control!='Direct mouse control': self.vbox_mode=True
            else: self.vbox_mode = False
        except:
            self.vbox_mode = False

        super().__init__(self.vbox_mode)

        # amount,pre-delay,x1,xy,x1tolerance,x2tolerance
        with open('coordinates.txt','r') as inf:
            c = eval(inf.read())
            coo=c['mouse_mover']

        self.coo=coo[pokersite[0:2]]

    def move_mouse_away_from_buttons(self):
        x2 = int(np.round(np.random.uniform(1700, 2000, 1), 0)[0])
        y2 = int(np.round(np.random.uniform(10, 200, 1), 0)[0])

        time.sleep(np.random.uniform(0.5, 1.2, 1)[0])
        if not self.vbox_mode: (x1, y1) = self.mouse.position()
        else:
            x1 = self.old_x
            y1 = self.old_y
        x1 = 10 if x1 > 2000 else x1
        y1 = 10 if y1 > 1000 else y1

        try:
            self.logger.debug("Moving mouse away: "+str(x1)+","+str(y1)+","+str(x2)+","+str(y2))
            self.mouse_mover(x1, y1, x2, y2)
        except Exception as e:
            self.logger.warning("Moving mouse away failed")

    def move_mouse_away_from_buttons_jump(self):
        x2 = int(np.round(np.random.uniform(1700, 2000, 1), 0)[0])
        y2 = int(np.round(np.random.uniform(10, 200, 1), 0)[0])

        try:
            self.logger.debug("Moving mouse away via jump: "+str(x2)+","+str(y2))
            if self.vbox_mode:
                self.mouse_move_vbox(x2, y2)
            else:
                self.mouse.move(x2, y2)
        except Exception as e:
            self.logger.warning("Moving mouse via jump away failed"+str(e))

    def enter_captcha(self, captchaString, topleftcorner):
        self.logger.warning("Entering Captcha: " + str(captchaString))
        buttonToleranceX = 30
        buttonToleranceY = 0
        tlx = topleftcorner[0]
        tly = topleftcorner[1]
        if not self.vbox_mode: (x1, y1) = self.mouse.position()
        else:
            x1=self.old_x
            y1=self.old_y
        x2 = 30 + tlx
        y2 = 565 + tly
        self.mouse_mover(x1, y1, x2, y2)
        self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
        try:
            write_characters_to_virtualbox(captchaString, "win")
        except:
            self.logger.info("Captcha Error")

    def mouse_action(self, decision, topleftcorner):
        if decision == 'Check Deception': decision = 'Check'
        if decision == 'Call Deception': decision = 'Call'

        tlx = int(topleftcorner[0])
        tly = int(topleftcorner[1])

        self.logger.info("Mouse moving to: "+decision)
        for action in self.coo[decision]:
            for i in range (int(action[0])):
                time.sleep(np.random.uniform(0, action[1], 1)[0])
                self.logger.debug("Mouse action:"+str(action))
                if not self.vbox_mode:
                    (x1, y1) = self.mouse.position()
                else:
                    x1 = self.old_x
                    y1 = self.old_y
                x2 = 30 + tlx
                self.mouse_mover(x1, y1, action[2]+ tlx, action[3]+ tly)
                self.mouse_clicker(action[2]+ tlx, action[3]+ tly,action[4], action[5])

        time.sleep(0.2)
        self.move_mouse_away_from_buttons()

if __name__=="__main__":
    logger = logging.getLogger()
    m=MouseMoverTableBased('PP',5,5)
    topleftcorner=[22,22]
    m.mouse_action(logger, topleftcorner)