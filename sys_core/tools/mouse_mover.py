import logging
import random
import time

import numpy as np
from PIL import ImageGrab

from sys_core import pymouse
from sys_core.tools.helper import get_config
from sys_core.tools.vbox_manager import VirtualBoxController
from sys_core.tools.button_detector import ButtonDetector, SmartMouseAction
from sys_core.tools import constants as const

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

    def _bezier_point(self, t, p0, p1, p2, p3):
        """Calculate point on cubic Bezier curve at t (0..1)"""
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        
        # Cubic Bezier formula: (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)t^2*P2 + t^3*P3
        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        return int(x), int(y)

    def mouse_mover(self, x1, y1, x2, y2):
        """Move mouse from (x1, y1) to (x2, y2) using human-like Bezier curves."""
        # Random control points for natural arc
        dist = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        offset = dist * 0.2  # Control point variance
        
        # P1: start control point
        cx1 = x1 + (x2 - x1) * 0.3 + np.random.uniform(-offset, offset)
        cy1 = y1 + (y2 - y1) * 0.3 + np.random.uniform(-offset, offset)
        
        # P2: end control point
        cx2 = x1 + (x2 - x1) * 0.7 + np.random.uniform(-offset, offset)
        cy2 = y1 + (y2 - y1) * 0.7 + np.random.uniform(-offset, offset)
        
        # Steps based on distance (more steps = smoother)
        steps = max(20, int(dist / 8))
        
        points = []
        for t in np.linspace(0, 1, steps):
            points.append(self._bezier_point(t, (x1,y1), (cx1,cy1), (cx2,cy2), (x2,y2)))
            
        # Move along curve with variable speed (ease-out)
        for i, (x, y) in enumerate(points):
            # Human physics: faster in middle, slower at end
            # Simple ease-out: delay increases as we get closer
            progress = i / len(points)
            base_delay = 0.001
            # Add micro-pauses for "friction"
            if random.random() < 0.05:
                base_delay += 0.02
                
            delay = base_delay + (progress * 0.005)  # Slow down slightly at end
            
            if self.vbox_mode:
                try:
                    self.mouse_move_vbox(x, y)
                except AttributeError:
                    pass
            else:
                self.mouse.move(x, y)
            
            time.sleep(delay)

        # Final correction to ensure exact target hit
        if self.vbox_mode:
            self.mouse_move_vbox(x2, y2)
        else:
            self.mouse.move(x2, y2)

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
        self.button_detector = ButtonDetector()
        self.smart_action = SmartMouseAction(table_dict)
        self.use_smart_detection = True  # Enable color-based detection

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

        # Use smart color-based detection for main action buttons
        if self.use_smart_detection and decision in ["Fold", "Call", "Check", "Bet", "Bet Bluff"]:
            screenshot = ImageGrab.grab()
            pos = self.smart_action.get_action_position(decision, screenshot, topleftcorner)
            if pos:
                log.info(f"Smart detection found {decision} at {pos}")
                # CRITICAL: get_action_position returns PIXEL coordinates
                # PyMouse expects POINT coordinates, so divide by RETINA_SCALE (2)
                from sys_core.tools import constants as const
                pos_pt = (
                    int(pos[0] / const.RETINA_SCALE),
                    int(pos[1] / const.RETINA_SCALE),
                    int(pos[2] / const.RETINA_SCALE),
                    int(pos[3] / const.RETINA_SCALE)
                )
                self.take_action(pos_pt[0], pos_pt[1], pos_pt[2], pos_pt[3])
                time.sleep(0.2)
                self.move_mouse_away_from_buttons()
                return
            else:
                log.warning(f"Smart detection failed for {decision}, falling back to table_dict")

        # Fallback to table_dict coordinates (no more hardcoded offsets!)
        if decision == "Fold":
            coo = self.table_dict['mouse_fold']
            self.take_action(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)

        elif decision == "Imback":
            # Check if we have a detected position for the 'Deal me in' button
            if hasattr(self, 'table_dict') and 'last_deal_me_in_pos' in self.table_dict:
                pos = self.table_dict['last_deal_me_in_pos']
                log.info(f"Clicking 'Deal me in' at detected position: {pos}")
                self.take_action(pos[0] + tlx, pos[1] + tly, pos[0] + tlx + 10, pos[1] + tly + 10)
            else:
                # Fallback to config coordinates
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
