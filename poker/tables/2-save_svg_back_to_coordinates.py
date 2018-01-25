#!/usr/bin/env python

import xml.dom.minidom as minidom
import argparse 
import glob
import json
import numpy as np


class CoordinatesSaver():
    def __init__(self, coordinates_file):
        # get scraping/mouse data
        self.coordinates_file = coordinates_file
        with open(coordinates_file) as inf:
            self.coordinates = json.load(inf)


    def parents(self, node, parentType):
        foundNodes = []
        while node.parentNode:
            node = node.parentNode
            if node.nodeName == parentType:
                foundNodes.append(node)

        return foundNodes


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
        
        return [int(i) for i in coordinates]


    def computeNewValue(self, rectangle):
        # get rect coordinates
        
        # apply transformation matrixes
        coordinates = self.matrixTransform(rectangle)
        
        # return a dict with these coords
        var = {}
        var['x1'], var['y1'], var['x2'], var['y2'] = coordinates

        return var

    # browse data and sets a new leaf value
    def setCoordinatesValue(self, path, data, newValue, recursion):
        if recursion < len(path) :
            data[path[recursion]] = self.setCoordinatesValue(path, data[path[recursion]], newValue, recursion+1)
            return data
        else:
            # last recursion execution
            return newValue
            


    def saveRectangleInCoordinates(self, rectangle):
        dataPath = rectangle.getAttribute('class').split('|')
        dataPath = [int(dp) if all(i.isdigit() for i in dp) else dp for dp in dataPath]
        newValue = self.computeNewValue(rectangle)
        self.coordinates = self.setCoordinatesValue(dataPath, self.coordinates, newValue, 0)


    def gather(self, path):
        svgFiles = glob.glob(path)

        for file in svgFiles:
            daDom = minidom.parse(file)
            rectangles = daDom.getElementsByTagName("rect")

            for rectangle in rectangles:
                self.saveRectangleInCoordinates(rectangle)

    # save edited var into it's file
    def save(self):
        with open(self.coordinates_file, 'w+') as file:
            file.write(json.dumps(self.coordinates, indent=4))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description='creates coordinates.txt file from user edited .svg data.')
    
    args = vars(parser.parse_args())
    coordinates_path = '../coordinates.txt'
    cs = CoordinatesSaver(coordinates_path)
    cs.gather('./templates/*.svg')
    cs.save()
    print('SVG data saved to {} !'.format(coordinates_path))