conda activate poker_venv
pyinstaller main.spec
cp coordinates.txt dist
cp icon.ico dist
cp -R pics/ dist/
mkdir dist/log
mkdir dist/log/screenshots
mkdir dist/decisionmaker
cp decisionmaker/preflop.xlsx dist/decisionmaker/
cp config.ini dist
makensis -V3 DeepMindPokerbot.nsi
