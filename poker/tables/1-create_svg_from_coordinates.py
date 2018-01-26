#!/usr/bin/env python

import svgwrite
from random import randint, seed
import argparse 
import json 
from PIL import Image
from cornerFinder import CornerFinder

class SVGCreator():
    
    def __init__(self, coordinates_file):
        seed(654321)
        # get scraping/mouse data
        with open(coordinates_file) as inf:
            self.coordinates = json.load(inf)

        self.topLeftCornerOffset = [0, 0]

    
    def setCorner(self,corner):
        self.topLeftCornerOffset = corner


    # cast int ==> 'int px' or [int, int] ==> ['intpx','intpx']
    def toPix(self, someNumber):
        if isinstance(someNumber, list):
            return (self.toPix(el) for el in someNumber)
        return str(someNumber)+'px'


    def addTopLeftCornerOffset(self, coordinates):
        return [
            coordinates['x1'] + self.topLeftCornerOffset[0],
            coordinates['y1'] + self.topLeftCornerOffset[1],
            coordinates['x2'] + self.topLeftCornerOffset[0],
            coordinates['y2'] + self.topLeftCornerOffset[1]
        ]

    def beautifulRectangleElementWithNiceTextAtTheMiddle(self, dwg, coordinates, name, color, dataPath):
        x1, y1, x2, y2 = self.addTopLeftCornerOffset(coordinates)

        width, height = (x2-x1, y2-y1)
        fontHeight=12

        group = dwg.g(id=name.replace(" ", "__"))

        if 'image' in coordinates.keys():
            img = svgwrite.image.Image('../../'+coordinates['image'], insert=(x1,y1))
            img.update({'opacity':0.8, 'id':name.replace(" ", "__")})
            group.add(img)
            width=height=0

        rect = dwg.rect(insert=self.toPix([x1, y1]), size=self.toPix([width, height]), fill=color, stroke='black')
        rect.update({'class':dataPath, 'fill-opacity':0.45})


        x, y = self.toPix([x1, y1+height/2+fontHeight/2])
        txt = dwg.text(name, insert=(x,y), fill=color)
        txt.update({'stroke':'rgb(255,255,255)', 'stroke-width': '0.5px'})
        
        group.add(rect)
        group.add(txt)

        return group

    # adds a background to SVG file if exists
    def addBackground(self, dwg, table_name):
        backgroundImage = 'backgrounds/'+table_name+'.png'
        pathRelativeToFile = '../'+backgroundImage
        background = Image.open(backgroundImage)

        if background is not None:
            width, height = (str(s)+'px' for s in background.size)
            dwg.update({'height':height, 'width':width})
            background = svgwrite.image.Image(pathRelativeToFile, insert=(0,0))

            group = dwg.g(id='background')
            group.add(background)
            dwg.add(group)
        else:
            print(table_name+'.png background doesn\'t exist ! Put your screenshot in poker/tables/backgrounds/'+table_name+'.png to help you design scraping svg templates')


    # creates a square element for each [x,y,x2,y2] leaf element
    def nested_data(self, dwg, path, data, group, color,text):
        if isinstance(data, dict) and len(data) > 0:
            values = list(data.values())
            # add dict leaf
            if (isinstance(values[0], int) or isinstance(values[0], float)) and len(values) >= 4:
                group.add(self.beautifulRectangleElementWithNiceTextAtTheMiddle(dwg, data, text, color, path))
            else:
                # thing nested in dict
                for key, val in data.items():
                    self.nested_data(dwg, '|'.join([path, key]), val, group, color, text)


        elif isinstance(data, list) and len(data) > 0:
            # (dict or list) nested in list
            if isinstance(data[0], list) or isinstance(data[0], dict):
                i = 0
                for item in data:
                    self.nested_data(dwg, '|'.join([path, str(i)]), item, group, color, text)
                    i+=1



    def add_squares(self, dwg, table_name, data_type):
         # *** squares ***
        squareGroup = dwg.g(id='squareGroup') 
        for zoneName, zone in self.coordinates[data_type].items():
            randomColor = "rgb({},{},{})".format(randint(0,255), randint(0,255), randint(0,255))
            if table_name in zone:
                self.nested_data(dwg, '|'.join([data_type, zoneName, table_name]), zone[table_name], squareGroup, randomColor, zoneName)
                    
        dwg.add(squareGroup)


    def add_squares_for_mouse_tracking(self, dwg, data_type, table_name):
         # *** squares ***
        squareGroup = dwg.g(id='squareGroup') 
        for zoneName, zones in self.coordinates[data_type][table_name].items():
            randomColor = "rgb({},{},{})".format(randint(0,255), randint(0,255), randint(0,255))
            i = 0
            for zone in zones:
                self.nested_data(dwg, '|'.join([data_type, table_name, zoneName, str(i)]), zone, squareGroup, randomColor, zoneName)
                i+=1
        dwg.add(squareGroup)


    def table_to_file(self, table_name, data_type):
        height, width = (str(s)+'px' for s in [100,100])
        file = 'templates/'+data_type+'_'+table_name+'.svg'
        dwg = svgwrite.Drawing(filename=file, size=(width, height))
        self.addBackground(dwg, table_name)

        if data_type == 'screen_scraping':
            self.add_squares(dwg, table_name, data_type)
        elif data_type == 'mouse_mover':
            self.add_squares_for_mouse_tracking(dwg, data_type, table_name)
        
        dwg.save()
        print(file+' created')




if __name__=='__main__':
    parser = argparse.ArgumentParser(description='creates .svg files from coordinates data, add background to scraping/mouse elements, so you can edit the .svg file after.')
    
    args = vars(parser.parse_args())

    svgCreator = SVGCreator('../coordinates.json')

    for table_name in ['PP','SN','PS','PS2']:

        corner = CornerFinder.findTopLeftCorner('../pics/'+table_name+'/topleft.png', 'backgrounds/'+table_name+'.png')
        if corner:
            svgCreator.setCorner(corner)

            for svg_file_type in ['screen_scraping', 'mouse_mover']:
                svgCreator.table_to_file(table_name, svg_file_type)
        else:
            print('corner not found for table '+table_name)