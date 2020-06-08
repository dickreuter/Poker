"""Pylint test."""

import logging
import os
import sys
from glob import glob

from pydocstyle import Error, check
from pydocstyle.cli import setup_stream_handlers, ReturnCode
from pydocstyle.config import ConfigurationParser, IllegalConfiguration
from pylint import lint
from pylint.reporters.text import TextReporter

from poker.tools.helper import get_dir

# pylint: disable=anomalous-backslash-in-string,too-few-public-methods,inconsistent-return-statements

log = logging.getLogger(__name__)
CODEBASE = get_dir('codebase')
REPOS = [name for name in os.listdir(CODEBASE) if os.path.isdir(name)]

FOLDERS = [name for name in os.listdir(CODEBASE) if
           os.path.isdir(os.path.join(CODEBASE, name)) and '.' not in name[0] and '_' not in name[0]]

LINT_EXTENSIONS = ['.py']

EXCLUDE_SUBFOLDERS = ['.idea', 'doc', 'mongodb-backup','mongodb-transfer2']

# To ignore specific rules, please disable it in your file or function,
# or (if given broad consensus) ignore it globally by adding an exception to .pylintrc.
# Full list of readable pylint message short-names can be found here:
# https://github.com/janjur/readable-pylint-messages

IGNORE_LIST = ["""\r\n""",  # part of final output
               "*************",  # part of final output
               "------------",  # part of final output
               "Your code has been rated at", "E           ",  # part of final output
               "Redefining built-in 'id'",  # exception as it seems never a problem
               "UPPER_CASE naming style (invalid-name)",
               "_ui_",
               "pymouse",
               """"log" doesn't conform to UPPER_CASE"""]

REPOSITORIES = list(set(FOLDERS) - set(EXCLUDE_SUBFOLDERS))


class _WritableOutput:
    """A simple class, supporting a write method to capture pylint output."""

    def __init__(self):
        self.content = []

    def write(self, string):
        """Write method to capture pylint output."""
        if string == '\n':
            return  # filter newlines
        self.content.append(string)


def test_pylint():
    """Test codebase for pylint errors."""
    files_to_check = get_relevant_files()
    log.info("{} changed files detected".format(len(files_to_check)))
    rcfile, reps = (os.path.join(CODEBASE, '.pylintrc'), files_to_check)

    pylint_args = ['--rcfile={}'.format(rcfile), ]
    log.info('applying pylint to repository {}'.format(reps))
    pylint_args += reps

    pylint_output = _WritableOutput()
    pylint_reporter = TextReporter(pylint_output)
    lint.Run(pylint_args, reporter=pylint_reporter, do_exit=False)

    pylint_outputs = pylint_output.content

    errors = []
    for output in pylint_outputs:
        if not any([i in output for i in IGNORE_LIST]):
            errors.append(output)
        if "Your code has been rated at" in output:
            print("\n" + output)

    if errors:
        raise AssertionError('{} Pylint errors found. '
                             'For quick resolution, consider running this test locally before you push. '
                             'Scroll down for hyperlinks to errors.\n{}'.format(len(errors), '\n'.join(errors)))


def get_relevant_files():
    """
    Get relevant changed files of current branch vs target branch.

    check_all_files (bool): get all files if true, get changed files since comparison commit

    Filenames are filtered:
       - Files need to be in lint_extensions
       - Files cannot be in the exclude_folders list

    Returns:
        list of str: changed files

    """
    filenames = [y for x in os.walk(get_dir('codebase')) for y in glob(os.path.join(x[0], '*.py'))]
    if os.name == 'nt':
        filenames = [filename.replace('/', """\\""") for filename in filenames]
    filenames = [filename for filename in filenames if filename]
    filenames = [filename for filename in filenames if os.path.splitext(filename)[1] in LINT_EXTENSIONS]
    filenames = [os.path.join(CODEBASE, filename) for filename in filenames]
    log.debug(filenames)

    return filenames


# nforce consistent docstrings as per https://www.python.org/dev/peps/pep-0257/.

log = logging.getLogger(__name__)
REPOSITORIES = ['dealer_engine', 'neuron_poker']

# --- please remove files here for enforcement ---

IGNORES = ['__init__.py']


def test_pydocstyle():
    """
    Docstring enforcement test.

    Please adjust the enforced_file list to enfoce the test in a file.
    To auto generate the correct format in intellij please make the following adjustments in your ide:
    Tools - Python Integrated Tools - Docstring format to google style.
    """
    # pass argv argument to pydocstyle via monkeypatch
    reps = [os.path.join(CODEBASE, rep) for rep in REPOSITORIES]

    sys.argv = ['test_pydocstyle'] + reps + [r"""--match=.*\.py"""]
    errors = run_pydocstyle()

    enforced_errors = [str(error) for error in errors]

    if enforced_errors:
        raise RuntimeError("Docstring test failed: \n{}".format('\n'.join(enforced_errors)))


def run_pydocstyle():
    """Adjust version of pydocstile to return detailed errors to the test."""
    log.setLevel(logging.DEBUG)
    conf = ConfigurationParser()
    setup_stream_handlers(conf.get_default_run_configuration())

    try:
        conf.parse()
    except IllegalConfiguration:
        return ReturnCode.invalid_options

    run_conf = conf.get_user_run_configuration()

    # Reset the logger according to the command line arguments
    setup_stream_handlers(run_conf)

    log.debug("starting in debug mode.")

    Error.explain = run_conf.explain
    Error.source = run_conf.source

    errors = []
    changed_files = get_relevant_files()

    if not changed_files:
        return []

    all_files = conf.get_files_to_check()
    all_files = [file for file in all_files if file[0] in changed_files]
    try:
        for filename, checked_codes, ignore_decorators in all_files:
            errors.extend(check((filename,), select=checked_codes, ignore_decorators=ignore_decorators))
    except IllegalConfiguration as error:
        # An illegal configuration file was found during file generation.
        log.error(error.args[0])
        return ReturnCode.invalid_options

    count = 0
    errors_final = []
    for err in errors:
        if hasattr(err, 'code') and not any(ignore in str(err) for ignore in IGNORES):
            sys.stdout.write('%s\n' % err)
            errors_final.append(err)
        count += 1
    return errors_final
