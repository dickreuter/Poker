# Deep mind pokerbot for pokerstars and partypoker

Hi,
I will try to improve the reading of the values. It will no longer be necessary to define coordinates.txt exactly. It is enough a generous range around the value. For this, I have extracted the numbers individually for cv2 as .png. The whole thing I have adapted only for PartyPoker.




Welcome to Nicolas Dickreuter's Python Pokerbot

Please note that the table scraping needs updating as the layouts have 
changed on both pokerstars and partypoker. Also, to train the bot I have started a new project here:
https://github.com/dickreuter/neuron_poker. The goal is to train agents by
playing against each other. Please contribute by creating a new Agent.

![alt text](https://github.com/dickreuter/Poker/raw/master/wiki/fullscreen1.png?raw=True)

This pokerbot plays automatically on Pokerstars and Partypoker. 
It works with image recognition, montecarlo simulation and a basic genetic algorithm. 
The mouse is moved automatically and the bot can play for hours. T

he binary installer can be downloaded from here: 
https://sourceforge.net/projects/partypoker-pokerstars-pokerbot/. It will automatically download the latest version of the bot.

You are welcome to contribute to this project in any shape or form 
(improving the software, doing data analysis, improving the GUI (based on Qt5 designer)). 
You can create an anaconda virtual environment with the 

`conda env create -f environment.yml -n poker_venv`.

### Setup instructions, how to get started:
https://github.com/dickreuter/Poker/wiki/Setup-instructions

### How and what to contribute:
https://github.com/dickreuter/Poker/projects
https://github.com/dickreuter/Poker/wiki/How-to-use-Git

### Strategies
The bot has currently been tested with partypoker Supersonic3 table and should also work 
with 6 player zoom poker on pokerstars. Fake money tables are not supported.
For a start please read the setup instructions.

To get more information on how to adjust the strategies, please read this:
https://github.com/dickreuter/Poker/wiki/Strategies-and-making-the-decision
