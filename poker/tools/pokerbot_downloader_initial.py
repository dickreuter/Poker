import requests
import sys
import subprocess
from pymongo import MongoClient


class UpdateChecker():
    def __init__(self):
        self.mongoclient = MongoClient('mongodb://guest:donald@dickreuter.com:27017/POKER')
        self.mongodb = self.mongoclient.POKER

    def downloader(self):
        self.file_name = "Pokerbot_installer.exe"
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
            self.mongodb.close()
            sys.exit()

if __name__ == '__main__':
    u=UpdateChecker()
    u.check_update(0)