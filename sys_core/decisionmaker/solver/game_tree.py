"""Poker game tree builder for CFR solving.

Builds action trees parameterized by SPR (stack-to-pot ratio).
Shallow stacks → fewer bet sizes. Deep stacks → more options.
All-in is ALWAYS an action at every decision node.
"""
from enum import IntEnum
from typing import List, Dict, Optional, Tuple


class Player(IntEnum):
    HERO = 0
    VILLAIN = 1


class Action:
    """A poker action with associated bet size."""
    FOLD = 'fold'
    CHECK = 'check'
    CALL = 'call'
    BET_SMALL = 'bet_small'    # ~33% pot
    BET_MEDIUM = 'bet_medium'  # ~67% pot
    BET_LARGE = 'bet_large'    # ~125% pot
    ALLIN = 'allin'


# Bet sizes as fraction of pot
BET_SIZES = {
    Action.BET_SMALL: 0.33,
    Action.BET_MEDIUM: 0.67,
    Action.BET_LARGE: 1.25,
}


class Node:
    """A node in the poker game tree."""
    __slots__ = ('player', 'actions', 'children', 'history',
                 'pot', 'stacks', 'is_terminal', 'terminal_type',
                 'bet_into_pot')

    def __init__(self, player: int, pot: float, stacks: Tuple[float, float],
                 history: str = ''):
        self.player = player
        self.pot = pot
        self.stacks = stacks  # (hero_stack, villain_stack)
        self.history = history
        self.actions: List[str] = []
        self.children: Dict[str, 'Node'] = {}
        self.is_terminal = False
        self.terminal_type = None  # 'showdown', 'fold_hero', 'fold_villain'
        self.bet_into_pot = 0.0  # Amount the acting player has already put in this round


def _make_terminal(pot, stacks, history, terminal_type):
    """Create a terminal node."""
    node = Node(player=-1, pot=pot, stacks=stacks, history=history)
    node.is_terminal = True
    node.terminal_type = terminal_type
    return node


def build_tree(pot: float, stacks: Tuple[float, float],
               hero_is_ip: bool = True, spr: float = None) -> Node:
    """Build a single-street game tree.

    Args:
        pot: current pot size
        stacks: (hero_stack, villain_stack)
        hero_is_ip: True if hero acts second (in position)
        spr: stack-to-pot ratio (auto-computed if None)

    Returns:
        Root node of the game tree.
    """
    if spr is None:
        eff_stack = min(stacks[0], stacks[1])
        spr = eff_stack / pot if pot > 0 else 10.0

    # Choose bet sizes based on SPR
    if spr < 2:
        bet_actions = [Action.ALLIN]
    elif spr < 4:
        bet_actions = [Action.BET_MEDIUM, Action.ALLIN]
    elif spr < 8:
        bet_actions = [Action.BET_SMALL, Action.BET_MEDIUM, Action.ALLIN]
    else:
        bet_actions = [Action.BET_SMALL, Action.BET_MEDIUM, Action.BET_LARGE, Action.ALLIN]

    # First to act
    first = Player.VILLAIN if hero_is_ip else Player.HERO
    second = Player.HERO if hero_is_ip else Player.VILLAIN

    root = Node(player=first, pot=pot, stacks=stacks, history='')
    _build_action_node(root, first, second, pot, stacks, bet_actions, '', 0)
    return root


def _build_action_node(node, acting, opponent, pot, stacks, bet_actions,
                       history, depth):
    """Recursively build action nodes."""
    if depth > 6:  # Safety: prevent infinite recursion
        node.is_terminal = True
        node.terminal_type = 'showdown'
        return

    hero_stack, villain_stack = stacks
    acting_stack = hero_stack if acting == Player.HERO else villain_stack

    # Available actions
    actions = []

    # Check if this is a response to a bet
    is_facing_bet = history.endswith('b') or history.endswith('B') or history.endswith('L') or history.endswith('A')

    if is_facing_bet:
        # Facing a bet: can fold, call, or raise (allin)
        actions.append(Action.FOLD)
        actions.append(Action.CALL)
        if acting_stack > 0:
            actions.append(Action.ALLIN)
    else:
        # No bet to face: can check or bet
        actions.append(Action.CHECK)
        for ba in bet_actions:
            if ba == Action.ALLIN:
                if acting_stack > 0:
                    actions.append(Action.ALLIN)
            else:
                bet_size = BET_SIZES.get(ba, 0.5) * pot
                if bet_size < acting_stack:
                    actions.append(ba)
                elif acting_stack > 0:
                    # Bet would be all-in, skip (allin action covers this)
                    pass

    node.actions = actions
    node.player = acting

    for action in actions:
        child_history = history + _action_char(action)

        if action == Action.FOLD:
            # Opponent wins pot
            if acting == Player.HERO:
                child = _make_terminal(pot, stacks, child_history, 'fold_hero')
            else:
                child = _make_terminal(pot, stacks, child_history, 'fold_villain')
            node.children[action] = child

        elif action == Action.CHECK:
            if is_facing_bet:
                # Can't check when facing a bet
                continue
            # Check: if both checked, it's a showdown (or next street)
            if 'x' in history:  # Both players checked
                child = _make_terminal(pot, stacks, child_history, 'showdown')
            else:
                # Opponent's turn to act
                child = Node(player=opponent, pot=pot, stacks=stacks,
                             history=child_history)
                _build_action_node(child, opponent, acting, pot, stacks,
                                   [ba for ba in bet_actions], child_history, depth + 1)
            node.children[action] = child

        elif action == Action.CALL:
            # Call: match the bet, go to showdown (single-street tree)
            # Figure out what we're calling
            call_amount = _get_call_amount(history, pot, stacks, acting)
            new_pot = pot + call_amount
            new_stacks = list(stacks)
            if acting == Player.HERO:
                new_stacks[0] -= call_amount
            else:
                new_stacks[1] -= call_amount
            child = _make_terminal(new_pot, tuple(new_stacks),
                                   child_history, 'showdown')
            node.children[action] = child

        elif action == Action.ALLIN:
            allin_amount = acting_stack
            new_pot = pot + allin_amount
            new_stacks = list(stacks)
            if acting == Player.HERO:
                new_stacks[0] = 0
            else:
                new_stacks[1] = 0

            if is_facing_bet:
                # All-in raise — opponent can fold or call
                child = Node(player=opponent, pot=new_pot,
                             stacks=tuple(new_stacks), history=child_history)
                child.actions = [Action.FOLD, Action.CALL]

                # Fold
                if opponent == Player.HERO:
                    fold_node = _make_terminal(new_pot, tuple(new_stacks),
                                               child_history + 'f', 'fold_hero')
                else:
                    fold_node = _make_terminal(new_pot, tuple(new_stacks),
                                               child_history + 'f', 'fold_villain')
                child.children[Action.FOLD] = fold_node

                # Call
                opp_stack = new_stacks[0] if opponent == Player.HERO else new_stacks[1]
                call_amt = min(allin_amount, opp_stack)
                call_pot = new_pot + call_amt
                call_stacks = list(new_stacks)
                if opponent == Player.HERO:
                    call_stacks[0] -= call_amt
                else:
                    call_stacks[1] -= call_amt
                call_node = _make_terminal(call_pot, tuple(call_stacks),
                                           child_history + 'c', 'showdown')
                child.children[Action.CALL] = call_node
                node.children[action] = child
            else:
                # Open shove — opponent can fold or call
                child = Node(player=opponent, pot=new_pot,
                             stacks=tuple(new_stacks), history=child_history)
                child.actions = [Action.FOLD, Action.CALL]

                if opponent == Player.HERO:
                    fold_node = _make_terminal(new_pot, tuple(new_stacks),
                                               child_history + 'f', 'fold_hero')
                else:
                    fold_node = _make_terminal(new_pot, tuple(new_stacks),
                                               child_history + 'f', 'fold_villain')
                child.children[Action.FOLD] = fold_node

                opp_stack = new_stacks[0] if opponent == Player.HERO else new_stacks[1]
                call_amt = min(allin_amount, opp_stack)
                call_pot = new_pot + call_amt
                call_stacks = list(new_stacks)
                if opponent == Player.HERO:
                    call_stacks[0] -= call_amt
                else:
                    call_stacks[1] -= call_amt
                call_node = _make_terminal(call_pot, tuple(call_stacks),
                                           child_history + 'c', 'showdown')
                child.children[Action.CALL] = call_node
                node.children[action] = child

        else:
            # Bet (small/medium/large)
            bet_frac = BET_SIZES.get(action, 0.5)
            bet_amount = min(bet_frac * pot, acting_stack)
            new_pot = pot + bet_amount
            new_stacks = list(stacks)
            if acting == Player.HERO:
                new_stacks[0] -= bet_amount
            else:
                new_stacks[1] -= bet_amount

            # Opponent responds
            child = Node(player=opponent, pot=new_pot,
                         stacks=tuple(new_stacks), history=child_history)
            _build_facing_bet(child, opponent, acting, new_pot,
                              tuple(new_stacks), bet_amount, child_history, depth + 1)
            node.children[action] = child


def _build_facing_bet(node, acting, opponent, pot, stacks, bet_amount,
                      history, depth):
    """Build response to a bet: fold, call, or raise-allin."""
    if depth > 6:
        node.is_terminal = True
        node.terminal_type = 'showdown'
        return

    acting_stack = stacks[0] if acting == Player.HERO else stacks[1]
    actions = [Action.FOLD, Action.CALL]
    if acting_stack > bet_amount:
        actions.append(Action.ALLIN)

    node.actions = actions
    node.player = acting

    for action in actions:
        child_history = history + _action_char(action)

        if action == Action.FOLD:
            if acting == Player.HERO:
                child = _make_terminal(pot, stacks, child_history, 'fold_hero')
            else:
                child = _make_terminal(pot, stacks, child_history, 'fold_villain')
            node.children[action] = child

        elif action == Action.CALL:
            call_amt = min(bet_amount, acting_stack)
            new_pot = pot + call_amt
            new_stacks = list(stacks)
            if acting == Player.HERO:
                new_stacks[0] -= call_amt
            else:
                new_stacks[1] -= call_amt
            child = _make_terminal(new_pot, tuple(new_stacks),
                                   child_history, 'showdown')
            node.children[action] = child

        elif action == Action.ALLIN:
            allin_amt = acting_stack
            new_pot = pot + allin_amt
            new_stacks = list(stacks)
            if acting == Player.HERO:
                new_stacks[0] = 0
            else:
                new_stacks[1] = 0

            # Opponent responds to the raise
            opp_child = Node(player=opponent, pot=new_pot,
                             stacks=tuple(new_stacks), history=child_history)
            opp_child.actions = [Action.FOLD, Action.CALL]

            if opponent == Player.HERO:
                fold_n = _make_terminal(new_pot, tuple(new_stacks),
                                        child_history + 'f', 'fold_hero')
            else:
                fold_n = _make_terminal(new_pot, tuple(new_stacks),
                                        child_history + 'f', 'fold_villain')
            opp_child.children[Action.FOLD] = fold_n

            opp_stack = new_stacks[0] if opponent == Player.HERO else new_stacks[1]
            call_a = min(allin_amt, opp_stack)
            call_p = new_pot + call_a
            call_s = list(new_stacks)
            if opponent == Player.HERO:
                call_s[0] -= call_a
            else:
                call_s[1] -= call_a
            call_n = _make_terminal(call_p, tuple(call_s),
                                    child_history + 'c', 'showdown')
            opp_child.children[Action.CALL] = call_n
            node.children[action] = opp_child


def _action_char(action):
    """Short character for action history string."""
    return {
        Action.FOLD: 'f', Action.CHECK: 'x', Action.CALL: 'c',
        Action.BET_SMALL: 'b', Action.BET_MEDIUM: 'B',
        Action.BET_LARGE: 'L', Action.ALLIN: 'A',
    }.get(action, '?')


def _get_call_amount(history, pot, stacks, acting):
    """Estimate call amount from history."""
    # Look at the last bet action
    for ch in reversed(history):
        if ch == 'b':
            return 0.33 * (pot * 0.7)  # Rough: 33% of original pot
        elif ch == 'B':
            return 0.67 * (pot * 0.7)
        elif ch == 'L':
            return 1.25 * (pot * 0.7)
        elif ch == 'A':
            # Opponent went all-in
            opp_idx = 1 if acting == Player.HERO else 0
            return stacks[opp_idx]  # Already 0 if they're all-in
    return 0


def count_nodes(node) -> int:
    """Count total nodes in tree (for debugging)."""
    if node.is_terminal:
        return 1
    total = 1
    for child in node.children.values():
        total += count_nodes(child)
    return total


def count_terminals(node) -> int:
    """Count terminal nodes."""
    if node.is_terminal:
        return 1
    total = 0
    for child in node.children.values():
        total += count_terminals(child)
    return total
