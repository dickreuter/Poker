'''
Assesses the log file and checks how the parameters in strategies.xml need to be adjusted to optimize playing
'''
import xml.etree.ElementTree as xml
from log_manager import *
from xml_handler import *
from debug_logger import *

class Genetic_Algorithm(object):
    def __init__(self, autoUpdate, logger):
        self.logger=logger
        p = XMLHandler('strategies.xml')
        p.read_XML()
        p_name = p.current_strategy.text
        L = self.loadLog(p_name)
        self.improve_strategy(L, p)
        if p.modified == True:
            if autoUpdate == False:
                user_input = input("Y/N? ")
                if user_input.upper() == "Y":
                    p.save_XML()
                    self.logger.info("XML Saved")
        if autoUpdate == True and self.changed > 0:
            p.save_XML()

    def loadLog(self, p_name):
        self.gameResults = {}
        L = Logging('log')
        L.get_stacked_bar_data('Template', p_name, 'stackedBar')
        self.recommendation = dict()
        return L

    def assess_call(self, p, L, decision, stage, coeff1, coeff2, coeff3, coeff4, change):
        A = L.d[decision, stage, 'Won'] > L.d[decision, stage, 'Lost'] * coeff1  # Call won > call lost * c1
        B = L.d[decision, stage, 'Lost'] > L.d['Fold', stage, 'Lost'] * coeff2  # Call Lost > Fold lost
        C = L.d[decision, stage, 'Won'] + L.d['Bet', stage, 'Won'] < L.d[
                                                                         'Fold', stage, 'Lost'] * coeff3  # Fold Lost*c3 > Call won + bet won
        if A and B:
            self.recommendation[stage, decision] = "ok"
        elif A and B == False and C:
            self.recommendation[stage, decision] = "more agressive"
            p.modify_XML(stage + 'MinCallEquity', -change)
            p.modify_XML(stage + 'CallPower', -change * 25)
            self.changed += 1
        elif A == False and B == True:
            self.recommendation[stage, decision] = "less agressive"
            p.modify_XML(stage + 'MinCallEquity', +change)
            p.modify_XML(stage + 'CallPower', +change * 25)
            self.changed += 1
        else:
            self.recommendation[stage, decision] = "inconclusive"
        self.logger.info(stage + " " + decision + ": " + self.recommendation[stage, decision])
        pass

    def assess_bet(self, p, L, decision, stage, coeff1, change):
        A = L.d['Bet', stage, 'Won'] + L.d['BetPlus', stage, 'Won'] + L.d['Bet half pot', stage, 'Won'] > (L.d[
                                                                                                               'Bet', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'BetPlus', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'Bet half pot', stage, 'Lost']) * coeff1  # Bet won bigger Bet lost
        B = L.d['Bluff', stage, 'Won'] > L.d['Bluff', stage, 'Lost']  # check won bigger check lost
        C = L.d['Bet', stage, 'Won'] + L.d['BetPlus', stage, 'Won'] + L.d['Bet half pot', stage, 'Won'] < (L.d[
                                                                                                               'Bet', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'BetPlus', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'Bet half pot', stage, 'Lost']) * 1  # Bet won bigger Bet lost

        if A and B == False:
            self.recommendation[stage, decision] = "ok"
        elif A and B:
            self.recommendation[stage, decision] = "more agressive"
            p.modify_XML(stage + 'MinBetEquity', -change)
            p.modify_XML(stage + 'BetPower', -change * 25)
            self.changed += 1
        elif C and B == False:
            self.recommendation[stage, decision] = "less agressive"
            p.modify_XML(stage + 'MinBetEquity', +change)
            p.modify_XML(stage + 'BetPower', +change * 25)
            self.changed += 1
        else:
            self.recommendation[stage, decision] = "inconclusive"
        self.logger.info(stage + " " + decision + ": " + self.recommendation[stage, decision])

    def assess_bluff(self, p, L, decision, stage, coeff1, change):
        # TODO: Not yet implemented
        A = L.d['Bet', stage, 'Won'] + L.d['BetPlus', stage, 'Won'] + L.d['Bet half pot', stage, 'Won'] > (L.d[
                                                                                                               'Bet', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'BetPlus', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'Bet half pot', stage, 'Lost']) * coeff1  # Bet won bigger Bet lost
        B = L.d['Check', stage, 'Won'] > L.d['Check', stage, 'Lost']  # check won bigger check lost
        C = L.d['Bet', stage, 'Won'] + L.d['BetPlus', stage, 'Won'] + L.d['Bet half pot', stage, 'Won'] < (L.d[
                                                                                                               'Bet', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'BetPlus', stage, 'Lost'] +
                                                                                                           L.d[
                                                                                                               'Bet half pot', stage, 'Lost']) * 1  # Bet won bigger Bet lost


    def improve_strategy(self, L, p):

        self.changed = 0
        maxChanges = 2
        if self.changed <= maxChanges:
            coeff1 = 2
            coeff2 = 1
            coeff3 = 2
            coeff4 = 1
            stage = 'River'
            decision = 'Call'
            change = 0.02
            self.assess_call(p, L, decision, stage, coeff1, coeff2, coeff3, coeff4, change)

        if self.changed < maxChanges:
            coeff1 = 2
            coeff2 = 1.5
            coeff3 = 2
            stage = 'Turn'
            decision = 'Call'
            change = 0.02
            self.assess_call(p, L, decision, stage, coeff1, coeff2, coeff3, coeff4, change)

        if self.changed < maxChanges:
            coeff1 = 2
            coeff2 = 1.5
            coeff3 = 2
            stage = 'Flop'
            decision = 'Call'
            change = 0.01
            self.assess_call(p, L, decision, stage, coeff1, coeff2, coeff3, coeff4, change)

        if self.changed < maxChanges:
            coeff1 = 2
            coeff2 = 2.5
            coeff3 = 2
            stage = 'PreFlop'
            decision = 'Call'
            change = 0.03
            self.assess_call(p, L, decision, stage, coeff1, coeff2, coeff3, coeff4, change)

        self.changed = 0
        if self.changed < maxChanges:
            coeff1 = 2
            stage = 'River'
            decision = 'Bet'
            change = 0.02
            self.assess_bet(p, L, decision, stage, coeff1, change)

        if self.changed < maxChanges:
            coeff1 = 2
            stage = 'Turn'
            decision = 'Bet'
            change = 0.02
            self.assess_bet(p, L, decision, stage, coeff1, change)

            # if self.changed<maxChanges:
            #     coeff1=2
            #     stage='Flop'
            #     decision='Bet'
            #     change=0.02
            #     self.assessBet(p,L, decision,stage,coeff1,change)

            # if self.changed<maxChanges:
            #     coeff1=2
            #     stage='PreFlop'
            #     decision='Bet'
            #     change=0.02
            #     self.assessBet(p,L, decision,stage,coeff1,change)


def run_genetic_algorithm(write, logger):
    logger.info("===Running genetic algorithm===")
    Terminator = Genetic_Algorithm(write,logger)



if __name__ == '__main__':
    logger = debug_logger().start_logger()
    run_genetic_algorithm(False,logger)
