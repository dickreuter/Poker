cd poker
source activate poker35_venv
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
cp config.ini dist/main
makensis -V3 DeepMindPokerbot.nsi
