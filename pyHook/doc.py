import sys
from epydoc.cli import cli

# add default parameters to the command line
options = ['--html', '-o', 'doc', '--inheritance', 'listed']
sys.argv.extend(options)
# extend the command line to include the given files
files = ['__init__.py', 'HookManager.py']
sys.argv.extend(files)
cli()