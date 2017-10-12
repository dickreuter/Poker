
import os.path
from setuptools import setup, find_packages
import distutils.log

top_level_folder = 'poker'

distutils.log.set_verbosity(-1)  # Disable logging in disutils
distutils.log.set_verbosity(distutils.log.ERROR)  # Set DEBUG level

adj_packages = []
packages = find_packages(top_level_folder)

for package in packages:
    adj_packages.append(top_level_folder + '.' + package)

adj_packages.append(top_level_folder)

setup(
    name="pokerbot",
    author="Nicolas Dickreuter",
    description="pokerbot",
    zip_safe=False,
    packages=adj_packages,
    package_data={'': ['*.ini', '*.json', '*.csv', '*.h5', '*.xml']},
    entry_points={
        'console_scripts': [
            ['pokerbot = poker.main:run_poker',]
        ],
    }
)
