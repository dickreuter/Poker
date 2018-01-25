#!/usr/bin/env python

import cv2
import svgwrite
from random import randint
import argparse 
import json 



class SVGCreator():
    
    def __init__(self, coordinates_file):
        # get scraping/mouse data
        with open(coordinates_file) as inf:
            self.coordinates = json.load(inf)


    # cast int ==> 'int px' or [int, int] ==> ['intpx','intpx']
    def toPix(self, someNumber):
        if isinstance(someNumber, list):
            return (self.toPix(el) for el in someNumber)
        return str(int(someNumber))+'px'


    def beautifulRectangleElementWithNiceTextAtTheMiddle(self, dwg, coordinates, name, color, dataPath):
        x1, y1, x2, y2 = coordinates[:4]

        width, height = (x2-x1, y2-y1)
        fontHeight=12

        group = dwg.g(id=name.replace(" ", "__"))
        rect = dwg.rect(insert=self.toPix([x1, y1]), size=self.toPix([width, height]), fill=color, stroke='black')
        rect.update({'class':dataPath, 'fill-opacity':0.6})
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
        img = cv2.imread(backgroundImage, 0)
        if img is not None:
            height, width = (str(s)+'px' for s in img.shape[:2])
            dwg.update({'height':height, 'width':width})
            background = svgwrite.image.Image(pathRelativeToFile, insert=(0,0), size=(width, height))

            group = dwg.g(id='background')
            group.add(background)
            dwg.add(group)
            print(table_name+'.png added as background')
        else:
            print(table_name+'.png background doesn\'t exist ! Put your screenshot in poker/tables/backgrounds/'+table_name+'.png to help you design scraping svg templates')


    # creates a square element for each [x,y,x2,y2] leaf element
    def nested_data(self, dwg, path, data, group, color):
        if isinstance(data, dict) and len(data) > 0:
            values = list(data.values())
            
            # add dict leaf
            if isinstance(values[0], int) and len(values) >= 4:
                group.add(self.beautifulRectangleElementWithNiceTextAtTheMiddle(dwg, values[:4], path.split('|')[1], color, path))
            else:
                # thing nested in dict
                for key, val in data.items():
                    self.nested_data(dwg, '|'.join([path, key]), val, group, color)


        if isinstance(data, list) and len(data) > 0:
            # add list leaf
            if len(data) >= 4 and isinstance(data[0], int):
                group.add(self.beautifulRectangleElementWithNiceTextAtTheMiddle(dwg, data[:4], path.split('|')[1], color, path))

            # (dict or list) nested in list
            elif isinstance(data[0], list) or isinstance(data[0], dict):
                i = 0
                for item in data:
                    self.nested_data(dwg, '|'.join([path, str(i)]), item, group, color)
                    i+=1



    def add_squares(self, dwg, table_name, data_type):
         # *** squares ***
        squareGroup = dwg.g(id='squareGroup') 
        for zoneName, zone in self.coordinates[data_type].items():
            randomColor = "rgb({},{},{})".format(randint(0,255), randint(0,255), randint(0,255))
            if table_name in zone:
                self.nested_data(dwg, '|'.join([data_type, zoneName, table_name]), zone[table_name], squareGroup, randomColor)
                    
        dwg.add(squareGroup)

    def add_squares_for_mouse_tracking(self, dwg, data_type, table_name):
         # *** squares ***
        squareGroup = dwg.g(id='squareGroup') 
        for zonesName, zones in self.coordinates[data_type][table_name].items():
            randomColor = "rgb({},{},{})".format(randint(0,255), randint(0,255), randint(0,255))
            i = 0
            for tableZone in zones:
                if len(tableZone) > 5 and isinstance(tableZone[2], int):
                    tableZone[4:6] = [(x + y) for (x, y) in zip(tableZone[2:4], tableZone[4:6])]
                    squareGroup.add(self.beautifulRectangleElementWithNiceTextAtTheMiddle(dwg, tableZone[2:6], zonesName, randomColor, '|'.join([data_type, table_name, zonesName, str(i)])))
                    i += 1
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
        print(file+' saved')



if __name__=='__main__':
    parser = argparse.ArgumentParser(description='creates .svg files from coordinates data, add background to scraping/mouse elements, so you can edit the .svg file after.')
    
    args = vars(parser.parse_args())

    # top_left_corner_file="poker/pics/PS/topleft.png"
    svgCreator = SVGCreator('../coordinates.txt')

    for table_name in ['PP','SN','PS','PS2']:
        for svg_file_type in ['screen_scraping', 'mouse_mover']:
            svgCreator.table_to_file(table_name, svg_file_type)
