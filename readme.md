## Welcome to Nicolas Dickreuter's Python Pokerbot

This pokerbot plays automatically on Pokerstars and Partypoker. It works with image recognition, montecarlo simulation and a basic genetic algorithm. The mouse is moved automatically and the bot can play for hours. Captchas in Partypoker are sent to deathbycaptcha which has somebody resolve them usually within 15 seconds.

![](http://www.dickreuter.com/poker_fullscreen.png)

### Setup:
Download the Pokerstars or Partypoker software and run it in Virtualbox. The Pokerbot needs to be run outside the Virtual Machine to avoid detection.

### Dependencies:
* OpenCV (for image template recognition)
* Pytesseract (for OCR recognition of names and numbers)
* Pandas
* Matplotlib
* Tkinter (to be replaced with Pyside)
* Pillow
* Numpy

### Files:
* **Poker.py**: Main file containing most of the decision process
* **Captcha_manager.py:** If a captcha appears it ends a picture to deathbycaptcha and sends the necessary
commands to Virtualbox to enter the solved captcha
* **Charts.py:** Generates charts with Matplotlib for the GUI
* **Curvefitting.py:** Helps to fit curves when two points and a curvature are given.
* **Genetic_Algorithm.py:** Genetic algorithm to self-improve parameters for decision making, stored in strategies.xml
* **Log_manager.py:** Managing the logging system
* **Montecarlo_v3.py:** Native Python version of montecarlo simulation to calculate winning probabilities
* **Montecarlo_v4.py:** Pure matrix Numpy version of the montecarlo simulation to get winning probabilities of given hands (currently under construction)

### The decision making process
The decision is made by the DecisionMaker class in Poker.py. A variety of factors are taken into consideration:
* Equity (winning probability), which is calculated by Montecarlo_v3.py (will be replaced with a faster numpy-only version in Montecarlo_v4.py)
* Equity and minimum call/bet value need to be on the left of the corresponding curve in order for the bot not to fold
* Various other factors, such as behaviour in the previous round are taken into consideration

### The genetic algorithm
![](http://www.dickreuter.com/poker_charts.png)
After a number of hands (usually 250 or more) the genetic algorithm analyses the stacked barplot below. 
The below charts show 4 stages: pre-flop, flop, turn and river. Each stage has two bars: $wins and $losses. 
When it finds that calling or betting is too aggressive for certain stages, the parameters for the curve that is used to decide whether to fold, call or bet, are adjusted in strategies.xml (through minimum required equity and the curvature). For example we can see that the call winnings at the turn are slightly less than the call losses, which means the bot should probably be slightly less aggressive at that stage, even more so at the River where all calls appear to end up in losses. On the other hand, bets appear to work very well, they could potentially be even more aggressive.
