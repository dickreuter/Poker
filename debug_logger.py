import logging
import sys
class debug_logger(object):
    def start_logger(self):
        logger = logging.getLogger('Poker')
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler('pokerprogram.log')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(fh)
        logger.addHandler(ch)
        return logger