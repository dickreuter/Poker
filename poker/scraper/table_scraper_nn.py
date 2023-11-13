import io
import json
import logging
import os
import shutil

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm

from poker.tools.helper import get_dir
from poker.tools.mongo_manager import MongoManager

SCRAPER_DIR = get_dir('pics')
TRAIN_FOLDER = get_dir('pics', "training_cards")
VALIDATE_FOLDER = get_dir('pics', "validate_cards")
TEST_FOLDER = get_dir('tests', "test_cards")

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

    @staticmethod
    def create_augmented_images(table_name):
        shutil.rmtree(TRAIN_FOLDER, ignore_errors=True)
        shutil.rmtree(VALIDATE_FOLDER, ignore_errors=True)

        log.info("Augmenting data with random pictures based on templates")

        from tensorflow.keras.preprocessing.image import ImageDataGenerator
        datagen = ImageDataGenerator(
            rotation_range=10,
            width_shift_range=0.05,
            height_shift_range=0.05,
            shear_range=0.02,
            zoom_range=0.05,
            horizontal_flip=False,
            fill_mode='nearest')

        mongo = MongoManager()
        table = mongo.get_table(table_name)

        for folder in [TRAIN_FOLDER, VALIDATE_FOLDER]:
            card_ranks_original = '23456789TJQKA'
            original_suits = 'CDHS'

            namelist = []
            for c in card_ranks_original:
                for s in original_suits:
                    namelist.append(c + s)

            for name in tqdm(namelist):
                img = table[name.lower()]  # this is a PIL image
                x = binary_pil_to_cv2(img)
                x = adjust_colors(x)

                x = x.reshape((1,) + x.shape)  # this is a Numpy array with shape (1, 3, 150, 150)

                # the .flow() command below generates batches of randomly transformed images
                # and saves the results to the `preview/` directory
                i = 0
                directory = os.path.join(SCRAPER_DIR, folder, name)
                if not os.path.exists(directory):
                    os.makedirs(directory)

                for _ in datagen.flow(x, save_to_dir=directory,
                                      save_prefix=name,
                                      save_format='png',
                                      ):
                    i += 1
                    if i > 500:
                        break  # otherwise the generator would loop indefinitely

    def train_neural_network(self):
        from tensorflow.keras.preprocessing.image import ImageDataGenerator
        self.train_generator = ImageDataGenerator(
            rescale=0.02,
            shear_range=0.01,
            zoom_range=0.02,
            horizontal_flip=False).flow_from_directory(
            directory=os.path.join(SCRAPER_DIR, TRAIN_FOLDER),
            target_size=(img_height, img_width),
            batch_size=128,
            class_mode='binary',
            color_mode='rgb')

        self.validation_generator = ImageDataGenerator(
            rescale=0.01,
            shear_range=0.05,
            zoom_range=0.05,
            horizontal_flip=False).flow_from_directory(
            directory=os.path.join(SCRAPER_DIR, VALIDATE_FOLDER),
            target_size=(img_height, img_width),
            batch_size=128,
            class_mode='binary',
            color_mode='rgb')

        num_classes = 52
        input_shape = (50, 15, 3)
        epochs = 50
        from tensorflow.keras.callbacks import TensorBoard, EarlyStopping, LearningRateScheduler
        from tensorflow.keras.constraints import MaxNorm
        from tensorflow.keras.layers import Conv2D, MaxPooling2D, BatchNormalization
        from tensorflow.keras.layers import Dropout, Flatten, Dense
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.losses import sparse_categorical_crossentropy
        from tensorflow.keras import optimizers
        from tensorflow.math import exp
        model = Sequential()
        model.add(Conv2D(64, (3, 3), input_shape=input_shape, activation='relu', padding='same'))
        model.add(Conv2D(64, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.3))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.4))
        model.add(Conv2D(256, (3, 3), activation='relu', padding='same'))
        model.add(Conv2D(256, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.5))
        model.add(Flatten())
        model.add(Dense(2048, activation='relu', kernel_constraint=MaxNorm(3)))
        model.add(Dropout(0.5))
        model.add(Dense(1024, activation='relu', kernel_constraint=MaxNorm(3)))
        model.add(Dropout(0.5))
        model.add(Dense(num_classes, activation='softmax'))        
        from tensorflow.keras.losses import sparse_categorical_crossentropy
        from tensorflow.keras import optimizers
        model.compile(loss=sparse_categorical_crossentropy,
                      optimizer=optimizers.Adam(),
                      metrics=['accuracy'])

        log.info(model.summary())

        early_stop = EarlyStopping(monitor='val_accuracy',
                                min_delta=0,
                                patience=5, # increased patience as sometimes more epochs are beneficial
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
        score = model.evaluate(self.validation_generator, steps=52)
        print('Validation loss:', score[0])
        print('Validation accuracy:', score[1])

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
        with open(SCRAPER_DIR + '/model.json', 'r') as json_file:
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
        with open(SCRAPER_DIR + '/model.json', 'r') as json_file:
            loaded_model_json = json_file.read()
        from keras.models import model_from_json
        self.loaded_model = model_from_json(loaded_model_json)
        # load weights into new model
        self.loaded_model.load_weights(SCRAPER_DIR + "/model.h5")
        with open(SCRAPER_DIR + "/model_classes.json") as json_file:
            self.class_mapping = json.load(json_file)

    def predict(self, file):
        print(file)
        img = cv2.imread(file)
        prediction = predict(img, self.loaded_model, self.class_mapping)
        return prediction


# actual predict function
def predict(pil_image, nn_model, mapping):
    img = pil_to_cv2(pil_image)
    img = adjust_colors(img)
    img = cv2.resize(img, (15, 50))
    from tensorflow.keras.preprocessing.image import img_to_array
    x = img_to_array(img)
    x = x.reshape((1,) + x.shape)
    x = x * 0.02

    prediction = np.argmax(nn_model.predict(x))
    card = mapping[str(prediction)]
    return card
