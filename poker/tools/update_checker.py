import subprocess
import sys

import requests
from pymongo import MongoClient


class UpdateChecker:
    def __init__(self):
        self.preflop_url = ''
        self.preflop_url_backup = 'decisionmaker/preflop.xlsx'
        self.file_name = "Pokerbot_installer.exe"
        self.dl_link = ""
        self.mongoclient = MongoClient('mongodb://neuron_poker:donald@dickreuter.com/neuron_poker')
        self.mongodb = self.mongoclient.neuron_poker

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
                    sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50 - done)))
                    sys.stdout.flush()

    def check_update(self, version):
        cursor = self.mongodb.internal.find()
        c = cursor.next()
        current_version = c['current_version']
        self.dl_link = c['dl']
        latest_updates = c['latest_updates']
        if current_version > version:
            print("Downloading latest version of the DeepMind Pokerbot...")
            print("\n")
            print("Version changes:")
            for latest_update in latest_updates:
                print("* " + latest_update)
            print("\n")
            self.downloader()
            subprocess.call(["start", self.file_name], shell=True)
            sys.exit()

    def get_preflop_sheet_url(self):
        cursor = self.mongodb.internal.find()
        c = cursor.next()
        self.preflop_url = c['preflop_url']
        return self.preflop_url, self.preflop_url_backup
