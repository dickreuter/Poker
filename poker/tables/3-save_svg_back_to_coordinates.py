#!/usr/bin/env python

import argparse
import xml.dom.minidom as minidom
import numpy as np
from coordinates_merger import CoordinatesMerger


if __name__=='__main__':
    parser = argparse.ArgumentParser(description='creates coordinates.json file from user edited .svg data.')
    
    args = vars(parser.parse_args())

    cm = CoordinatesMerger('../coordinates.json', './templates/')
    cm.save()

    print('coordinates.json saved')