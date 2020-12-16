import io
import logging

import pandas as pd
from pymongo import MongoClient

from poker.tools.helper import COMPUTER_NAME
from poker.tools.singleton import Singleton

tables_collection = 'tables'
log = logging.getLogger(__name__)


class MongoManager(metaclass=Singleton):
    """Single class to manage interaction with mongodb"""

    def __init__(self):
        """Initialize connection as singleton"""
        self.client = MongoClient(f'mongodb://neuron_poker:donald@dickreuter.com/neuron_poker')
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
        self.db[tables_collection].update({'table_name': table_name},
                                          {'$set': {label: binary_image}}, upsert=True)

    def get_table(self, table_name):
        """
        get full table structure, pictures, cards and coordinates

        Args:
            table_name: str

        Returns: dict

        """
        try:
            table = list(self.db[tables_collection].find({'table_name': table_name}, {"_id": 0}))[0]
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
        table = list(self.db[tables_collection].find({'table_name': table_name}, {"_owner": 1}))
        return table[0]['_owner']

    def get_available_tables(self):
        """
        Get available tables

        Returns: list

        """
        tables = list(self.db[tables_collection].distinct('table_name'))
        return tables

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
        self.db[tables_collection].update({'table_name': table_name},
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
        self.db[tables_collection].update({'table_name': table_name},
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
        dic['table_name'] = table_name
        self.db[tables_collection].insert_one(dic)
        return True

    def save_coordinates(self, table_name, label, coordinates_dict):
        """Save coordinates for a given label for a given table"""
        log.info(f"Saving to mongodb.... {coordinates_dict}")
        self.db[tables_collection].update({'table_name': table_name},
                                          {'$set': {label: coordinates_dict}}, upsert=True)
        log.info("Coordinates saved")

    def available_tables(self):
        """Available tables"""
        return self.db[tables_collection].distinct("table_name")

    def delete_table(self, table_name):
        """Delete a table"""
        dic = {'table_name': table_name}
        self.db[tables_collection].delete_one(dic)
