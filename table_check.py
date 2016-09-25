import cv2
from table_setup import Setup
screenshot_file="tests/691119677_PreFlop_0.png"
output_file='log/screenshots/table_check.png'
table='PP'

s=Setup(topleftcorner_file = "pics/PP/topleft.png",
        screenshot_file = screenshot_file,
        output_file=output_file)

with open('coordinates.txt', 'r') as inf:
    c = eval(inf.read())
    coo = c['screen_scraping']


img = cv2.imread(output_file,0)

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