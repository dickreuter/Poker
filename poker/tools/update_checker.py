import subprocess
import sys

import requests

from poker.tools.helper import get_config

# pylint: disable=unused-variable,missing-function-docstring,missing-class-docstring,invalid-name,missing-timeout

config = get_config()
URL = config.config.get('main', 'db')


class UpdateChecker:
    def __init__(self):
        self.preflop_url = ''
        self.preflop_url_backup = 'decisionmaker/preflop.xlsx'
        self.file_name = "Pokerbot_installer.exe"
        self.dl_link = ""

    def downloader(self):
        with open(self.file_name, "wb") as f:
            print("Downloading %s" % self.file_name)
            response = requests.get(self.dl_link, stream=True)
            total_length = response.headers.get('content-length')

            if total_length is None:  # no content length header
                f.write(response.content)
            else:
                dl = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    done = int(50 * dl / total_length)
                    sys.stdout.write("\r[%s%s]" %
                                     ('=' * done, ' ' * (50 - done)))
                    sys.stdout.flush()

    def check_update(self, version):
        c = requests.post(URL + "get_internal").json()[0]
        current_version = c['current_version']
        self.dl_link = c['dl']
        latest_updates = c['latest_updates']

        if current_version > version:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                print("Downloading latest version of the DeeperMind Pokerbot...")
                print("\n")
                print("Version changes:")
                for latest_update in latest_updates:
                    print("* " + latest_update)
                print("\n")
                self.downloader()
                subprocess.call(["start", self.file_name], shell=True)
            else:
                print(
                    "Please get the latest version by either updating your repo or by downloading the latest binaries. "
                    "\nThis version is out of date and may not work correcly or you may be missing important updates"
                    " to ensure the bot plays the best possible strategy.")
            sys.exit()

    def get_preflop_sheet_url(self):
        c = requests.post(URL + "get_internal").json()[0]
        self.preflop_url = c['preflop_url']
        return self.preflop_url, self.preflop_url_backup
