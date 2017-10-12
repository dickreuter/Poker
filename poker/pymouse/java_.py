#Copyright 2013 Paul Barton
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

from java.awt import Robot, Toolkit
from java.awt.event import InputEvent
from java.awt.MouseInfo import getPointerInfo
from .base import PyMouseMeta

r = Robot()

class PyMouse(PyMouseMeta):
    def press(self, x, y, button = 1):
        button_list = [None, InputEvent.BUTTON1_MASK, InputEvent.BUTTON3_MASK, InputEvent.BUTTON2_MASK]
        self.move(x, y)
        r.mousePress(button_list[button])

    def release(self, x, y, button = 1):
        button_list = [None, InputEvent.BUTTON1_MASK, InputEvent.BUTTON3_MASK, InputEvent.BUTTON2_MASK]
        self.move(x, y)
        r.mouseRelease(button_list[button])
    
    def move(self, x, y):
        r.mouseMove(x, y)

    def position(self):
        loc = getPointerInfo().getLocation()
        return loc.getX, loc.getY

    def screen_size(self):
        dim = Toolkit.getDefaultToolkit().getScreenSize()
        return dim.getWidth(), dim.getHeight()
