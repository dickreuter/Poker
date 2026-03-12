"""Testing of neural network related functions"""
import logging

import pytest
from PIL import Image

from sys_core.scraper.table_scraper_nn import TEST_FOLDER, predict
from sys_core.tools.helper import ON_CI
from sys_core.tools.mongo_manager import MongoManager

log = logging.getLogger(__name__)


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_save_model():
    from sys_core.scraper.table_scraper_nn import CardNeuralNetwork
    nn = CardNeuralNetwork()
    nn.load_model()
    nn.save_model_to_db('test_table')


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_load_nn_model():
    mongo = MongoManager()
    mongo.load_table_nn_weights('test_table')


@pytest.mark.skipif(ON_CI, reason='too long for ci')
def test_train_card_neural_network_and_predict():
    from sys_core.scraper.table_scraper_nn import CardNeuralNetwork
    n = CardNeuralNetwork()
    n.create_augmented_images('GG System2')
    n.train_neural_network()
    n.save_model_to_disk()
    n.load_model()

    for card in ['AH', '5C', 'QS', '6C', 'JC', '2H']:
        filename = f'{TEST_FOLDER}/' + card + '.png'
        img = Image.open(filename)
        prediction = predict(img, n.loaded_model, n.class_mapping)
        log.info(f"Prediction: {prediction} vs actual: {card}")
        assert card == prediction
