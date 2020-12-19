import numpy as np


def straight_draw(cards):
    """check for straight draw"""
    values = "23456789TJQKA"
    card_value_indices = []
    _ = [card_value_indices.append(values.index(i)) for i in cards[0]]  # get indices of the card values
    card_value_indices = np.unique(np.array(card_value_indices))  # remove duplicates
    v = np.diff(np.sort(np.array(card_value_indices)))  # difference of 1 means consecutive cards
    is_straight_draw = (sum(np.sort(v)[0:4]) == 4)  # 4 consecutive cards
    return is_straight_draw
