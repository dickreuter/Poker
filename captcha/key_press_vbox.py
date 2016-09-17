'''
Pressing keys in virtual box from outside virtual box to solve Captchas
'''

import time
import subprocess
import pandas as pd
import os

def read_scancode_table():
    df = pd.read_excel('virtualbox_scancodes.xlsx', sheetname='Sheet1')
    return df

def call_virtualbox(h, vbox):
    hList = h.split()
    for h in hList:
        param = [r"C:\Program Files\Oracle\VirtualBox\vboxmanage", "controlvm", vbox, "keyboardputscancode", h];
        try:
            subprocess.check_call(param)
        except:
            print("VMBOX keyboard entering error")
        time.sleep(0.2)

def get_key_release_code(h):
    dec = int(str(h), 16)
    rel = dec + 128
    code = hex(rel)
    return (code[-2:])

def tableLookup(char, Table):
    i = Table.loc[Table['Key'] == char].index.get_values()[0]
    h = Table.at[i, 'Code']
    s = Table.at[i, 'PressShift']
    return h, s

def generate_output(input):
    Table = read_scancode_table()
    letters = list(input)
    output = []
    for letter in letters:
        try:
            h, s = tableLookup(letter, Table)
        except:
            print("Scancode Tablelookup failure")
            h, s = (0, 0)
        if (s == 1): output.append("36 ")  # shift
        r = get_key_release_code(h)
        output.append(str(h) + " " + r + " ")
        if (s == 1): output.append("b6 ")  # shift release

    return (''.join(output))

def write_characters_to_virtualbox(input, vbox):
    result = (generate_output(input)) + "1C 9c"  # add ENTER
    call_virtualbox(result, vbox)


if __name__ == '__main__':
    write_characters_to_virtualbox("Anybody around", "Windows")
