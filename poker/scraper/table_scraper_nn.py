import base64
import io
import json
import logging
import os
import shutil

import cv2
import numpy as np
import requests
import tensorflow.keras.losses
from PIL import Image
from tensorflow.keras.callbacks import TensorBoard
from tensorflow.keras.constraints import MaxNorm
from tensorflow.keras.layers import Conv2D, MaxPooling2D
from tensorflow.keras.layers import Dropout, Flatten, Dense
from tensorflow.keras.models import Sequential, model_from_json
from tensorflow.keras.preprocessing.image import ImageDataGenerator, img_to_array
from tqdm import tqdm

from poker.tools.helper import get_dir
from poker.tools.mongo_manager import MongoManager

SCRAPER_DIR = get_dir('scraper')
TRAIN_FOLDER = "training_cards"
VALIDATE_FOLDER = "validate_cards"
TEST_FOLDER = "test_cards"

log = logging.getLogger(__name__)


def pil_to_cv2(img):
    return cv2.cvtColor(np.array(img), cv2.COLOR_BGR2RGB)


def binary_pil_to_cv2(img):
    return cv2.cvtColor(np.array(Image.open(io.BytesIO(img))), cv2.COLOR_BGR2RGB)


def adjust_colors(a, tol=120):  # tol - tolerance to decides on the "-ish" factor

    # define colors to be worked upon (red, green, black, white, blue)
    colors = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 0], [255, 255, 255], [0, 0, 255]])

    # Mask of all elements that are closest to one of the colors
    mask0 = np.isclose(a, colors[:, None, None, :], atol=tol).all(-1)

    # Select the valid elements for edit. Sets all nearish colors to exact ones
    out = np.where(mask0.any(0)[..., None], colors[mask0.argmax(0)], a)

    # Finally set all green to black
    out[(out == colors[1]).all(-1)] = colors[2]

    # Finally set all blue to red
    out[(out == colors[4]).all(-1)] = colors[0]
    return out.astype(np.uint8)


img_height = 50
img_width = 15


class CardNeuralNetwork():
    def __init__(self):
        pass

    def create_test_images(self):
        shutil.rmtree(TRAIN_FOLDER, ignore_errors=True)
        shutil.rmtree(VALIDATE_FOLDER, ignore_errors=True)
        shutil.rmtree(TEST_FOLDER, ignore_errors=True)

        log.info("Augmenting data with random pictures based on templates")

        datagen = ImageDataGenerator(
            rotation_range=10,
            width_shift_range=0.1,
            height_shift_range=0.1,
            shear_range=0.05,
            zoom_range=0.1,
            horizontal_flip=False,
            fill_mode='nearest')

        # mongo = MongoManager()
        # table_dict = mongo.get_table('GG Poker2')
        cards = {}
        table = requests.post('http://dickreuter.com:7777/' + "get_table", params={'table_name': 'GG Poker2'}).json()
        for key, value in table.items():
            if isinstance(value, (dict, int, list, float)):
                cards[key] = value
            elif value[0:2] == 'iV':
                cards[key] = base64.b64decode(value)
            else:
                cards[key] = value

        for folder in [TRAIN_FOLDER, VALIDATE_FOLDER, TEST_FOLDER]:
            card_ranks_original = '23456789TJQKA'
            original_suits = 'CDHS'

            namelist = []
            for c in card_ranks_original:
                for s in original_suits:
                    namelist.append(c + s)

            for name in tqdm(namelist):
                img = cards[name.lower()]  # this is a PIL image
                x = binary_pil_to_cv2(img)
                x = adjust_colors(x)

                x = x.reshape((1,) + x.shape)  # this is a Numpy array with shape (1, 3, 150, 150)

                # the .flow() command below generates batches of randomly transformed images
                # and saves the results to the `preview/` directory
                i = 0
                directory = os.path.join(SCRAPER_DIR, folder, name)
                if not os.path.exists(directory):
                    os.makedirs(directory)

                for _ in datagen.flow(x, batch_size=100,
                                      save_to_dir=directory,
                                      save_prefix=name,
                                      save_format='png',
                                      ):
                    i += 1
                    if i > 100:
                        break  # otherwise the generator would loop indefinitely

    def train_neural_network(self):
        self.train_generator = ImageDataGenerator(
            rescale=0.02,
            shear_range=0.01,
            zoom_range=0.02,
            horizontal_flip=False).flow_from_directory(
            directory=os.path.join(SCRAPER_DIR, TRAIN_FOLDER),
            target_size=(img_height, img_width),
            batch_size=100,
            class_mode='binary',
            color_mode='rgb')

        self.validation_generator = ImageDataGenerator(
            rescale=0.01,
            shear_range=0.05,
            zoom_range=0.05,
            horizontal_flip=False).flow_from_directory(
            directory=os.path.join(SCRAPER_DIR, VALIDATE_FOLDER),
            target_size=(img_height, img_width),
            batch_size=100,
            class_mode='binary',
            color_mode='rgb')

        self.test_generator = ImageDataGenerator(
            rescale=0.02).flow_from_directory(
            directory=os.path.join(SCRAPER_DIR, TEST_FOLDER),
            target_size=(img_height, img_width),
            batch_size=1,
            shuffle=True,
            class_mode='binary',
            color_mode='rgb')

        num_classes = 52
        input_shape = (50, 15, 3)
        epochs = 20

        model = Sequential()
        model.add(Conv2D(64, (3, 3), input_shape=input_shape, activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(64, (2, 2), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Conv2D(256, (3, 3), activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(256, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Flatten())
        model.add(Dropout(0.2))
        model.add(Dense(2048, activation='relu', kernel_constraint=MaxNorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(1024, activation='relu', kernel_constraint=MaxNorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(num_classes, activation='softmax'))

        model.compile(loss=tensorflow.keras.losses.sparse_categorical_crossentropy,
                      optimizer=tensorflow.keras.optimizers.Adam(),
                      metrics=['accuracy'])

        log.info(model.summary())

        early_stop = tensorflow.keras.callbacks.EarlyStopping(monitor='val_loss',
                                                              min_delta=0,
                                                              patience=1,
                                                              verbose=1, mode='auto')
        tb = TensorBoard(log_dir='c:/tensorboard/pb',
                         histogram_freq=1,
                         write_graph=True,
                         write_images=True,
                         embeddings_freq=1,
                         embeddings_layer_names=False,
                         embeddings_metadata=False)

        model.fit(self.train_generator,
                  epochs=epochs,
                  verbose=1,
                  validation_data=self.validation_generator,
                  callbacks=[early_stop])
        self.model = model
        score = model.evaluate(self.test_generator, steps=52)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])

    def save_model_to_disk(self):
        # serialize model to JSON
        log.info("Save model to disk")
        class_mapping = self.train_generator.class_indices
        class_mapping = dict((v, k) for k, v in class_mapping.items())
        with open(SCRAPER_DIR + "/model_classes.json", "w") as json_file:
            json.dump(class_mapping, json_file)
        model_json = self.model.to_json()
        with open(SCRAPER_DIR + "/model.json", "w") as json_file:
            json_file.write(model_json)
        # serialize weights to HDF5
        self.model.save_weights(SCRAPER_DIR + "/model.h5")
        log.info("Done.")

    def save_model_to_db(self, table_name):
        log.info("Save model to database")
        json_file = open(SCRAPER_DIR + '/model.json', 'r')
        loaded_model_json = json_file.read()
        with open(SCRAPER_DIR + "/model_classes.json") as json_file:
            self.class_mapping = json.load(json_file)

        with open(SCRAPER_DIR + '/model.h5', 'rb') as filehandler:
            hd5_file_content = filehandler.read()
        mongo = MongoManager()
        mongo.update_tensorflow_model(table_name, hd5_file_content, json.dumps(loaded_model_json),
                                      json.dumps(self.class_mapping))
        log.info("Upload complete")

    def load_model(self):
        log.info("Loading model from disk")
        # load json and create model
        json_file = open(SCRAPER_DIR + '/model.json', 'r')
        loaded_model_json = json_file.read()
        json_file.close()
        self.loaded_model = model_from_json(loaded_model_json)
        # load weights into new model
        self.loaded_model.load_weights(SCRAPER_DIR + "/model.h5")
        with open(SCRAPER_DIR + "/model_classes.json") as json_file:
            self.class_mapping = json.load(json_file)

    def predict(self, file):
        print(file)
        if type(file) == str:
            img = cv2.imread(file)  # this is a PIL image
            img = cv2.resize(img, (15, 50))
            x = img_to_array(img)
            x = x.reshape((1,) + x.shape)
            x = x * 0.02
        else:
            x = file

        prediction = np.argmax(self.loaded_model.predict(x))
        return self.class_mapping[str(prediction)]


if __name__ == '__main__':
    n = CardNeuralNetwork()
    # n.create_test_images()

    n.train_neural_network()

    n.load_model()
    n.load_model()

    for card in ['3H', 'AS', '5C', 'KS']:
        filename = os.listdir(f'{TEST_FOLDER}/{card}/')[0]
        filename = f'{TEST_FOLDER}/{card}/' + filename
        prediction = n.predict(filename)
        print(prediction)
        print(f"Correct: {card == prediction}")
