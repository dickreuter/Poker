import os
import keras
import json
import numpy as np
import sys
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


class CardNeuralNetwork():
    def __init__(self):
        pass

    def prepare_data(self):
        train_data_dir = dir_path + "/card_training"
        validation_data_dir = dir_path + "/card_testing"
        test_data_dir = validation_data_dir



        return

    def train_neural_network(self):
        train_generator, validation_generator, test_datagen = self.prepare_data()
        num_classes = 53
        input_shape = (50, 15, 3)
        epochs = 18

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
                                                   patience=30,
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

class ApplyModel():
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

    def apply_model(self, input):

        prediction = self.loaded_model.predict(input)
        result = self.class_mapping[str(np.argmax(prediction))]
        return result


if __name__ == '__main__':
    n = CardNeuralNetwork()
    # n.create_test_images()
    #
    #
    # n.train_neural_network()

    n.load_model()
    print(n.recognize_card(r'c:\temp\5c.png'))
    print(n.recognize_card(r'c:\temp\7h.png'))
    print(n.recognize_card(r'c:\temp\ah.png'))
    print(n.recognize_card(r'c:\temp\ts.png'))
