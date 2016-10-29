import logging, logging.handlers
import sys
class debug_logger(object):
    def start_logger(self,name):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL) # if you wanna see the old version, just change CRITICAL to DEBUG
        if not len(logger.handlers):
            fh = logging.handlers.RotatingFileHandler('log/pokerprogram.log', maxBytes=1000000, backupCount=10)
            fh.setLevel(logging.DEBUG)
            fh2 = logging.handlers.RotatingFileHandler('log/pokerprogram_info_only.log', maxBytes=1000000, backupCount=5)
            fh2.setLevel(logging.INFO)
            test = logging.handlers.RotatingFileHandler('log/test.log', maxBytes=1000000, backupCount=5)
            test.setLevel(logging.CRITICAL) # in log/test.log will all stuffs are saved. Critical has no effect, it is just to categorise the stuffs
            er = logging.handlers.RotatingFileHandler('log/errors.log', maxBytes=2000000, backupCount=2)
            er.setLevel(logging.WARNING)
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(1)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            fh2.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            er.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            ch.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(fh)
            logger.addHandler(fh2)
            logger.addHandler(ch)
            logger.addHandler(er)
            logger.addHandler(test)
        return logger