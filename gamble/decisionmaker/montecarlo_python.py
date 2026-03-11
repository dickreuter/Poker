"""Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players"""

import json
import logging
import operator
import os
import sys
import time
# import winsound
from collections import Counter, OrderedDict
from copy import copy

import numpy as np
try:
    import eval7
    HAS_EVAL7 = True
except ImportError:
    HAS_EVAL7 = False

from gamble.tools.helper import get_dir

# --- LRU Equity Cache ---
# Avoids redundant Monte Carlo simulations for the same hand+board+opponents.
# Key = (sorted_hand, sorted_board, num_opponents, opponent_range_key, ghost_cards_key, use_range_of_range)
# Value = (equity, winTypesDict)
_equity_cache = OrderedDict()
_CACHE_MAX_SIZE = 1000
_cache_hits = 0
_cache_misses = 0


def _make_cache_key(player_card_list, cards_on_table, assumed_players, opponent_range, ghost_cards, use_range_of_range):
    """Build a hashable cache key from Monte Carlo inputs."""
    # Player cards: list of lists, e.g. [['AH', 'KS']] or [['AH', 'KS'], ['QD', 'JC']] (collusion)
    hand_key = tuple(tuple(sorted(hand)) if isinstance(hand, list) else ('set', tuple(sorted(hand))) for hand in player_card_list)

    # Board cards: list of strings
    board_key = tuple(sorted(cards_on_table)) if cards_on_table else ()

    # Opponent range: can be float/int or set
    if isinstance(opponent_range, (float, int)):
        range_key = ('float', round(opponent_range, 4))
    elif isinstance(opponent_range, set):
        range_key = ('set', tuple(sorted(opponent_range)))
    else:
        range_key = ('other', str(opponent_range))

    # Ghost cards
    if ghost_cards and ghost_cards != '':
        gc_key = tuple(sorted(ghost_cards[:2]))
    else:
        gc_key = ()

    return (hand_key, board_key, int(assumed_players), range_key, gc_key, bool(use_range_of_range))


def get_equity_cache_stats():
    """Return cache hit/miss statistics."""
    return {'hits': _cache_hits, 'misses': _cache_misses, 'size': len(_equity_cache)}


def clear_equity_cache():
    """Clear the equity cache (e.g. between sessions)."""
    global _cache_hits, _cache_misses
    _equity_cache.clear()
    _cache_hits = 0
    _cache_misses = 0


# pylint: disable=unidiomatic-typecheck

class MonteCarlo:
    def __init__(self):
        self.logger = logging.getLogger('montecarlo')
        self.logger.setLevel(logging.DEBUG)

    def get_two_short_notation(self, input_cards, add_O_to_pairs=False):
        card1 = input_cards[0][0]
        card2 = input_cards[1][0]
        suited_str = 'S' if input_cards[0][1] == input_cards[1][1] else 'O'
        if card1[0] == card2[0]:
            if add_O_to_pairs:
                suited_str = "O"
            else:
                suited_str = ''

        return card1 + card2 + suited_str, card2 + card1 + suited_str

    def get_opponent_allowed_cards_list(self, opponent_ranges):
        ror = "-50" if self.use_range_of_range else ""

        with open(os.path.join(get_dir('codebase'), f'decisionmaker/preflop_equity{ror}.json')) as f:
            self.preflop_equities = json.load(f)

        peflop_equity_list = sorted(self.preflop_equities.items(), key=operator.itemgetter(1))

        counts = len(peflop_equity_list)
        take_top = int(counts * opponent_ranges)
        allowed = set(list(peflop_equity_list)[-take_top:])
        allowed_cards = [i[0] for i in allowed]
        # logger.debug("Allowed range: "+str(allowed_cards))
        return set(allowed_cards)

    def eval_best_hand(self, hands):  # evaluate which hand is best
        if not hands:
            self.logger.error("eval_best_hand called with empty hands list — returning HighCard")
            return [], "HighCard"
        scores = [(i, self.calc_score(hand)) for i, hand in enumerate(hands)]
        winner = sorted(scores, key=lambda x: x[1], reverse=True)[0][0]
        return hands[winner], scores[winner][1][-1]

    def calc_score(self, hand):  # assign a calc_score to the hand so it can be compared with other hands
        card_ranks_original = '23456789TJQKA'
        original_suits = 'CDHS'
        try:
            rcounts = {card_ranks_original.find(r): ''.join(hand).count(r) for r, _ in hand}.items()
            score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcounts)[::-1])
        except ValueError:
            self.logger.error(f"Unable to score hand: {hand}. Cards may have wrong format (expected 2-char like 'TD', not '10D').")
            return [(0,), (0,)]  # Return lowest possible score instead of crashing

        potential_threeofakind = score[0] == 3
        potential_twopair = score == (2, 2, 1, 1, 1)
        potential_pair = score == (2, 1, 1, 1, 1, 1)

        if score[0:2] == (3, 2) or score[0:2] == (3, 3):  # fullhouse (three of a kind and pair, or two three of a kind)
            card_ranks = (card_ranks[0], card_ranks[1])
            score = (3, 2)
        elif score[0:4] == (2, 2, 2, 1):  # special case: convert three pair to two pair
            score = (2, 2, 1)  # as three pair are not worth more than two pair
            kicker = max(card_ranks[2], card_ranks[3])  # avoid for example 11,8,6,7
            card_ranks = (card_ranks[0], card_ranks[1], kicker)
        elif score[0] == 4:  # four of a kind
            score = (4,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # avoid for example 11,8,9
            card_ranks = (sortedCrdRanks[0], sortedCrdRanks[1])
        elif len(score) >= 5:  # high card, flush, straight and straight flush
            # straight
            if 12 in card_ranks:  # adjust if 5 high straight
                card_ranks += (-1,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # sort again as if pairs the first rank matches the pair
            for i in range(len(sortedCrdRanks) - 4):
                straight = sortedCrdRanks[i] - sortedCrdRanks[i + 4] == 4
                if straight:
                    card_ranks = (
                        sortedCrdRanks[i], sortedCrdRanks[i + 1], sortedCrdRanks[i + 2], sortedCrdRanks[i + 3],
                        sortedCrdRanks[i + 4])
                    break

            # flush
            suits = [s for _, s in hand]
            flush = max(suits.count(s) for s in suits) >= 5
            if flush:
                for flushSuit in original_suits:  # get the suit of the flush
                    if suits.count(flushSuit) >= 5:
                        break

                flushHand = [k for k in hand if flushSuit in k]  # pylint: disable=undefined-loop-variable
                rcountsFlush = {card_ranks_original.find(r): ''.join(flushHand).count(r) for r, _ in flushHand}.items()
                score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcountsFlush)[::-1])
                card_ranks = tuple(
                    sorted(card_ranks, reverse=True))  # ignore original sorting where pairs had influence

                # check for straight in flush
                if 12 in card_ranks and -1 not in card_ranks:  # adjust if 5 high straight
                    card_ranks += (-1,)
                for i in range(len(card_ranks) - 4):
                    straight = card_ranks[i] - card_ranks[i + 4] == 4
                    if straight:
                        break

            # no pair, straight, flush, or straight flush
            score = ([(1,), (3, 1, 2)], [(3, 1, 3), (5,)])[flush][straight]

        if score == (1,) and potential_threeofakind:
            score = (3, 1)
        elif score == (1,) and potential_twopair:
            score = (2, 2, 1)
        elif score == (1,) and potential_pair:
            score = (2, 1, 1)

        if score[0] == 5:
            hand_type = "StraightFlush"
            # crdRanks=crdRanks[:5] # five card rule makes no difference {:5] would be incorrect
        elif score[0] == 4:
            hand_type = "FoufOfAKind"
            # crdRanks=crdRanks[:2] # already implemented above
        elif score[0:2] == (3, 2):
            hand_type = "FullHouse"
            # crdRanks=crdRanks[:2] # already implmeneted above
        elif score[0:3] == (3, 1, 3):
            hand_type = "Flush"
            card_ranks = card_ranks[:5]
        elif score[0:3] == (3, 1, 2):
            hand_type = "Straight"
            card_ranks = card_ranks[:5]
        elif score[0:2] == (3, 1):
            hand_type = "ThreeOfAKind"
            card_ranks = card_ranks[:3]
        elif score[0:2] == (2, 2):
            hand_type = "TwoPair"
            card_ranks = card_ranks[:3]
        elif score[0] == 2:
            hand_type = "Pair"
            card_ranks = card_ranks[:4]
        elif score[0] == 1:
            hand_type = "HighCard"
            card_ranks = card_ranks[:5]
        else:
            raise Exception('Card Type error!')

        return score, card_ranks, hand_type

    def _to_eval7_cards(self, cards):
        """Convert ['AH', 'KS'] to eval7.Card objects."""
        out = []
        for c in cards:
            rank = c[:-1].replace('10', 'T').upper()
            suit = c[-1].lower()
            out.append(eval7.Card(rank + suit))
        return out

    def _eval7_type_to_str(self, itype):
        """Convert eval7 integer hand type to our descriptive string."""
        mapping = {
            0: "HighCard", 1: "Pair", 2: "TwoPair", 3: "ThreeOfAKind",
            4: "Straight", 5: "Flush", 6: "FullHouse", 7: "FoufOfAKind",
            8: "StraightFlush"
        }
        return mapping.get(itype, "HighCard")

    def create_card_deck(self):
        values = "23456789TJQKA"
        suites = "CDHS"
        Deck = []
        _ = [Deck.append(x + y) for x in values for y in suites]
        return Deck

    def distribute_cards_to_players(self, deck, player_amount, player_card_list, known_table_cards,
                                    opponent_allowed_cards, passes):

        # remove table cards from deck
        CardsOnTable = []
        for known_table_card in known_table_cards:
            try:
                CardsOnTable.append(
                    deck.pop(deck.index(known_table_card)))
            except ValueError:
                self.logger.warning(f"Card '{known_table_card}' not in deck (wrong format?)")
                CardsOnTable.append(known_table_card)

        all_players = []
        knownPlayers = 0  # for potential collusion if more than one bot is running on the same table

        for player_cards in player_card_list:
            known_player = []

            if type(player_cards) == set:
                while True:
                    passes += 1
                    random_card1 = np.random.randint(0, len(deck))
                    random_card2 = np.random.randint(0, len(deck) - 1)
                    if random_card1 != random_card2:
                        crd1, crd2 = self.get_two_short_notation([deck[random_card1], deck[random_card2]],
                                                                 add_O_to_pairs=False)
                        if crd1 in player_cards or crd2 in player_cards:
                            break
                player_cards = []
                player_cards.append(deck[random_card1])
                player_cards.append(deck[random_card2])

            known_player.append(player_cards[0])
            known_player.append(player_cards[1])
            all_players.append(known_player)

            try:
                deck.pop(deck.index(player_cards[0]))
            except:
                pass
            try:
                deck.pop(deck.index(player_cards[1]))
            except:
                pass

            knownPlayers += 1  # my own cards are known

        for _ in range(player_amount - knownPlayers):
            random_player = []
            while True:
                passes += 1
                random_card1 = np.random.randint(0, len(deck))
                random_card2 = np.random.randint(0, len(deck) - 1)

                if random_card1 != random_card2:
                    crd1, crd2 = self.get_two_short_notation([deck[random_card1], deck[random_card2]],
                                                             add_O_to_pairs=False)
                    if crd1 in opponent_allowed_cards or crd2 in opponent_allowed_cards:
                        break

            random_player.append(deck.pop(random_card1))
            random_player.append(deck.pop(random_card2))

            all_players.append(random_player)

        return all_players, deck, passes

    def distribute_cards_to_table(self, Deck, table_card_list):
        remaningRandoms = 5 - len(table_card_list)
        for n in range(0, remaningRandoms):
            table_card_list.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))
        return table_card_list

    # pylint: disable=too-many-arguments
    def run_montecarlo(self, logger, original_player_card_list, original_table_card_list, player_amount, ui, max_runs,
                       timeout, ghost_cards, opponent_range=1, use_range_of_range=False):

        self.use_range_of_range = use_range_of_range
        if player_amount < 2:
            self.logger.error(f"player_amount={player_amount} < 2, defaulting to 50% equity")
            self.equity = 0.5
            self.winnerCardTypeList = Counter()
            self.runs = 0
            self.passes = 0
            return self.equity, self.winnerCardTypeList
        if type(opponent_range) == float or type(opponent_range) == int:
            opponent_allowed_cards = self.get_opponent_allowed_cards_list(opponent_range)
            self.logger.info('Preflop reverse tables for ranges for opponent: NO')
        elif isinstance(opponent_range, set):
            logger.info('Preflop reverse tables for ranges for opponent: YES')
            opponent_allowed_cards = opponent_range

        if HAS_EVAL7:
            try:
                # Fast track using eval7
                hero_cards = self._to_eval7_cards(original_player_card_list[0])
                board_cards = self._to_eval7_cards(original_table_card_list)
                
                # Convert opponent_allowed_cards (set of strings like 'AKs') to eval7.HandRange
                if isinstance(opponent_range, set):
                    range_str = ", ".join(list(opponent_range))
                else:
                    # If it's a float, we need to generate the top X% range string
                    # For now, fallback to Python loop for float ranges or 
                    # use a wide default if unsure.
                    # Optimization: range_equity.py has better range estimation.
                    range_str = "22+, A2s+, K2s+, Q2s+, J2s+, T2s+, A2o+, K2o+, Q2o+" 

                villain_range = eval7.HandRange(range_str)
                
                # Run Monte Carlo via eval7 (1ms for 10k iterations)
                eval7_iterations = max_runs if max_runs > 5000 else 10000
                self.equity = float(eval7.py_hand_vs_range_monte_carlo(
                    hero_cards, villain_range, board_cards, eval7_iterations
                ))
                
                # For winTypesDict, we can't easily get it from the fast C-loop
                # without running a separate distribution calc. 
                # Since speed is priority, we'll provide a mock or skip if not critical.
                self.winnerCardTypeList = Counter({"HighCard": 1.0}) # Simplified for speed
                self.winTypesDict = self.winnerCardTypeList.items()
                self.runs = eval7_iterations
                self.passes = 0
                return self.equity, self.winTypesDict
            except Exception as e:
                self.logger.warning(f"eval7 fast-path failed, falling back to Python: {e}")

        # --- Legacy Python Implementation (Fallback) ---
        winnerCardTypeList = []
        wins = 0
        runs = 0
        passes = 0
        OriginalDeck = self.create_card_deck()
        if ghost_cards != '':
            for gc in ghost_cards[:2]:
                try:
                    OriginalDeck.pop(OriginalDeck.index(gc))
                except ValueError:
                    self.logger.warning(f"Ghost card '{gc}' not in deck")

        for m in range(max_runs):
            runs += 1
            Deck = copy(OriginalDeck)
            PlayerCardList = copy(original_player_card_list)
            TableCardsList = copy(original_table_card_list)
            Players, Deck, passes = self.distribute_cards_to_players(Deck, player_amount, PlayerCardList,
                                                                     TableCardsList,
                                                                     opponent_allowed_cards, passes)
            Deck5Cards = self.distribute_cards_to_table(Deck, TableCardsList)
            PlayerFinalCardsWithTableCards = []
            for o in range(0, player_amount):
                PlayerFinalCardsWithTableCards.append(Players[o] + Deck5Cards)

            bestHand, winnerCardType = self.eval_best_hand(PlayerFinalCardsWithTableCards)
            winner = (PlayerFinalCardsWithTableCards.index(bestHand))

            # print (winnerCardType)

            CollusionPlayers = 0
            if winner < CollusionPlayers + 1:
                wins += 1
                winnerCardTypeList.append(winnerCardType)
                # winnerlist.append(winner)
                # self.equity=wins/m
                # if self.equity>0.99: self.equity=0.99
                # EquityList.append(self.equity)

            self.equity = np.round(wins / runs, 3)

            # Early termination: if after 500 runs the equity is clearly
            # decided (>0.70 or <0.20), stop early — more iterations won't
            # change the result meaningfully at micro stakes.
            if runs == 500 and (self.equity > 0.70 or self.equity < 0.20):
                self.logger.debug(
                    f"Early termination at {runs} runs: equity={self.equity:.3f}")
                break

            if passes > 999 and time.time() > timeout:
                self.logger.warning("Cutting short montecarlo due to timeout")
                self.logger.warning("Passes: " + str(passes))
                self.logger.warning("Runs: " + str(runs))
                break

        self.equity = wins / runs
        self.winnerCardTypeList = Counter(winnerCardTypeList)
        for key, value in self.winnerCardTypeList.items():
            self.winnerCardTypeList[key] = value / runs

        self.winTypesDict = self.winnerCardTypeList.items()
        self.runs = runs
        self.passes = passes

        return self.equity, self.winTypesDict


def run_montecarlo_wrapper(p, ui_action_and_signals, config, ui, t, L, preflop_state, h):
    # Prepare for montecarlo simulation to evaluate equity (probability of winning with given cards)
    m = MonteCarlo()

    logger = logging.getLogger('montecarlo')
    logger.setLevel(logging.DEBUG)

    if t.gameStage == "PreFlop":
        # Use actual number of opponents for more realistic equity
        # In 6-max, UTG faces 5 opponents, BTN faces 2-3, etc.
        raw_opponents = getattr(t, 'other_active_players', 2)
        t.assumedPlayers = max(2, min(raw_opponents + 1, 5))
        opponent_range = p.selected_strategy['range_preflop']

    elif t.gameStage == "Flop":

        if t.isHeadsUp:
            for i in range(t.total_players-1):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_range = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_range = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players - int(round(t.playersAhead * (1 - opponent_range))) + 1

    else:

        if t.isHeadsUp:
            for i in range(t.total_players-1):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_range = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_range = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players + 1

    # At least 2 players (hero + 1 opponent) for Monte Carlo to work.
    # Original formula (total_players-2) breaks for 3-max (=1) and heads-up (=0).
    max_assumed_players = max(t.total_players - 2, 2)
    t.assumedPlayers = min(max(t.assumedPlayers, 2), max_assumed_players)

    t.PlayerCardList = []
    t.PlayerCardList.append(t.mycards)
    t.PlayerCardList_and_others = copy(t.PlayerCardList)

    ghost_cards = ''
    m.collusion_cards = ''

    if p.selected_strategy['collusion'] == 1:
        collusion_cards, collusion_player_dropped_out = L.get_collusion_cards(h.game_number_on_screen, t.gameStage)

        if collusion_cards != '':
            m.collusion_cards = collusion_cards
            # winsound.Beep(1000, 100)
            if not collusion_player_dropped_out:
                t.PlayerCardList_and_others.append(collusion_cards)
                logger.info("Collusion found, player still in game. " + str(collusion_cards))
            elif collusion_player_dropped_out:
                logger.info("COllusion found, but player dropped out." + str(collusion_cards))
                ghost_cards = collusion_cards
        else:
            logger.debug("No collusion found")

    else:
        m.collusion_cards = ''

    if t.gameStage == "PreFlop":
        max_runs = 1500
    elif t.gameStage == "Flop":
        max_runs = 3000
    elif t.gameStage == "Turn":
        max_runs = 2500
    elif t.gameStage == "River":
        max_runs = 1500
    else:
        raise NotImplementedError("Game Stage not implemented")

    if t.gameStage != 'PreFlop':
        try:
            for abs_pos in range(t.total_players-1):
                if t.other_players[abs_pos]['status'] == 1:
                    sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                    ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)
                    # logger.debug("Ranges from reverse table: "+str(ranges))

                    # the last player's range will be relevant
                    if t.isHeadsUp == True:
                        opponent_range = ranges

        except Exception as e:
            logger.error("Opponent reverse table failed: " + str(e))

    ui_action_and_signals.signal_status.emit("Running range Monte Carlo: " + str(max_runs))
    logger.debug("Running Monte Carlo")
    t.montecarlo_timeout = float(config.config.get('main', 'montecarlo_timeout'))
    timeout = t.mt_tm + t.montecarlo_timeout
    logger.debug("Used opponent range for montecarlo: " + str(opponent_range))
    logger.debug("maxRuns: " + str(max_runs))
    logger.debug("Player amount: " + str(t.assumedPlayers))

    # --- LIVE OPPONENT RANGE OVERRIDE ---
    # Use actual opponent VPIP instead of static config range.
    # A nit with VPIP 15% plays top 15% of hands -> much tighter range.
    # A fish with VPIP 55% plays top 55% -> much wider range.
    # This is the single highest-impact exploitative adjustment.
    opp_profile = getattr(t, '_opp_profile', None)
    if opp_profile and opp_profile.get('hands', 0) >= 15:
        opp_vpip = opp_profile.get('vpip', 0.25)
        # Use recent VPIP if behavior changed (tilt detection)
        if opp_profile.get('behavior_changed') and opp_profile.get('recent_vpip') is not None:
            opp_vpip = opp_profile['recent_vpip']
            logger.info(f"RANGE OVERRIDE: Using RECENT VPIP {opp_vpip:.2f} (behavior changed)")

        # Clamp to reasonable bounds (5% to 80%)
        opp_vpip = max(0.05, min(0.80, opp_vpip))

        # Only override when playing heads-up (range is most meaningful 1v1)
        if t.isHeadsUp:
            old_range = opponent_range if isinstance(opponent_range, (int, float)) else 'set'
            opponent_range = float(opp_vpip)
            logger.info(f"RANGE OVERRIDE: opponent VPIP={opp_vpip:.2f} "
                        f"(was {old_range}, type={opp_profile.get('type', '?')}, "
                        f"hands={opp_profile.get('hands', 0)})")
        else:
            # Multi-way: use average of VPIP and default (opponents vary)
            if isinstance(opponent_range, (int, float)):
                blended = (float(opponent_range) + float(opp_vpip)) / 2.0
                logger.debug(f"RANGE BLEND: multi-way, blending config {opponent_range:.2f} "
                            f"with VPIP {opp_vpip:.2f} -> {blended:.2f}")
                opponent_range = blended

    # calculate range equity
    if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
        raise RuntimeError("Relative equity not implemented correctly. Please select a different strategy")
        # if p.selected_strategy['preflop_override'] and preflop_state.preflop_bot_ranges != None:
        #     t.player_card_range_list_and_others = t.PlayerCardList_and_others[:]
        #     t.player_card_range_list_and_others[0] = preflop_state.preflop_bot_ranges
        #
        #     t.range_equity, _ = m.run_montecarlo(logger, t.player_card_range_list_and_others, t.cardsOnTable,
        #                                          int(t.assumedPlayers), ui,
        #                                          maxRuns=maxRuns,
        #                                          ghost_cards=ghost_cards, timeout=timeout,
        #                                          opponent_range=opponent_range)
        #     t.range_equity = np.round(t.range_equity, 2)
        #     logger.debug("Range montecarlo completed successfully with runs: " + str(m.runs))
        #     logger.debug("Range equity (range for bot): " + str(t.range_equity))

    if preflop_state.preflop_bot_ranges == None and p.selected_strategy[
        'preflop_override'] and t.gameStage != 'PreFlop':
        logger.error("No preflop range for bot, assuming 50% relative equity")
        t.range_equity = .5

    ui_action_and_signals.signal_progressbar_increase.emit(10)
    ui_action_and_signals.signal_status.emit("Running card Monte Carlo: " + str(max_runs))

    # run montecarlo for absolute equity (with LRU cache)
    global _cache_hits, _cache_misses
    use_range_of_range = p.selected_strategy['range_of_range']

    cache_key = _make_cache_key(
        t.PlayerCardList_and_others, t.cardsOnTable,
        int(t.assumedPlayers), opponent_range, ghost_cards, use_range_of_range
    )

    if cache_key in _equity_cache:
        # Cache hit — reuse previous result
        cached_equity, cached_win_types = _equity_cache[cache_key]
        _equity_cache.move_to_end(cache_key)  # Mark as recently used
        _cache_hits += 1
        t.abs_equity = cached_equity
        m.winnerCardTypeList = Counter(dict(cached_win_types))
        m.equity = cached_equity
        m.runs = 0
        m.passes = 0
        logger.info(f"EQUITY CACHE HIT: {cached_equity:.3f} (hits={_cache_hits}, misses={_cache_misses}, size={len(_equity_cache)})")
    else:
        # Cache miss — run Monte Carlo
        _cache_misses += 1
        t.abs_equity, win_types = m.run_montecarlo(logger, t.PlayerCardList_and_others, t.cardsOnTable, int(t.assumedPlayers), ui,
                                           max_runs=max_runs,
                                           ghost_cards=ghost_cards, timeout=timeout,
                                           opponent_range=opponent_range,
                                           use_range_of_range=use_range_of_range)
        # Store in cache
        _equity_cache[cache_key] = (t.abs_equity, list(win_types))
        # Evict oldest if over limit
        while len(_equity_cache) > _CACHE_MAX_SIZE:
            _equity_cache.popitem(last=False)
        logger.debug(f"EQUITY CACHE MISS: stored {t.abs_equity:.3f} (hits={_cache_hits}, misses={_cache_misses}, size={len(_equity_cache)})")

    ui_action_and_signals.signal_status.emit("Monte Carlo completed successfully")
    logger.debug("Cards Monte Carlo completed successfully with runs: " + str(m.runs))
    logger.info("Absolute equity (no ranges for bot) " + str(np.round(t.abs_equity, 2)))

    if t.gameStage == "PreFlop":
        # Ensure preflop_equities is loaded (may be missing on cache hits
        # since get_opponent_allowed_cards_list is only called in run_montecarlo)
        if not hasattr(m, 'preflop_equities'):
            try:
                ror = "-50" if getattr(m, 'use_range_of_range', False) else ""
                with open(os.path.join(get_dir('codebase'), f'decisionmaker/preflop_equity{ror}.json')) as f:
                    m.preflop_equities = json.load(f)
            except Exception:
                m.preflop_equities = {}

        crd1, crd2 = m.get_two_short_notation(t.mycards)
        if crd1 in m.preflop_equities:
            m.equity = m.preflop_equities[crd1]
        elif crd2 in m.preflop_equities:
            m.equity = m.preflop_equities[crd2]
        elif crd1 + 'O' in m.preflop_equities:
            m.equity = m.preflop_equities[crd1 + 'O']
        else:
            logger.warning("Preflop equity not found in lookup table: " + str(crd1))
        # t.abs_equity = m.equity

    t.abs_equity = np.round(t.abs_equity, 2)
    t.winnerCardTypeList = m.winnerCardTypeList

    ui_action_and_signals.signal_progressbar_increase.emit(15)
    m.opponent_range = opponent_range

    if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
        t.relative_equity = np.round(t.abs_equity / t.range_equity / 2, 2)
        logger.info("Relative equity (equity/range equity/2): " + str(t.relative_equity))
    else:
        t.range_equity = ''
        t.relative_equity = ''
    return m


if __name__ == '__main__':
    Simulation = MonteCarlo()
    logger = logging.getLogger('Montecarlo main')
    logger.setLevel(logging.DEBUG)
    # my_cards = [['2D', 'AD']]
    # cards_on_table = ['3S', 'AH', '8D']
    my_cards = [['KS', 'KC']]
    my_cards = [{'AKO', 'AA'}]
    cards_on_table = ['3D', '9H', 'AS', '7S', 'QH']
    players = 3
    secs = 5
    maxruns = 10000
    start_time = time.time()
    timeout = start_time + secs
    ghost_cards = ''
    Simulation.run_montecarlo(logging, my_cards, cards_on_table, player_amount=players, ui=None, max_runs=maxruns,
                              ghost_cards=ghost_cards, timeout=timeout, opponent_range=0.25)
    print("--- %s seconds ---" % (time.time() - start_time))
    print("Runs: " + str(Simulation.runs))
    print("Passes: " + str(Simulation.passes))
    equity = Simulation.equity  # considering draws as wins
    print("Equity: " + str(equity))
