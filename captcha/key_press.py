import ctypes

LONG = ctypes.c_long
DWORD = ctypes.c_ulong
ULONG_PTR = ctypes.POINTER(DWORD)
WORD = ctypes.c_ushort


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (('dx', LONG),
                ('dy', LONG),
                ('mouseData', DWORD),
                ('dwFlags', DWORD),
                ('time', DWORD),
                ('dwExtraInfo', ULONG_PTR))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (('wVk', WORD),
                ('wScan', WORD),
                ('dwFlags', DWORD),
                ('time', DWORD),
                ('dwExtraInfo', ULONG_PTR))


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (('uMsg', DWORD),
                ('wParamL', WORD),
                ('wParamH', WORD))


class _INPUTunion(ctypes.Union):
    _fields_ = (('mi', MOUSEINPUT),
                ('ki', KEYBDINPUT),
                ('hi', HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (('type', DWORD),
                ('union', _INPUTunion))


def SendInput(*inputs):
    nInputs = len(inputs)
    LPINPUT = INPUT * nInputs
    pInputs = LPINPUT(*inputs)
    cbSize = ctypes.c_int(ctypes.sizeof(INPUT))
    return ctypes.windll.user32.SendInput(nInputs, pInputs, cbSize)


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARD = 2


def Input(structure):
    if isinstance(structure, MOUSEINPUT):
        return INPUT(INPUT_MOUSE, _INPUTunion(mi=structure))
    if isinstance(structure, KEYBDINPUT):
        return INPUT(INPUT_KEYBOARD, _INPUTunion(ki=structure))
    if isinstance(structure, HARDWAREINPUT):
        return INPUT(INPUT_HARDWARE, _INPUTunion(hi=structure))
    raise TypeError('Cannot create INPUT structure!')


WHEEL_DELTA = 120
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_HWHEEL = 0x01000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100


def MouseInput(flags, x, y, data):
    return MOUSEINPUT(x, y, data, flags, 0, None)


VK_LBUTTON = 0x01  # Left mouse button
VK_RBUTTON = 0x02  # Right mouse button
VK_CANCEL = 0x03  # Control-break processing
VK_MBUTTON = 0x04  # Middle mouse button (three-button mouse)
VK_XBUTTON1 = 0x05  # X1 mouse button
VK_XBUTTON2 = 0x06  # X2 mouse button
VK_BACK = 0x08  # BACKSPACE key
VK_TAB = 0x09  # TAB key
VK_CLEAR = 0x0C  # CLEAR key
VK_RETURN = 0x0D  # ENTER key
VK_SHIFT = 0x10  # SHIFT key
VK_CONTROL = 0x11  # CTRL key
VK_MENU = 0x12  # ALT key
VK_PAUSE = 0x13  # PAUSE key
VK_CAPITAL = 0x14  # CAPS LOCK key
VK_KANA = 0x15  # IME Kana mode
VK_HANGUL = 0x15  # IME Hangul mode
VK_JUNJA = 0x17  # IME Junja mode
VK_FINAL = 0x18  # IME final mode
VK_HANJA = 0x19  # IME Hanja mode
VK_KANJI = 0x19  # IME Kanji mode
VK_ESCAPE = 0x1B  # ESC key
VK_CONVERT = 0x1C  # IME convert
VK_NONCONVERT = 0x1D  # IME nonconvert
VK_ACCEPT = 0x1E  # IME accept
VK_MODECHANGE = 0x1F  # IME mode change request
VK_SPACE = 0x20  # SPACEBAR
VK_PRIOR = 0x21  # PAGE UP key
VK_NEXT = 0x22  # PAGE DOWN key
VK_END = 0x23  # END key
VK_HOME = 0x24  # HOME key
VK_LEFT = 0x25  # LEFT ARROW key
VK_UP = 0x26  # UP ARROW key
VK_RIGHT = 0x27  # RIGHT ARROW key
VK_DOWN = 0x28  # DOWN ARROW key
VK_SELECT = 0x29  # SELECT key
VK_PRINT = 0x2A  # PRINT key
VK_EXECUTE = 0x2B  # EXECUTE key
VK_SNAPSHOT = 0x2C  # PRINT SCREEN key
VK_INSERT = 0x2D  # INS key
VK_DELETE = 0x2E  # DEL key
VK_HELP = 0x2F  # HELP key
VK_LWIN = 0x5B  # Left Windows key (Natural keyboard)
VK_RWIN = 0x5C  # Right Windows key (Natural keyboard)
VK_APPS = 0x5D  # Applications key (Natural keyboard)
VK_SLEEP = 0x5F  # Computer Sleep key
VK_NUMPAD0 = 0x60  # Numeric keypad 0 key
VK_NUMPAD1 = 0x61  # Numeric keypad 1 key
VK_NUMPAD2 = 0x62  # Numeric keypad 2 key
VK_NUMPAD3 = 0x63  # Numeric keypad 3 key
VK_NUMPAD4 = 0x64  # Numeric keypad 4 key
VK_NUMPAD5 = 0x65  # Numeric keypad 5 key
VK_NUMPAD6 = 0x66  # Numeric keypad 6 key
VK_NUMPAD7 = 0x67  # Numeric keypad 7 key
VK_NUMPAD8 = 0x68  # Numeric keypad 8 key
VK_NUMPAD9 = 0x69  # Numeric keypad 9 key
VK_MULTIPLY = 0x6A  # Multiply key
VK_ADD = 0x6B  # Add key
VK_SEPARATOR = 0x6C  # Separator key
VK_SUBTRACT = 0x6D  # Subtract key
VK_DECIMAL = 0x6E  # Decimal key
VK_DIVIDE = 0x6F  # Divide key
VK_F1 = 0x70  # F1 key
VK_F2 = 0x71  # F2 key
VK_F3 = 0x72  # F3 key
VK_F4 = 0x73  # F4 key
VK_F5 = 0x74  # F5 key
VK_F6 = 0x75  # F6 key
VK_F7 = 0x76  # F7 key
VK_F8 = 0x77  # F8 key
VK_F9 = 0x78  # F9 key
VK_F10 = 0x79  # F10 key
VK_F11 = 0x7A  # F11 key
VK_F12 = 0x7B  # F12 key
VK_F13 = 0x7C  # F13 key
VK_F14 = 0x7D  # F14 key
VK_F15 = 0x7E  # F15 key
VK_F16 = 0x7F  # F16 key
VK_F17 = 0x80  # F17 key
VK_F18 = 0x81  # F18 key
VK_F19 = 0x82  # F19 key
VK_F20 = 0x83  # F20 key
VK_F21 = 0x84  # F21 key
VK_F22 = 0x85  # F22 key
VK_F23 = 0x86  # F23 key
VK_F24 = 0x87  # F24 key
VK_NUMLOCK = 0x90  # NUM LOCK key
VK_SCROLL = 0x91  # SCROLL LOCK key
VK_LSHIFT = 0xA0  # Left SHIFT key
VK_RSHIFT = 0xA1  # Right SHIFT key
VK_LCONTROL = 0xA2  # Left CONTROL key
VK_RCONTROL = 0xA3  # Right CONTROL key
VK_LMENU = 0xA4  # Left MENU key
VK_RMENU = 0xA5  # Right MENU key
VK_BROWSER_BACK = 0xA6  # Browser Back key
VK_BROWSER_FORWARD = 0xA7  # Browser Forward key
VK_BROWSER_REFRESH = 0xA8  # Browser Refresh key
VK_BROWSER_STOP = 0xA9  # Browser Stop key
VK_BROWSER_SEARCH = 0xAA  # Browser Search key
VK_BROWSER_FAVORITES = 0xAB  # Browser Favorites key
VK_BROWSER_HOME = 0xAC  # Browser Start and Home key
VK_VOLUME_MUTE = 0xAD  # Volume Mute key
VK_VOLUME_DOWN = 0xAE  # Volume Down key
VK_VOLUME_UP = 0xAF  # Volume Up key
VK_MEDIA_NEXT_TRACK = 0xB0  # Next Track key
VK_MEDIA_PREV_TRACK = 0xB1  # Previous Track key
VK_MEDIA_STOP = 0xB2  # Stop Media key
VK_MEDIA_PLAY_PAUSE = 0xB3  # Play/Pause Media key
VK_LAUNCH_MAIL = 0xB4  # Start Mail key
VK_LAUNCH_MEDIA_SELECT = 0xB5  # Select Media key
VK_LAUNCH_APP1 = 0xB6  # Start Application 1 key
VK_LAUNCH_APP2 = 0xB7  # Start Application 2 key
VK_OEM_1 = 0xBA  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the ';:' key
VK_OEM_PLUS = 0xBB  # For any country/region, the '+' key
VK_OEM_COMMA = 0xBC  # For any country/region, the ',' key
VK_OEM_MINUS = 0xBD  # For any country/region, the '-' key
VK_OEM_PERIOD = 0xBE  # For any country/region, the '.' key
VK_OEM_2 = 0xBF  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the '/?' key
VK_OEM_3 = 0xC0  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the '`~' key
VK_OEM_4 = 0xDB  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the '[{' key
VK_OEM_5 = 0xDC  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the '\|' key
VK_OEM_6 = 0xDD  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the ']}' key
VK_OEM_7 = 0xDE  # Used for miscellaneous characters; it can vary by keyboard.
# For the US standard keyboard, the 'single-quote/double-quote' key
VK_OEM_8 = 0xDF  # Used for miscellaneous characters; it can vary by keyboard.
VK_OEM_102 = 0xE2  # Either the angle bracket key or the backslash key on the RT 102-key keyboard
VK_PROCESSKEY = 0xE5  # IME PROCESS key
VK_PACKET = 0xE7  # Used to pass Unicode characters as if they were keystrokes. The VK_PACKET key is the low word of a 32-bit Virtual Key value used for non-keyboard input methods. For more information, see Remark in KEYBDINPUT, SendInput, WM_KEYDOWN, and WM_KEYUP
VK_ATTN = 0xF6  # Attn key
VK_CRSEL = 0xF7  # CrSel key
VK_EXSEL = 0xF8  # ExSel key
VK_EREOF = 0xF9  # Erase EOF key
VK_PLAY = 0xFA  # Play key
VK_ZOOM = 0xFB  # Zoom key
VK_PA1 = 0xFD  # PA1 key
VK_OEM_CLEAR = 0xFE  # Clear key

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004

KEY_0 = 0x30
KEY_1 = 0x31
KEY_2 = 0x32
KEY_3 = 0x33
KEY_4 = 0x34
KEY_5 = 0x35
KEY_6 = 0x36
KEY_7 = 0x37
KEY_8 = 0x38
KEY_9 = 0x39
KEY_A = 0x41
KEY_B = 0x42
KEY_C = 0x43
KEY_D = 0x44
KEY_E = 0x45
KEY_F = 0x46
KEY_G = 0x47
KEY_H = 0x48
KEY_I = 0x49
KEY_J = 0x4A
KEY_K = 0x4B
KEY_L = 0x4C
KEY_M = 0x4D
KEY_N = 0x4E
KEY_O = 0x4F
KEY_P = 0x50
KEY_Q = 0x51
KEY_R = 0x52
KEY_S = 0x53
KEY_T = 0x54
KEY_U = 0x55
KEY_V = 0x56
KEY_W = 0x57
KEY_X = 0x58
KEY_Y = 0x59
KEY_Z = 0x5A


def KeybdInput(code, flags):
    return KEYBDINPUT(code, code, flags, 0, None)


def HardwareInput(message, parameter):
    return HARDWAREINPUT(message & 0xFFFFFFFF,
                         parameter & 0xFFFF,
                         parameter >> 16 & 0xFFFF)


def Mouse(flags, x=0, y=0, data=0):
    return Input(MouseInput(flags, x, y, data))


def Keyboard(code, flags=0):
    return Input(KeybdInput(code, flags))


def Hardware(message, parameter=0):
    return Input(HardwareInput(message, parameter))


################################################################################

import string

UPPER = frozenset('~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?')
LOWER = frozenset("`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./")
ORDER = string.ascii_letters + string.digits + ' \b\r\t'
ALTER = dict(zip('!@#$%^&*()', '1234567890'))
OTHER = {'`': VK_OEM_3,
         '~': VK_OEM_3,
         '-': VK_OEM_MINUS,
         '_': VK_OEM_MINUS,
         '=': VK_OEM_PLUS,
         '+': VK_OEM_PLUS,
         '[': VK_OEM_4,
         '{': VK_OEM_4,
         ']': VK_OEM_6,
         '}': VK_OEM_6,
         '\\': VK_OEM_5,
         '|': VK_OEM_5,
         ';': VK_OEM_1,
         ':': VK_OEM_1,
         "'": VK_OEM_7,
         '"': VK_OEM_7,
         ',': VK_OEM_COMMA,
         '<': VK_OEM_COMMA,
         '.': VK_OEM_PERIOD,
         '>': VK_OEM_PERIOD,
         '/': VK_OEM_2,
         '?': VK_OEM_2}


def keyboard_stream(string):
    mode = False
    for character in string.replace('\r\n', '\r').replace('\n', '\r'):
        if mode and character in LOWER or not mode and character in UPPER:
            yield Keyboard(VK_SHIFT, mode and KEYEVENTF_KEYUP)
            mode = not mode
        character = ALTER.get(character, character)
        if character in ORDER:
            code = ord(character.upper())
        elif character in OTHER:
            code = OTHER[character]
        else:
            continue
            raise ValueError('String is not understood!')
        yield Keyboard(code)
        yield Keyboard(code, KEYEVENTF_KEYUP)
    if mode:
        yield Keyboard(VK_SHIFT, KEYEVENTF_KEYUP)


################################################################################

import time, sys


def Write(text):
    time.sleep(3)
    for event in keyboard_stream('36 23 a3 b6 1E 9e 26 a6 26 a6 18 98 1C 9c'):
        SendInput(event)
        time.sleep(0.1)


if __name__ == '__main__':
    Write('abcdefghijklmnopqrstuvwxyz')


def switch_program():
    SendInput(Keyboard(VK_MENU), Keyboard(VK_TAB))
    time.sleep(0.2)
    SendInput(Keyboard(VK_TAB, KEYEVENTF_KEYUP),
              Keyboard(VK_MENU, KEYEVENTF_KEYUP))
    time.sleep(0.2)


def select_line():
    SendInput(Keyboard(VK_SHIFT, KEYEVENTF_EXTENDEDKEY),
              Keyboard(VK_END, KEYEVENTF_EXTENDEDKEY))
    time.sleep(0.2)
    SendInput(Keyboard(VK_SHIFT, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP),
              Keyboard(VK_END, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP))
    time.sleep(0.2)


def copy_line():
    SendInput(Keyboard(VK_CONTROL), Keyboard(KEY_C))
    time.sleep(0.2)
    SendInput(Keyboard(VK_CONTROL, KEYEVENTF_KEYUP),
              Keyboard(KEY_C, KEYEVENTF_KEYUP))
    time.sleep(0.2)


def next_line():
    SendInput(Keyboard(VK_HOME), Keyboard(VK_DOWN))
    time.sleep(0.2)
    SendInput(Keyboard(VK_HOME, KEYEVENTF_KEYUP),
              Keyboard(VK_DOWN, KEYEVENTF_KEYUP))
    time.sleep(0.2)


def prepare_text():
    # Open Text
    SendInput(Keyboard(KEY_M))
    time.sleep(0.2)
    SendInput(Keyboard(KEY_M, KEYEVENTF_KEYUP))
    time.sleep(0.2)
    # Goto Area
    SendInput(Keyboard(VK_TAB))
    time.sleep(0.2)
    SendInput(Keyboard(VK_TAB, KEYEVENTF_KEYUP))
    time.sleep(0.2)
    # Paste Message
    SendInput(Keyboard(VK_CONTROL), Keyboard(KEY_V))
    time.sleep(0.2)
    SendInput(Keyboard(VK_CONTROL, KEYEVENTF_KEYUP),
              Keyboard(KEY_V, KEYEVENTF_KEYUP))
    time.sleep(0.2)
    # Goto Button
    SendInput(Keyboard(VK_TAB))
    time.sleep(0.2)
    SendInput(Keyboard(VK_TAB, KEYEVENTF_KEYUP))
    time.sleep(0.2)


def send_one_message():
    select_line()
    copy_line()
    next_line()
    switch_program()
    prepare_text()
    # Send Message
    SendInput(Keyboard(VK_RETURN))
    time.sleep(0.2)
    SendInput(Keyboard(VK_RETURN, KEYEVENTF_KEYUP))
    time.sleep(10)
    switch_program()


def send_messages(total):
    time.sleep(10)
    for _ in range(total):
        send_one_message()
