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

"""
The goal of PyMouse is to have a cross-platform way to control the mouse.
PyMouse should work on Windows, Mac and any Unix that has xlib.

PyMouse is a part of PyUserInput, along with PyKeyboard, for more information
about this project, see:
http://github.com/SavinaRoja/PyUserInput

PyMouse was originally developed by Pepijn de Vos. For the original repository,
see:
https://github.com/pepijndevos/PyMouse
"""

import sys

if sys.platform.startswith('java'):
    from .java_ import PyMouse

elif sys.platform == 'darwin':
    from .mac import PyMouse, PyMouseEvent

elif sys.platform == 'win32':
    from .windows import PyMouse, PyMouseEvent

else:
    from .x11 import PyMouse, PyMouseEvent

