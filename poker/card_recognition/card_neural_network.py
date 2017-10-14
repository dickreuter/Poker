import os
import keras
import json
import numpy as np
import sys
import shutil

from PIL import Image
from keras.callbacks import TensorBoard
from keras.constraints import maxnorm
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array, load_img
from keras.models import Sequential, model_from_json
from keras.layers import Conv2D, MaxPooling2D
from keras.layers import Activation, Dropout, Flatten, Dense
from scipy import misc

if getattr(sys, 'frozen', False):
    dir_path = 'card_recognition'
    base_dir = ''
else:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    base_dir = os.path.join(os.path.dirname(__file__), '..')


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


class CardNeuralNetwork():
    def __init__(self):
        pass

    def create_test_images(self):
        shutil.rmtree('card_training', ignore_errors=True)
        shutil.rmtree('card_testing', ignore_errors=True)

        datagen = ImageDataGenerator(
            rotation_range=1,
            width_shift_range=0.1,
            height_shift_range=0.1,
            shear_range=0.05,
            zoom_range=0.1,
            horizontal_flip=False,
            fill_mode='nearest')

        dirs = [(base_dir + r'/pics/PP_old/', r'/card_training/'),
                (base_dir + r'/pics/SN/', r'/card_training/'),
                (base_dir + r'/pics/PS/', r'/card_training/'),
                (base_dir + r'/pics/PS/', r'/card_testing/'),
                             (r'tests/', r'/card_testing/')]

        for d in dirs:
            source_folder = d[0]
            destination_folder = d[1]
            card_ranks_original = '23456789TJQKA'
            original_suits = 'CDHS'

            namelist = []
            namelist.append('empty')
            for c in card_ranks_original:
                for s in original_suits:
                    namelist.append(c + s)

            for name in namelist:
                try:
                    img = load_img(source_folder + name + '.png')  # this is a PIL image
                    x = np.asarray(img)
                    x = adjust_colors(x)

                    x = x.reshape((1,) + x.shape)  # this is a Numpy array with shape (1, 3, 150, 150)

                    # the .flow() command below generates batches of randomly transformed images
                    # and saves the results to the `preview/` directory
                    i = 0
                    directory = dir_path + destination_folder + name
                    if not os.path.exists(directory):
                        os.makedirs(directory)

                    for batch in datagen.flow(x, batch_size=1,
                                              save_to_dir=directory,
                                              save_prefix=name,
                                              save_format='png',
                                              ):
                        i += 1
                        if i > 50:
                            break  # otherwise the generator would loop indefinitely
                except:
                    print("skipping: " + name)

    def prepare_data(self):
        train_data_dir = dir_path + "/card_training"
        validation_data_dir = dir_path + "/card_testing"
        test_data_dir = validation_data_dir

        img_height = 50
        img_width = 15
        batch_size = 52

        train_datagen = ImageDataGenerator(
            rescale=0.02,
            shear_range=0.01,
            zoom_range=0.02,
            horizontal_flip=False)

        validation_datagen = ImageDataGenerator(
            rescale=0.01,
            shear_range=0.05,
            zoom_range=0.05,
            horizontal_flip=False)

        test_datagen = ImageDataGenerator(
            rescale=0.02)

        train_generator = train_datagen.flow_from_directory(
            train_data_dir,
            target_size=(img_height, img_width),
            batch_size=batch_size,
            class_mode='binary',
            color_mode='rgb')

        validation_generator = validation_datagen.flow_from_directory(
            validation_data_dir,
            target_size=(img_height, img_width),
            batch_size=batch_size,
            class_mode='binary',
            color_mode='rgb')

        test_generator = test_datagen.flow_from_directory(
            test_data_dir,
            target_size=(img_height, img_width),
            batch_size=batch_size,
            class_mode='binary',
            color_mode='rgb')

        return train_generator, validation_generator, test_generator

    def train_neural_network(self):
        train_generator, validation_generator, test_datagen = self.prepare_data()
        num_classes = 53
        input_shape = (50, 15, 3)
        epochs = 17

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
        model.add(Dense(2048, activation='relu', kernel_constraint=maxnorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(1024, activation='relu', kernel_constraint=maxnorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(num_classes, activation='softmax'))

        model.compile(loss=keras.losses.sparse_categorical_crossentropy,
                      optimizer=keras.optimizers.Adam(),
                      metrics=['accuracy'])

        early_stop = keras.callbacks.EarlyStopping(monitor='val_loss',
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

        model.fit_generator(train_generator,
                            steps_per_epoch=num_classes,
                            epochs=epochs,
                            verbose=1,
                            validation_data=validation_generator,
                            validation_steps=100,
                            callbacks=[early_stop])
        score = model.evaluate_generator(test_datagen, steps=52)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])

        class_mapping = train_generator.class_indices

        # serialize model to JSON
        class_mapping = dict((v, k) for k, v in class_mapping.items())
        with open(dir_path + "/model_classes.json", "w") as json_file:
            json.dump(class_mapping, json_file)
        model_json = model.to_json()
        with open(dir_path + "/model.json", "w") as json_file:
            json_file.write(model_json)
        # serialize weights to HDF5
        model.save_weights(dir_path + "/model.h5")
        print("Saved model to disk")

    def load_model(self):
        # load json and create model
        json_file = open(dir_path+'/model.json', 'r')
        loaded_model_json = json_file.read()
        json_file.close()
        self.loaded_model = model_from_json(loaded_model_json)
        # load weights into new model
        self.loaded_model.load_weights(dir_path+"/model.h5")
        with open(dir_path+"/model_classes.json") as json_file:
            self.class_mapping = json.load(json_file)

    def recognize_card(self, file):
        if type(file) == str:
            image = Image.open(file)
            image = np.asarray(image)

        else:
            image = file
        image = misc.imresize(image, (50, 15))
        image = adjust_colors(image)

        image = image.reshape((1, 50, 15, 3))

        prediction = self.loaded_model.predict(image)
        result = self.class_mapping[str(np.argmax(prediction))]
        return result


if __name__ == '__main__':
    n = CardNeuralNetwork()
    n.create_test_images()

    n.train_neural_network()

    n.load_model()
    print(n.recognize_card(r'tests/5c.png'))
    print(n.recognize_card(r'tests/7h.png'))
    print(n.recognize_card(r'tests/ah.png'))
    print(n.recognize_card(r'tests/ts.png'))
    print(n.recognize_card(r'tests/qs.png'))
