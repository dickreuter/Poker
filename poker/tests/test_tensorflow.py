"""Testing of neural network related functions"""
import logging

import pytest
from PIL import Image
import os

from poker.scraper.table_scraper_nn import TEST_FOLDER, predict
from poker.tools.helper import ON_CI
from poker.tools.mongo_manager import MongoManager

log = logging.getLogger(__name__)


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_save_model():
    from poker.scraper.table_scraper_nn import CardNeuralNetwork
    nn = CardNeuralNetwork()
    nn.load_model()
    nn.save_model_to_db('test_table')


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_load_nn_model():
    mongo = MongoManager()
    mongo.load_table_nn_weights('test_table')


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_train_card_neural_network_and_predict():
    from poker.scraper.table_scraper_nn import CardNeuralNetwork, predict
    n = CardNeuralNetwork()
    n.create_augmented_images('GGpoker')
    n.train_neural_network()
    n.save_model_to_disk()
    n.load_model()

    for card in ['AH', '5C', 'QS', '6C', 'JC', '2H']:
        # Obtener el nombre de la carpeta específica
        folder_name = card

        # Acceder a la carpeta correspondiente
        folder_path = os.path.join(TEST_FOLDER, folder_name)

        # Buscar archivos en la carpeta
        for file_name in os.listdir(folder_path):
            if file_name.startswith(card) and file_name.endswith('.png'):
                # La imagen coincide con el nombre de la tarjeta
                file_path = os.path.join(folder_path, file_name)
                img = Image.open(file_path)
                prediction = predict(img, n.loaded_model, n.class_mapping)
                log.info(f"Prediction: {prediction} vs actual: {card}")
                assert card == prediction

            elif card in file_name and file_name.endswith('.png'):
                # La imagen tiene el nombre similar a "5C_0_27"
                file_path = os.path.join(folder_path, file_name)
                img = Image.open(file_path)
                prediction = predict(img, n.loaded_model, n.class_mapping)
                log.info(f"Prediction for similar name: {prediction} vs actual: {card}")
                assert card == prediction
