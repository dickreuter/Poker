from .outs_calculator import Outs_Calculator

class Implied_Odds(object):
    def __init__(self):
        pass

    def calculate_implied_odds(self, effective_stacks,call_value,pot_value,table_phase,t):

        oc = Outs_Calculator()
        outs = oc.evaluate_hands(self,t.myCards,t.cardsOnTable)

        pot_odds = (pot_value + call_value) / call_value

        if table_phase == 'Flop':
            hitting_odds = (1 / (outs/47)) - 1
        else:
            hitting_odds = (1 / (outs/46)) - 1

        odds_difference = hitting_odds - pot_odds
        ev_difference = call_value * odds_difference
        remaining_stack = effective_stacks - call_value
        pot_on_next_street = pot_value + (call_value*2)

        return ev_difference, remaining_stack, pot_on_next_street


if __name__ == '__main__':
        print("Hello World")