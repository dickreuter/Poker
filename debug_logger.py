import logging
import sys
class debug_logger(object):
    def start_logger(self):
        logger = logging.getLogger('Poker')
        logger.setLevel(logging.DEBUG)
        fh = logging.handlers.RotatingFileHandler('pokerprogram.log', maxBytes=1000000, backupCount=2)
        fh.setLevel(logging.DEBUG)
        er = logging.handlers.RotatingFileHandler('errors.log', maxBytes=1000000, backupCount=2)
        er.setLevel(logging.WARNING)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.ERROR)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        er.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(fh)
        logger.addHandler(ch)
        logger.addHandler(er)
        return logger