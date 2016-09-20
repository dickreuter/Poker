import cv2
from table_setup import Setup

s=Setup(topleftcorner_file = "pics/PS/topleft.png",
        screenshot_file = "pics/PS/cap4.PNG",
        output_file='checker.png')

with open('coordinates.txt', 'r') as inf:
    c = eval(inf.read())
    coo = c['screen_scraping']
table='PS2'

img = cv2.imread('checker.png',0)

for key,item in coo.items():
    try:
        for c in item[table]:
            try:
                print (c)
                cv2.rectangle(img,(c[0],c[1]), (c[2], c[3]),200)
            except:
                try:
                    cv2.rectangle(img, (c['x1'], c['y1']), (c['x2'], c['y2']), 200)
                except Exception as e:
                    print (e)


    except Exception as e:
        print (e)

cv2.imshow('img', img)
cv2.waitKey()