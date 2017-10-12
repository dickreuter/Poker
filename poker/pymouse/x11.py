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

from Xlib.display import Display
from Xlib import X
from Xlib.ext.xtest import fake_input
from Xlib.ext import record
from Xlib.protocol import rq

from .base import PyMouseMeta, PyMouseEventMeta, ScrollSupportError


class X11Error(Exception):
    """An error that is thrown at the end of a code block managed by a
    :func:`display_manager` if an *X11* error occurred.
    """
    pass


def display_manager(display):
    """Traps *X* errors and raises an :class:``X11Error`` at the end if any
    error occurred.

    This handler also ensures that the :class:`Xlib.display.Display` being
    managed is sync'd.

    :param Xlib.display.Display display: The *X* display.

    :return: the display
    :rtype: Xlib.display.Display
    """
    from contextlib import contextmanager

    @contextmanager
    def manager():
        errors = []

        def handler(*args):
            errors.append(args)

        old_handler = display.set_error_handler(handler)
        yield display
        display.sync()
        display.set_error_handler(old_handler)
        if errors:
            raise X11Error(errors)

    return manager()


def translate_button_code(button):
    # In X11, the button numbers are:
    #  leftclick=1, middleclick=2, rightclick=3
    #  For the purposes of the cross-platform interface of PyMouse, we
    #  invert the button number values of the right and middle buttons
    if button in [1, 2, 3]:
        return (None, 1, 3, 2)[button]
    else:
        return button

def button_code_to_scroll_direction(button):
    # scrollup=4, scrolldown=5, scrollleft=6, scrollright=7
    return {
        4: (1, 0),
        5: (-1, 0),
        6: (0, 1),
        7: (0, -1),
    }[button]


class PyMouse(PyMouseMeta):
    def __init__(self, display=None):
        PyMouseMeta.__init__(self)
        self.display = Display(display)
        self.display2 = Display(display)

    def press(self, x, y, button=1):
        self.move(x, y)

        with display_manager(self.display) as d:
            fake_input(d, X.ButtonPress, translate_button_code(button))

    def release(self, x, y, button=1):
        self.move(x, y)

        with display_manager(self.display) as d:
            fake_input(d, X.ButtonRelease, translate_button_code(button))

    def scroll(self, vertical=None, horizontal=None, depth=None):
        #Xlib supports only vertical and horizontal scrolling
        if depth is not None:
            raise ScrollSupportError('PyMouse cannot support depth-scrolling \
in X11. This feature is only available on Mac.')

        #Execute vertical then horizontal scrolling events
        if vertical is not None:
            vertical = int(vertical)
            if vertical == 0:  # Do nothing with 0 distance
                pass
            elif vertical > 0:  # Scroll up if positive
                self.click(*self.position(), button=4, n=vertical)
            else:  # Scroll down if negative
                self.click(*self.position(), button=5, n=abs(vertical))
        if horizontal is not None:
            horizontal = int(horizontal)
            if horizontal == 0:  # Do nothing with 0 distance
                pass
            elif horizontal > 0:  # Scroll right if positive
                self.click(*self.position(), button=7, n=horizontal)
            else:  # Scroll left if negative
                self.click(*self.position(), button=6, n=abs(horizontal))

    def move(self, x, y):
        if (x, y) != self.position():
            with display_manager(self.display) as d:
                fake_input(d, X.MotionNotify, x=x, y=y)

    def drag(self, x, y):
        with display_manager(self.display) as d:
            fake_input(d, X.ButtonPress, 1)
            fake_input(d, X.MotionNotify, x=x, y=y)
            fake_input(d, X.ButtonRelease, 1)

    def position(self):
        coord = self.display.screen().root.query_pointer()._data
        return coord["root_x"], coord["root_y"]

    def screen_size(self):
        width = self.display.screen().width_in_pixels
        height = self.display.screen().height_in_pixels
        return width, height


class PyMouseEvent(PyMouseEventMeta):
    def __init__(self, capture=False, capture_move=False, display=None):
        PyMouseEventMeta.__init__(self,
                                  capture=capture,
                                  capture_move=capture_move)
        self.display = Display(display)
        self.display2 = Display(display)
        self.ctx = self.display2.record_create_context(
            0,
            [record.AllClients],
            [{
                    'core_requests': (0, 0),
                    'core_replies': (0, 0),
                    'ext_requests': (0, 0, 0, 0),
                    'ext_replies': (0, 0, 0, 0),
                    'delivered_events': (0, 0),
                    'device_events': (X.ButtonPressMask, X.ButtonReleaseMask),
                    'errors': (0, 0),
                    'client_started': False,
                    'client_died': False,
            }])

    def run(self):
        try:
            if self.capture and self.capture_move:
                capturing = X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask
            elif self.capture:
                capturing = X.ButtonPressMask | X.ButtonReleaseMask
            elif self.capture_move:
                capturing = X.PointerMotionMask
            else:
                capturing = False

            if capturing:
                self.display2.screen().root.grab_pointer(True,
                                                         capturing,
                                                         X.GrabModeAsync,
                                                         X.GrabModeAsync,
                                                         0, 0, X.CurrentTime)
                self.display.screen().root.grab_pointer(True,
                                                         capturing,
                                                         X.GrabModeAsync,
                                                         X.GrabModeAsync,
                                                         0, 0, X.CurrentTime)

            self.display2.record_enable_context(self.ctx, self.handler)
            self.display2.record_free_context(self.ctx)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.state = False
        with display_manager(self.display) as d:
            d.ungrab_pointer(X.CurrentTime)
            d.record_disable_context(self.ctx)
        with display_manager(self.display2) as d:
            d.ungrab_pointer(X.CurrentTime)
            d.record_disable_context(self.ctx)

    def handler(self, reply):
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, self.display.display, None, None)

            if event.detail in [4, 5, 6, 7]:
                if event.type == X.ButtonPress:
                    self.scroll(event.root_x, event.root_y, *button_code_to_scroll_direction(event.detail))
            elif event.type == X.ButtonPress:
                self.click(event.root_x, event.root_y, translate_button_code(event.detail), True)
            elif event.type == X.ButtonRelease:
                self.click(event.root_x, event.root_y, translate_button_code(event.detail), False)
            else:
                self.move(event.root_x, event.root_y)
