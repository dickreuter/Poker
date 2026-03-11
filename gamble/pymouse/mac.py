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

import Quartz
from AppKit import NSEvent, NSScreen
from .base import PyMouseMeta, PyMouseEventMeta

pressID = [None, Quartz.kCGEventLeftMouseDown,
           Quartz.kCGEventRightMouseDown, Quartz.kCGEventOtherMouseDown]
releaseID = [None, Quartz.kCGEventLeftMouseUp,
             Quartz.kCGEventRightMouseUp, Quartz.kCGEventOtherMouseUp]


class PyMouse(PyMouseMeta):

    def press(self, x, y, button=1):
        event = Quartz.CGEventCreateMouseEvent(None,
                                        pressID[button],
                                        (x, y),
                                        button - 1)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def release(self, x, y, button=1):
        event = Quartz.CGEventCreateMouseEvent(None,
                                        releaseID[button],
                                        (x, y),
                                        button - 1)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def move(self, x, y):
        move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x, y), 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)

    def drag(self, x, y):
        drag = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, (x, y), 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag)

    def position(self):
        loc = NSEvent.mouseLocation()
        return loc.x, Quartz.CGDisplayPixelsHigh(0) - loc.y

    def screen_size(self):
        return NSScreen.mainScreen().frame().size.width, NSScreen.mainScreen().frame().size.height

    def scroll(self, vertical=None, horizontal=None, depth=None):
        #Local submethod for generating Mac scroll events in one axis at a time
        def scroll_event(y_move=0, x_move=0, z_move=0, n=1):
            for _ in range(abs(n)):
                scrollWheelEvent = Quartz.CGEventCreateScrollWheelEvent(
                    None,  # No source
                    Quartz.kCGScrollEventUnitLine,  # Unit of measurement is lines
                    3,  # Number of wheels(dimensions)
                    y_move,
                    x_move,
                    z_move)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, scrollWheelEvent)

        #Execute vertical then horizontal then depth scrolling events
        if vertical is not None:
            vertical = int(vertical)
            if vertical == 0:   # Do nothing with 0 distance
                pass
            elif vertical > 0:  # Scroll up if positive
                scroll_event(y_move=1, n=vertical)
            else:  # Scroll down if negative
                scroll_event(y_move=-1, n=abs(vertical))
        if horizontal is not None:
            horizontal = int(horizontal)
            if horizontal == 0:  # Do nothing with 0 distance
                pass
            elif horizontal > 0:  # Scroll right if positive
                scroll_event(x_move=1, n=horizontal)
            else:  # Scroll left if negative
                scroll_event(x_move=-1, n=abs(horizontal))
        if depth is not None:
            depth = int(depth)
            if depth == 0:  # Do nothing with 0 distance
                pass
            elif vertical > 0:  # Scroll "out" if positive
                scroll_event(z_move=1, n=depth)
            else:  # Scroll "in" if negative
                scroll_event(z_move=-1, n=abs(depth))


class PyMouseEvent(PyMouseEventMeta):
    def run(self):
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventMouseMoved) |
            Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown) |
            Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseUp) |
            Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown) |
            Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseUp) |
            Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown) |
            Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseUp),
            self.handler,
            None)

        loopsource = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(loop, loopsource, Quartz.kCFRunLoopDefaultMode)
        Quartz.CGEventTapEnable(tap, True)

        while self.state:
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 5, False)

    def handler(self, proxy, type, event, refcon):
        (x, y) = Quartz.CGEventGetLocation(event)
        if type in pressID:
            self.click(x, y, pressID.index(type), True)
        elif type in releaseID:
            self.click(x, y, releaseID.index(type), False)
        else:
            self.move(x, y)

        if self.capture:
            Quartz.CGEventSetType(event, Quartz.kCGEventNull)

        return event
