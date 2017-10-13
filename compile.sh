cd poker
source activate poker35_venv
pyinstaller main.spec
cp coordinates.txt dist
cp icon.ico dist
cp -R pics/ dist/
mkdir dist/log
mkdir dist/log/screenshots
mkdir dist/decisionmaker
mkdir dist/card_recognition
cp decisionmaker/preflop.xlsx dist/decisionmaker/
cp card_recognition/model.h5 dist/card_recognition/
cp card_recognition/model.json dist/card_recognition/
cp card_recognition/model_classes.json dist/card_recognition/
cp config.ini dist
makensis -V3 DeepMindPokerbot.nsi
