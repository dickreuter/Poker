import io
import logging

import pandas as pd
from PIL import Image
from pymongo import MongoClient

from poker.tools.helper import COMPUTER_NAME
from poker.tools.singleton import Singleton

TABLES_COLLECTION = 'tables'
log = logging.getLogger(__name__)


class MongoManager(metaclass=Singleton):
    """Single class to manage interaction with mongodb"""

    def __init__(self):
        """Initialize connection as singleton"""
        self.client = MongoClient('mongodb://neuron_poker:donald@dickreuter.com/neuron_poker')
        self.db = self.client['neuron_poker']

    def upload_dataframe(self, df, collection_name):
        """updload df to mongodb"""
        self.db[collection_name].insert_many(df.to_dict('records'))

    def get_dataframe(self, collection_name, max_rows=0):
        """download dict from mongodb and convert to dataframe"""
        df = pd.DataFrame(list(self.db[collection_name].find().limit(max_rows)))
        return df

    def update_table_image(self, pil_image, label, table_name):
        """update table image"""
        img_byte_array = io.BytesIO()
        pil_image.save(img_byte_array, format='PNG')
        binary_image = img_byte_array.getvalue()
        self.db[TABLES_COLLECTION].update({'table_name': table_name},
                                          {'$set': {label: binary_image}}, upsert=True)

    def load_table_image(self, image_name, table_name):
        """load table image"""
        log.debug("started")

        try:
            table_dict = list(self.db[TABLES_COLLECTION].find({'table_name': table_name}, {"_id": 0}))[0]
            loaded_image = Image.open(io.BytesIO(table_dict[image_name]))
            loaded_image.save('log/pics/loaded_image.png')
        except:
            raise RuntimeError("No image found for given name.")
        log.debug("finished")
        return loaded_image

    def get_table(self, table_name):
        """
        get full table structure, pictures, cards and coordinates

        Args:
            table_name: str

        Returns: dict

        """
        try:
            table = list(self.db[TABLES_COLLECTION].find({'table_name': table_name}, {"_id": 0}))[0]
        except IndexError:
            raise RuntimeError("No table found for given name.")
        return table

    def get_table_owner(self, table_name):
        """
        get owner of a table

        Args:
            table_name: str

        Returns: dict

        """
        table = list(self.db[TABLES_COLLECTION].find({'table_name': table_name}, {"_owner": 1}))
        return table[0]['_owner']

    def get_available_tables(self, computer_name):
        """
        Get available tables

        Returns: list

        """
        tables = list(self.db[TABLES_COLLECTION].distinct('table_name',
                                                          {"$or": [{"_owner": computer_name},
                                                                   {"_plays": {"$gte": 1}}]}))
        return tables

    def increment_plays(self, table_name):
        table = list(self.db[TABLES_COLLECTION].find({'table_name': table_name}, {"_plays": 1}))
        try:
            new_plays = table[0]['_plays'] + 1
        except:
            new_plays = 1
        self.db[TABLES_COLLECTION].update({'table_name': table_name},
                                          {'$set': {"_plays": new_plays}})

    def find(self, collection, search_dict):
        """
        Find entry in mongodb

        Args:
            collection: str
            search_dict: dict

        Returns:

        """
        output = self.db[collection].find(search_dict)
        return output

    def save_image(self, table_name, label, image):
        """
        save market image in mongodb

        Args:
            table_name: str
            label: str
            image: byte

        """
        self.db[TABLES_COLLECTION].update({'table_name': table_name},
                                          {'$set': {label: image}}, upsert=True)

    def create_new_table(self, table_name):
        """
        Create a new table entry

        Args:
            table_name: str

        """
        if table_name == "":
            return False
        if table_name in self.available_tables():
            return False
        self.db[TABLES_COLLECTION].update({'table_name': table_name},
                                          {'$set': {"_owner": COMPUTER_NAME}}, upsert=True)
        return True

    def create_new_table_from_old(self, table_name, old_table_name):
        """
        Create a new table entry

        Args:
            table_name: str
            old_table_name: str

        """
        if table_name == "":
            return False
        if table_name in self.available_tables():
            return False
        dic = self.get_table(old_table_name)
        dic['_owner'] = COMPUTER_NAME
        dic['_plays'] = 0
        dic['table_name'] = table_name
        self.db[TABLES_COLLECTION].insert_one(dic)
        return True

    def save_coordinates(self, table_name, label, coordinates_dict):
        """Save coordinates for a given label for a given table"""
        log.info(f"Saving to mongodb.... {coordinates_dict}")
        self.db[TABLES_COLLECTION].update({'table_name': table_name},
                                          {'$set': {label: coordinates_dict}}, upsert=True)
        log.info("Coordinates saved")

    def available_tables(self):
        """Available tables"""
        return self.db[TABLES_COLLECTION].distinct("table_name")

    def delete_table(self, table_name):
        """Delete a table"""
        dic = {'table_name': table_name}
        self.db[TABLES_COLLECTION].delete_one(dic)
