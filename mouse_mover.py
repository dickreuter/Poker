from captcha.key_press_vbox import *
import logging
import random
import numpy as np
import pymouse

class MouseMover():
    def __init__(self):
        self.mouse=pymouse.PyMouse()

    def click(self, x, y):
        self.mouse.move(x,y)
        self.mouse.click(x,y)
        time.sleep(np.random.uniform(0.3, 0.5, 1)[0])

    def mouse_mover(self, x1, y1, x2, y2):
        speed = .4
        stepMin = 7
        stepMax = 50
        rd1 = int(np.round(np.random.uniform(stepMin, stepMax, 1)))
        rd2 = int(np.round(np.random.uniform(stepMin, stepMax, 1)))

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
            self.mouse.move(x, y)
            time.sleep(np.random.uniform(0.01 * speed, 0.03 * speed, 1)[0])

            self.mouse.move(x2, y2)

    def mouse_clicker(self, x2, y2, buttonToleranceX, buttonToleranceY):

        xrand = int(np.random.uniform(0, buttonToleranceX, 1))
        yrand = int(np.random.uniform(0, buttonToleranceY, 1))
        self.mouse.move(x2 + xrand, y2 + yrand)

        time.sleep(np.random.uniform(0.1, 0.2, 1)[0])

        self.click(x2 + xrand, y2 + yrand)

        time.sleep(np.random.uniform(0.1, 0.5, 1)[0])

class MouseMoverPP(MouseMover):
    def enter_captcha(self, captchaString, topleftcorner):
        logger.warning("Entering Captcha: " + str(captchaString))
        buttonToleranceX = 30
        buttonToleranceY = 0
        tlx = topleftcorner[0]
        tly = topleftcorner[1]
        (x1, y1) = self.mouse.position()
        x2 = 30 + tlx
        y2 = 565 + tly
        self.mouse_mover(x1, y1, x2, y2)
        self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
        try:
            write_characters_to_virtualbox(captchaString, "win")
        except:
            logger.info("Captcha Error")
            pass

    def mouse_action(self, decision, topleftcorner, betplus_inc, current_bluff, logger):
        logger.info("Moving Mouse: "+str(decision))
        tlx = int(topleftcorner[0])
        tly = int(topleftcorner[1])
        (x1, y1) = self.mouse.position()
        buttonToleranceX = 100
        buttonToleranceY = 35

        if decision == "Imback":
            time.sleep(np.random.uniform(1, 5, 1)[0])
            buttonToleranceX = 100
            buttonToleranceY = 31
            x2 = 560 + tlx
            y2 = 492 + tly
            logger.debug( "move mouse to "+str(y2))
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Fold":
            x2 = 419 + tlx
            y2 = 493 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Call" or decision == "Call Deception":
            x2 = 543 + tlx
            y2 = 492 + tly

            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Check" or decision == "Check Deception":
            x2 = 543 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet":
            x2 = 673 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "BetPlus":
            buttonToleranceX = 4
            buttonToleranceY = 5
            x2 = 673 + tlx
            y2 = 465 + tly
            self.mouse_mover(x1, y1, x2, y2)

            for n in range(int(betplus_inc)):
                self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)
                # if t.minBet > float(betplus_inc): continue

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 100
            buttonToleranceY = 35
            time.sleep(np.random.uniform(0.1, 0.5, 1)[0])
            x2 = 675 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1temp, y1temp, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet Bluff":
            buttonToleranceX = 4
            buttonToleranceY = 5
            x2 = 673 + tlx
            y2 = 465 + tly
            self.mouse_mover(x1, y1, x2, y2)

            if current_bluff > 1:
                for n in range(current_bluff - 1):
                    self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 100
            buttonToleranceY = 35
            time.sleep(np.random.uniform(0.1, 0.5, 1)[0])
            x2 = 675 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1temp, y1temp, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet half pot":
            buttonToleranceX = 10
            buttonToleranceY = 5
            x2 = 477 + tlx
            y2 = 433 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.5, 1)[0])
            x2 = 675 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1temp, y1temp, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet pot":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 590 + tlx
            y2 = 433 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1)[0])
            x2 = 675 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1temp, y1temp, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        if decision == "Bet max":
            buttonToleranceX = 30
            buttonToleranceY = 10
            x2 = 722 + tlx
            y2 = 492 - 65 + tly
            self.mouse_mover(x1, y1, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

            x1temp = x2
            y1temp = y2

            buttonToleranceX = 635 - 525
            buttonToleranceY = 564 - 531
            time.sleep(np.random.uniform(0.1, 0.7, 1)[0])
            x2 = 675 + tlx
            y2 = 492 + tly
            self.mouse_mover(x1temp, y1temp, x2, y2)
            self.mouse_clicker(x2, y2, buttonToleranceX, buttonToleranceY)

        xscatter = int(np.round(np.random.uniform(1600, 1800, 1), 0))
        yscatter = int(np.round(np.random.uniform(300, 400, 1), 0))

        time.sleep(np.random.uniform(0.4, 1.0, 1)[0])

        self.mouse_mover(x2, y2, xscatter, yscatter)


if __name__=="__main__":
    logger = logging.getLogger()
    m=MouseMoverPP()
    topleftcorner=[22,22]
    m.mouse_action("Fold", topleftcorner, 0, 0, logger)