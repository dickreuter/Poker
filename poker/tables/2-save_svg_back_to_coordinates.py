#!/usr/bin/env python

import xml.dom.minidom as minidom
import argparse 
import json
from cornerFinder import CornerFinder
import numpy as np
import os


class CoordinatesSaver():
    def __init__(self, coordinates_file):
        # get scraping/mouse data
        self.coordinates_file = coordinates_file
        with open(coordinates_file) as inf:
            self.coordinates = json.load(inf)


    def setCorner(self,corner):
        self.topLeftCornerOffset = corner


    def parents(self, node, parentType):
        foundNodes = []
        while node.parentNode:
            node = node.parentNode
            if node.nodeName == parentType:
                foundNodes.append(node)

        return foundNodes


    # apply transformation matrixes, & translation if exists 
    def matrixTransform(self, rectangle):
        attributes = dict(rectangle.attributes.items())
        coordinates = [float(rectangle.getAttribute(t).split('px')[0]) for t in ['x','y','width', 'height']]

        # gets x2, y2 rather than width, height
        coordinates[2] += coordinates[0]
        coordinates[3] += coordinates[1]

        for groupNode in self.parents(rectangle, 'g'):
            groupNodeAttrs = dict(groupNode.attributes.items())
            if 'transform' in groupNodeAttrs.keys():
                if 'matrix' in groupNodeAttrs['transform']:
                    # x' = a*x + c*y + e 
                    # y' = b*x + d*y + f

                    transformMatrix = np.array(groupNode.getAttribute('transform').split('matrix(')[1].split(')')[0].split(','), dtype='float')
                    transformMatrix.shape = (3,2)

                    arrayBottom = np.array([0,0,1], dtype='float')
                    arrayBottom.shape = (1,3)

                    transformMatrix = np.append(np.matrix(transformMatrix).getT(), arrayBottom, axis=0)
                    
                    x1y1 = np.append(coordinates[:2], [1])
                    x2y2 = np.append(coordinates[2:4], [1])

                    x1y1 = np.dot(transformMatrix, x1y1)
                    x2y2 = np.dot(transformMatrix, x2y2)

                    coordinates[:2] = np.array(x1y1).reshape(-1,).tolist()[:2]
                    coordinates[2:4] = np.array(x2y2).reshape(-1,).tolist()[:2]

                elif 'translate' in groupNodeAttrs['transform']:
                    translate = np.array(groupNode.getAttribute('transform').split('translate(')[1].split(')')[0].split(','), dtype='float')
                    coordinates[0] += translate[0]
                    coordinates[2] += translate[0]
                    if len(translate) > 1:
                        coordinates[1] += translate[1]
                        coordinates[3] += translate[1]
                else:
                    print('DONT ROTATE OR *** THINGS, THAT\'S BAD')
        
        return coordinates


    def substract_top_left_corner_offset(self, coordinates):
        return  [
            coordinates[0] - self.topLeftCornerOffset[0],
            coordinates[1] - self.topLeftCornerOffset[1],
            coordinates[2] - self.topLeftCornerOffset[0],
            coordinates[3] - self.topLeftCornerOffset[1]
        ]


    # browse data and sets a new leaf value
    def setCoordinatesValue(self, path, data, newValue, recursion):
        if recursion < len(path) :
            data[path[recursion]] = self.setCoordinatesValue(path, data[path[recursion]], newValue, recursion+1)
            return data
        else:
            # last recursion execution
            data.update({
                'x1' : newValue[0],
                'y1' : newValue[1],
                'x2' : newValue[2],
                'y2' : newValue[3]
            })
            return data
            


    def saveRectangleInCoordinates(self, rectangle):
        dataPath = rectangle.getAttribute('class').split('|')
        dataPath = [int(dp) if all(i.isdigit() for i in dp) else dp for dp in dataPath]
        
        coo = self.matrixTransform(rectangle)
        if 'top_left_corner' not in dataPath:
            coo = self.substract_top_left_corner_offset(coo)

        self.coordinates = self.setCoordinatesValue(dataPath, self.coordinates, coo, 0)


    def parseFiles(self):
        for table_name in ['PP','SN','PS','PS2']:
            for svg_file_type in ['screen_scraping', 'mouse_mover']:
                template = 'templates/'+svg_file_type+'_'+table_name+'.svg'
               
                if os.path.exists(template):
                    daDom = minidom.parse(template)
                    corner = CornerFinder.findTopLeftCorner('../pics/'+table_name+'/topleft.png', 'backgrounds/'+table_name+'.png')
                    
                    if corner:
                        self.setCorner(corner)

                        for rectangle in daDom.getElementsByTagName("rect"):
                            self.saveRectangleInCoordinates(rectangle)


                        print (template+' coordinates appended to '+self.coordinates_file)
                    else:
                        print ('corner not found in '+template)
                else:
                    print(template+' doesn\'t exist and won\'t be appended to coordinates file')


    # save edited var into it's file
    def save(self):
        with open(self.coordinates_file, 'w+') as file:
            file.write(json.dumps(self.coordinates, indent=4))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description='creates coordinates.json file from user edited .svg data.')
    
    args = vars(parser.parse_args())
    coordinates_path = '../coordinates.json'
    cs = CoordinatesSaver(coordinates_path)
    cs.parseFiles()
    cs.save()