cd poker
source activate poker
pyinstaller main.spec
mkdir dist
mkdir dist/main/
mkdir dist/main/log
mkdir dist/main/log/screenshots
mkdir dist/main/decisionmaker
mkdir dist/main/card_recognition
cp coordinates.txt dist/main
cp icon.ico dist/main
cp -R pics/ dist/main/
cp decisionmaker/preflop.xlsx dist/main/decisionmaker/
cp card_recognition/model.h5 dist/main/card_recognition/
cp card_recognition/model.json dist/main/card_recognition/
cp card_recognition/model_classes.json dist/main/card_recognition/
cp config_default.ini dist/main/config.ini
makensis -V3 DeepMindPokerbot.nsi
