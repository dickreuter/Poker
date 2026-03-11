import logging
# for all other modules just use log = logging.getLogger(__name__)
import os
import sys
from logging import handlers  # pylint: disable=unused-import


def init_logger(screenlevel, filename):
    logdir = get_dir('log')
    root = logging.getLogger()
    _ = [root.removeHandler(rh) for rh in root.handlers]
    _ = [root.removeFilter(rf) for rf in root.filters]

    root = logging.getLogger('')
    root.setLevel(logging.WARNING)

    # fh = logging.handlers.RotatingFileHandler('log/betting.log', maxBytes=1000000, backupCount=10)
    # fh.setLevel(logging.DEBUG)
    fh2 = logging.handlers.RotatingFileHandler(os.path.join(logdir, filename + '.log'), maxBytes=300000, backupCount=20)
    fh2.setLevel(logging.INFO)
    er = logging.handlers.RotatingFileHandler(os.path.join(logdir, filename + '_errors.log'), maxBytes=300000,
                                              backupCount=20)
    er.setLevel(logging.WARNING)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(screenlevel)
    # fh.setFormatter(logging.Formatter('%(asctime)s - %(filename)s - %(levelname)s - %(message)s'))
    fh2.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s'))
    er.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s'))
    ch.setFormatter(logging.Formatter('%(filename)s - %(lineno)d - %(message)s'))

    # root.addHandler(fh)
    root.addHandler(fh2)
    root.addHandler(ch)
    root.addHandler(er)

    mainlogger = logging.getLogger('horse_racing')
    mainlogger.setLevel(logging.DEBUG)


def get_dir(path):
    codebase = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if path == 'codebase':
        return codebase
    return os.path.join(codebase, path)
