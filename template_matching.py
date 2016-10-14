import cv2
import numpy as np
from PIL import Image,ImageGrab
from matplotlib import pyplot as plt

#img = cv2.imread('screenshot.png',0)
img = cv2.cvtColor(np.array(Image.open('tests/screenshot.6.png')), cv2.COLOR_BGR2RGB) # works with 0.02
#img = cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_BGR2RGB)
#img = cv2.imread('new_screenshot.png',0)
#img = cv2.cvtColor(np.array(Image.open('file1.png')), cv2.COLOR_BGR2RGB)
img2=img.copy()

#template = cv2.imread('pics/sn/3d.png',0)
#template = cv2.imread('new_3d.png',0)
#template = cv2.imread('pics/sn/3d.png',0)
template = cv2.cvtColor(np.array(Image.open('pics/SN/button.png')), cv2.COLOR_BGR2RGB)
#template = cv2.cvtColor(np.array(Image.open('3d.png')), cv2.COLOR_BGR2RGB)
#template = cv2.cvtColor(np.array(Image.open('pics/sn/3d.png')), cv2.COLOR_BGR2RGB)

# All the 6 methods for comparison in a list
methods = ['cv2.TM_SQDIFF_NORMED']

for meth in methods:
     img = img2.copy()
     method = eval(meth)

     # Apply template Matching
     res = cv2.matchTemplate(img,template,method)
     min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

     # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
     if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
         top_left = min_loc
     else:
         top_left = max_loc

     print (min_val)

     plt.subplot(121),plt.imshow(res,cmap = 'gray')
     plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
     plt.subplot(122),plt.imshow(img,cmap = 'gray')
     plt.title('Detected Point'), plt.xticks([]), plt.yticks([])
     plt.suptitle(meth)


     plt.show()