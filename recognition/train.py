import os
import keras
import json
import numpy as np
from keras.callbacks import TensorBoard
from keras.constraints import maxnorm
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array, load_img
from keras.models import Sequential, model_from_json
from keras.layers import Conv2D, MaxPooling2D
from keras.layers import Activation, Dropout, Flatten, Dense
from scipy import misc

dir_path = os.path.dirname(os.path.realpath(__file__))
base_dir = os.path.join( os.path.dirname( __file__ ), '..' )


class CardNeuralNetwork():
    def __init__(self):
        pass

    def create_test_images(self):
        datagen = ImageDataGenerator(
            rotation_range=5,
            width_shift_range=0.07,
            height_shift_range=0.07,
            shear_range=0.05,
            zoom_range=0.2,
            horizontal_flip=False,
            fill_mode='nearest')
        dirs = [(base_dir + r'/pics/PP_old/', r'/card_training/'),
                (base_dir + r'/pics/SN/', r'/card_training/'),
                (base_dir + r'/pics/PS/', r'/card_training/'),
                (base_dir + r'/pics/PP_old/', r'/card_testing/')]

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
                img = load_img(source_folder + name + '.png', grayscale=True)  # this is a PIL image
                x = img_to_array(img)  # this is a Numpy array with shape (3, 150, 150)
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
                    if i > 100:
                        break  # otherwise the generator would loop indefinitely

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
            color_mode='grayscale')

        validation_generator = validation_datagen.flow_from_directory(
            validation_data_dir,
            target_size=(img_height, img_width),
            batch_size=batch_size,
            class_mode='binary',
            color_mode='grayscale')

        test_generator = test_datagen.flow_from_directory(
            test_data_dir,
            target_size=(img_height, img_width),
            batch_size=batch_size,
            class_mode='binary',
            color_mode='grayscale')

        return train_generator, validation_generator, test_generator

    def train_neural_network(self, train_generator, validation_generator, test_datagen):
        num_classes = 53
        input_shape = (50, 15, 1)
        epochs = 50

        model = Sequential()
        model.add(Conv2D(32, (3, 3), input_shape=input_shape, activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(32, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Conv2D(64, (3, 3), activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(64, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(Dropout(0.2))
        model.add(Conv2D(128, (3, 3), activation='relu', padding='same'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Flatten())
        model.add(Dropout(0.2))
        model.add(Dense(1024, activation='relu', kernel_constraint=maxnorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(512, activation='relu', kernel_constraint=maxnorm(3)))
        model.add(Dropout(0.2))
        model.add(Dense(num_classes, activation='softmax'))

        model.compile(loss=keras.losses.sparse_categorical_crossentropy,
                      optimizer=keras.optimizers.Adam(),
                      metrics=['accuracy'])

        early_stop = keras.callbacks.EarlyStopping(monitor='val_loss',
                                                   min_delta=0,
                                                   patience=2,
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
        json_file = open('recognition/model.json', 'r')
        loaded_model_json = json_file.read()
        json_file.close()
        self.loaded_model = model_from_json(loaded_model_json)
        # load weights into new model
        self.loaded_model.load_weights("recognition/model.h5")
        print("Loaded model from disk")
        with open("recognition/model_classes.json") as json_file:
            self.class_mapping = json.load(json_file)

    def recognize_card(self, file):
        if type(file) == str:
            image = misc.imread(file, mode='L')
        else:
            image = file
        image = misc.imresize(image, (50, 15))
        image = image.reshape((1, 50, 15, 1))

        prediction = self.loaded_model.predict(image)
        result = self.class_mapping[str(np.argmax(prediction))]
        return result


if __name__ == '__main__':
    n = CardNeuralNetwork()
    n.create_test_images()

    train_generator, validation_generator, test_datagen = n.prepare_data()
    model = n.train_neural_network(train_generator, validation_generator, test_datagen)
    #
    # n.load_model()
    # n.recognize_card(r'c:\temp\7h.png')
    # n.recognize_card(r'c:\temp\2s.png')
