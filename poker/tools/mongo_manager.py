import base64
import io
import json
import logging

import pandas as pd
import requests
from PIL import Image
from fastapi.encoders import jsonable_encoder
from requests.exceptions import JSONDecodeError

from poker.tools.helper import COMPUTER_NAME, get_config, get_dir
from poker.tools.singleton import Singleton

TABLES_COLLECTION = 'tables'

log = logging.getLogger(__name__)

config = get_config()
URL = config.config.get('main', 'db')


class MongoManager(metaclass=Singleton):
    """Single class to manage interaction with mongodb"""

    def __init__(self):
        """Initialize connection as singleton"""
        self.login = config.config.get('main', 'login')
        self.password = config.config.get('main', 'password')

    def save_image(self, table_name, label, image):
        """
        save market image in mongodb

        Args:
            table_name: str
            label: str
            image: byte

        """
        encoded = jsonable_encoder(image, custom_encoder={
            bytes: lambda v: base64.b64encode(v).decode('utf-8')})

        response = requests.post(URL + "update_table_image", json={'pil_image': encoded,
                                                                   'label': label,
                                                                   'table_name': table_name}).json()

    def update_table_image(self, pil_image, label, table_name):
        """update table image"""
        img_byte_array = io.BytesIO()
        pil_image.save(img_byte_array, format='PNG')
        binary_image = img_byte_array.getvalue()
        encoded = jsonable_encoder(binary_image, custom_encoder={
            bytes: lambda v: base64.b64encode(v).decode('utf-8')})
        response = requests.post(URL + "update_table_image", json={'pil_image': encoded,
                                                                   'label': label,
                                                                   'table_name': table_name}).json()
        log.info(response)
        return True

    def update_state(self, state, label, table_name):
        """update table image"""
        response = requests.post(URL + "update_state", params={'state': state,
                                                               'label': label,
                                                               'table_name': table_name}).json()
        log.info(response)
        return True

    def update_tensorflow_model(self, table_name: str, hdf5_file: bytes, model_str: str, class_mapping: str):
        response = requests.post(URL + "update_tensorflow_model",
                                 files={'hdf5_file': hdf5_file},
                                 data={'model_str': model_str,
                                       'class_mapping': class_mapping,
                                       'table_name': table_name
                                       }
                                 )
        return response

    def load_table_nn_weights(self, table_name: str):
        log.info("Downloading neural network weights for card recognition with tolerance...")
        try:
            weights_str = requests.post(URL + "get_tensorflow_weights", params={'table_name': table_name}).json()
            weights = base64.b64decode(weights_str)
        except Exception as e:
            log.error(f"No Trained Neural Network found. The cards need to be trained first. {e}")
            return

        with open(get_dir('codebase') + '/loaded_model.h5', 'wb') as fh:
            fh.write(weights)
        log.info("Download complete")

    def load_table_image(self, image_name, table_name):
        """load table image"""
        image = requests.post(URL + "load_table_image", params={'image_name': image_name,
                                                                'table_name': table_name}).json()
        loaded_image = Image.open(io.BytesIO(base64.b64decode(image)))
        return loaded_image

    def get_table(self, table_name):
        """
        get full table structure, pictures, cards and coordinates

        Args:
            table_name: str

        Returns: dict

        """
        try:
            table = requests.post(
                URL + "get_table", params={'table_name': table_name}).json()
        except IndexError:
            raise RuntimeError("No table found for given name.")
        except JSONDecodeError:
            raise RuntimeError("JSONDecodeError: Most likely this table has using neural network enabled" \
                               "but no neural network has been trained yet. Either train a neural network" \
                               "for this table, or untick the use neural network checkbox for the given table.")

        table_converted = {}
        for key, value in table.items():
            try:
                if isinstance(value, (dict, int, list, float)):
                    table_converted[key] = value
                elif value[0:2] == 'iV':
                    table_converted[key] = base64.b64decode(value)
                else:
                    table_converted[key] = value
            except TypeError:
                pass
            
        return table_converted

    def get_table_owner(self, table_name):
        """
        get owner of a table

        Args:
            table_name: str

        Returns: dict

        """
        owner = requests.post(URL + "get_table_owner",
                              params={'table_name': table_name}).json()
        return owner

    def get_available_tables(self, computer_name):
        """
        Get available tables

        Returns: list

        """
        tables = requests.post(URL + "get_available_tables",
                               params={'computer_name': computer_name}).json()
        return tables

    def increment_plays(self, table_name):
        requests.post(URL + "increment_plays",
                      params={'table_name': table_name})

    def get_rounds(self, game_id):
        """
        Find latest rounds

        Args:
            game_id: str

        Returns:
            rounds of current hand

        """
        output = requests.post(
            URL + "get_rounds", params={'game_id': game_id}).json()
        return output

    def create_new_table(self, table_name):
        """
        Create a new table entry

        Args:
            table_name: str

        """
        resp = requests.post(URL + "create_new_table", params={'table_name': table_name,
                                                               'computer_name': COMPUTER_NAME})
        return resp

    def create_new_table_from_old(self, table_name, old_table_name):
        """
        Create a new table entry

        Args:
            table_name: str
            old_table_name: str

        """
        resp = requests.post(URL + "create_new_table_from_old", params={'table_name': table_name,
                                                                        'old_table_name': old_table_name,
                                                                        'computer_name': COMPUTER_NAME}).json()
        return resp

    def save_coordinates(self, table_name, label, coordinates_dict):
        """Save coordinates for a given label for a given table"""
        requests.post(URL + "save_coordinates", params={'table_name': table_name,
                                                        'label': label,
                                                        'coordinates_dict': json.dumps(coordinates_dict)})
        log.info("Coordinates saved")

    def delete_table(self, table_name, owner):
        """Delete a table"""
        requests.post(URL + "delete_table", params={'table_name': table_name,
                                                    'owner': owner})

    def get_top_strategies(self):
        response = requests.post(
            URL + "get_top_strategies").json()
        return pd.DataFrame(json.loads(response))
