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
        time.sleep(np.random.uniform(0.2, 0.3, 1)[0])

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

class MouseMoverTableBased(MouseMover):
    def __init__(self, pokersite,betplus_inc=1,bet_bluff_inc=1):
        super().__init__()

        # amount,pre-delay,x1,xy,x1tolerance,x2tolerance
        coo = {
            "PP": {"Fold":          [[1,0,419,493,100,35]],
                   "Imback":        [[1,5,560,492,100,31]],
                   "Call":          [[1, 0, 543, 492, 100, 31]],
                   "Check":         [[1, 0, 543, 492, 100, 31]],
                   "Bet":           [[1, 0, 673, 492, 100, 31]],
                   "Bet Plus":       [[betplus_inc, 0.3, 673, 465, 30, 10],
                                     [1,0, 675, 492, 100, 31]],
                   "Bet Bluff":      [[bet_bluff_inc, 0.3, 673, 465, 30, 10],
                                    [1, 0, 675, 492, 100, 31]],
                   "Bet half pot":  [[1, 0.3, 477, 433, 30, 10],
                                     [1, 0, 675, 492, 100, 31]],
                   "Bet max":       [[1, 0.3, 722, 492 - 65, 30, 10],
                                    [1, 0, 675, 492, 100, 31]],
                   },
            "PS": {"Fold": [[]],
                   "Call": [[]]
            }
        }
        self.coo=coo[pokersite]


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


    def mouse_action(self, decision, topleftcorner, logger):
        if decision  =='Bet Bluff': decision='Bet Plus'
        if decision == 'Check Deception': decision = 'Check'
        if decision == 'Call Deception': decision = 'Call'
        if decision == 'Bet Bluff': decision = 'Bet'

        logger.info("Moving Mouse: "+str(decision))
        tlx = int(topleftcorner[0])
        tly = int(topleftcorner[1])

        logger.info("Mouse moving to: "+decision)
        for action in self.coo[decision]:
            for i in range (action[0]):
                time.sleep(np.random.uniform(0, action[1], 1)[0])
                logger.debug("Mouse action:"+str(action))
                (x1, y1) = self.mouse.position()
                self.mouse_mover(x1, y1, action[2]+ tlx, action[3]+ tly)
                self.mouse_clicker(action[2]+ tlx, action[3]+ tly,action[4], action[5])

        xscatter = int(np.round(np.random.uniform(1600, 1800, 1), 0))
        yscatter = int(np.round(np.random.uniform(300, 400, 1), 0))

        time.sleep(np.random.uniform(0.4, 1.0, 1)[0])
        time.sleep(2)
        (x2, y2) = self.mouse.position()
        self.mouse_mover(x2, y2, xscatter, yscatter)


if __name__=="__main__":
    logger = logging.getLogger()
    m=MouseMoverTableBased('PP',5,5)
    topleftcorner=[22,22]
    m.mouse_action("Bet Plus", topleftcorner, logger)