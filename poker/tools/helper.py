"""Helper functions."""

import datetime
import logging
import multiprocessing
import os
import pickle
import socket
import sys
import traceback
import webbrowser
from collections.abc import Iterable
from configparser import ConfigParser, ExtendedInterpolation
from logging import handlers

import pandas as pd
import requests

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    codebase = os.path.abspath(os.path.join(__file__, '..', '..', '..'))
else:
    codebase = os.path.abspath(os.path.join(__file__, '..', '..'))

log = logging.getLogger(__name__)

# check if os is windows or mac
IS_WINDOWS = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'

COMPUTER_NAME = socket.gethostname()


ON_CI = os.environ.get('ENV') == 'CI'


class Singleton(type):
    """
    Singleton Metaclass.

    Objects are only instantiated once and saved in the _instances dict if a class references
    to this metaclass.

    """

    _instances = {}

    # called at instantiation of an object that uses this metaclass
    def __call__(cls, *args, **kwargs):
        """Is called at instantiation of a class that refers to this metaclass."""
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @staticmethod
    def delete(class_name):
        """Delete an instancee of a singleton class."""
        if class_name in class_name._instances:  # pylint: disable=protected-access
            del class_name._instances[class_name]  # pylint: disable=protected-access


class CustomConfigParser():
    """
    Singleton class that wraps the ConfigParser to make sure it's only loaded once.

    The first time a config filename override will be considered. After that
    the parameter is irrelevant as the same config object will be returned.

    """

    def __init__(self, config_override_filename=None):
        """Load the configuration (usually config.ini)."""
        if config_override_filename and not os.path.isfile(config_override_filename):
            raise ValueError("Unable to find config file {}".format(
                config_override_filename))

        main_file = os.path.join(get_dir('codebase'), 'config.ini')

        self.config = ConfigParser(interpolation=ExtendedInterpolation())
        self.config.optionxform = str  # enforce case sensitivity on key

        if config_override_filename:  # custom config
            self.config.read([main_file, config_override_filename])
        else:  # no custom file
            self.config.read(main_file)

    def update_file(self):
        """write back to the config file"""
        main_file = os.path.join(get_dir('codebase'), 'config.ini')
        with open(main_file, 'w') as configfile:
            self.config.write(configfile)


def get_config():
    """Public accessor for config file."""
    return CustomConfigParser(os.path.join(get_dir('codebase'), 'config.ini'))


def init_logger(screenlevel, filename=None, logdir=None, modulename=''):
    """
    Initialize Logger.

    Args:
        screenlevel (logging): logging.INFO or logging.DEBUG
        filename (str): filename (without .log)
        logdir (str): directory name for log
        modulename (str): project name default

    """
    # for all other modules just use log = logging.getLogger(__name__)
    try:
        if not os.path.exists(logdir):
            os.makedirs(logdir)
    except OSError:
        print(f"Creation of the directory '{logdir}' failed")
        exit(1)
    else:
        print(f"Successfully created the directory '{logdir}' ")

    pics_path = "log/pics"
    try:
        if not os.path.exists(pics_path):
            os.makedirs(pics_path)
    except OSError:
        print(f"Creation of the directory '{pics_path}' failed")
        exit(1)
    else:
        print(f"Successfully created the directory '{pics_path}' ")

    root = logging.getLogger()
    [root.removeHandler(rh) for rh in root.handlers]  # pylint: disable=W0106
    [root.removeFilter(rf) for rf in root.filters]  # pylint: disable=W0106

    root = logging.getLogger('')
    root.setLevel(logging.WARNING)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(screenlevel)
    if filename and not filename == 'None':
        filename = filename.replace(
            "{date}", datetime.date.today().strftime("%Y%m%d"))
        all_logs_filename = os.path.join(logdir, filename + '.log')
        error_filename = os.path.join(logdir, filename + '_errors.log')
        info_filename = os.path.join(logdir, filename + '_info.log')

        print("Saving log file to: {}".format(all_logs_filename))
        print("Saving info file to: {}".format(info_filename))
        print("Saving error only file to: {}".format(error_filename))

        file_handler2 = handlers.RotatingFileHandler(
            all_logs_filename, maxBytes=300000, backupCount=20)
        file_handler2.setLevel(logging.DEBUG)

        error_handler = handlers.RotatingFileHandler(
            error_filename, maxBytes=300000, backupCount=20)
        error_handler.setLevel(logging.WARNING)

        info_handler = handlers.RotatingFileHandler(
            info_filename, maxBytes=30000000, backupCount=100)
        info_handler.setLevel(logging.INFO)

        # formatter when using --log command line and writing log to a file
        file_handler2.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(lineno)d - %(message)s'))
        error_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(lineno)d - %(message)s'))
        info_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(lineno)d - %(message)s'))

        # root.addHandler(fh)
        root.addHandler(file_handler2)
        root.addHandler(error_handler)
        root.addHandler(info_handler)

    # screen output formatter
    stream_handler.setFormatter(
        logging.Formatter('%(levelname)s - %(message)s'))
    root.addHandler(stream_handler)

    mainlogger = logging.getLogger(modulename)
    mainlogger.setLevel(logging.DEBUG)

    # pd.set_option('display.height', 1000)  # pd.set_option('display.max_rows', 500)  # pd.set_option('display.max_columns', 500)  # pd.set_option('display.width', 1000)


def get_dir(*paths):
    """
    Retrieve path (for subpath use multiple arguments).

    1. path from config file under Files section (relative to staging  folder), or
    2. 'codebase' for codebase base directory, or
    3. if neither of the above, custom directory relative to codebase

    """
    if paths[0] == 'codebase':  # pylint: disable=no-else-return
        return codebase
    else:
        # check if entry in config.ini
        try:
            config = get_config()
            specified_path = config.config.get("Files", paths[0])
            if len(paths) > 1:
                specified_path = os.path.join(specified_path, *paths[1:])
            thirdparty_dir = config.config.get('Thirdparty', 'thirdparty_dir')
            full_path = os.path.abspath(os.path.join(
                codebase, thirdparty_dir, specified_path))
            return full_path
        except:  # pylint: disable=bare-except
            # otherwise just return absolute path in codebase
            # if path has multiple entries
            return os.path.abspath(os.path.join(codebase, *paths))


def exception_hook(*exc_info):
    """Catches all unhandled exceptions."""
    # Print the error and traceback
    print("--- exception hook ----")
    text = "".join(traceback.format_exception(
        *exc_info))  # pylint: disable=E1120
    log.error("Unhandled exception: %s", text)


def flatten(items):
    """Yield items from any nested iterable; see Reference."""
    for x in items:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            for sub_x in flatten(x):
                yield sub_x
        else:
            yield x


def get_multiprocessing_config():
    """
    Load multiprocessing configuration from config and read amount of cores.

    Maximum number of cores that are used is max(1, min(cores, num_cpus - 1))

    Returns:
        parallel (boolean): if multiprocessing is True or False
        cores (int): Amount of cores to use

    """
    config = get_config()
    parallel = config.getboolean('MultiThreading', 'parallel')
    cores = config.getint('MultiThreading', 'cores')
    num_cpus = multiprocessing.cpu_count()
    cores = max(1, min(cores, num_cpus - 1))
    return parallel, cores


def multi_threading(pool_fn, pool_args, disable_multiprocessing=False, dataframe_mode=False):
    """
    Wrap multi threading for external c++ calls.

    Args:
        pool_fn: any partial function that takes a single argument. For multi argument functions reduce it with partial
                 to a single argument. The first argument needs to be the list over which the pool can iterate.
        pool_args (list): list of any type that is passed into the pool.map or map.
        disable_multiprocessing (bool): if set to True, multiprocessing will not be applied, regardless of config.ini entry.
        dataframe_mode (bool): set to true to use starmap, so pd.concat can be used on results,
                               if set to false, the result will be a list of list.

    Returns:
        res (list): Result of multiprocessing. Len of results will match len of the list of the pool_args

    """
    from multiprocessing.pool import ThreadPool
    parallel, cores = get_multiprocessing_config()
    log.debug("Start with parallel={} and cores={}, queue size={}".format(
        parallel, cores, len(pool_args)))
    if parallel and not disable_multiprocessing:
        threadpool = ThreadPool(cores)
        if dataframe_mode:
            res = threadpool.starmap(pool_fn, pool_args)
        else:
            res = threadpool.map(pool_fn, pool_args)
    else:
        res = [pool_fn(x) for x in pool_args]
    assert len(res) == len(pool_args)
    log.debug("Completed.")
    return res


def memory_cache(func):
    """Memoisation decorator for functions taking one or more arguments."""

    class Memoise:  # pylint: disable=too-few-public-methods
        """A memoise class class."""

        cache = {}

        def __init__(self, func_):
            self.func = func_

        def __call__(self, *args, **kwargs):
            """Call to function with cached decorator."""
            try:
                args_tuple = _keys_to_tuple(args, kwargs)
                try:
                    res = self.cache[self.func.__name__, args_tuple]
                    log.debug(
                        "+++ Using memory cacheed item for {} function +++ ".format(self.func.__name__))
                    return res
                except KeyError:
                    log.debug(
                        "--- Caching item for {} function in memory ---".format(self.func.__name__))
                    self.cache[self.func.__name__,
                               args_tuple] = res = self.func(*args, **kwargs)
                    return res
            except Exception as err:  # pylint: disable=broad-except
                raise RuntimeError(
                    "Error calling cached function {} ".format(self.func.__name__), err)

    return Memoise(func)


def _keys_to_tuple(args, kwargs):
    """Ensure everything is hashable."""
    compiled_args = []
    for arg in args:
        if isinstance(arg, (pd.DataFrame, dict)):
            compiled_args.append(pickle.dumps(arg))
        elif isinstance(arg, list):
            compiled_args.append(tuple(arg))
        else:
            compiled_args.append(arg)

    for k, v in sorted(kwargs.items()):
        compiled_args.append(k)
        compiled_args.append(v)
    return tuple(compiled_args)


def open_payment_link():
    config = get_config()
    URL = config.config.get('main', 'db')
    c = requests.post(URL + "get_internal").json()[0]
    payment_link = c['payment_link']
    webbrowser.open(payment_link, new=1)
