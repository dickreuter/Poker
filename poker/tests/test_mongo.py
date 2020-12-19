"""Tests for mongo"""
from poker.tools.mongo_manager import MongoManager


def test_increment_plays():
    mongo = MongoManager()
    mongo.increment_plays("PartyPoker 6 Players Fast Forward $1-$2 NL Hold'em")
