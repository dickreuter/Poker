"""Discounted Counterfactual Regret Minimization (DCFR) engine.

Core algorithm for computing Nash equilibrium strategies in poker.
Takes a game tree + payoff matrix, returns mixed strategies per hand bucket.

DCFR converges faster than vanilla CFR by discounting early (bad) iterations.
Used by postflop-solver (the open-source solver that beats PioSolver).
"""
import logging
from typing import Dict, Tuple, Optional
from .game_tree import Node, Player, Action

log = logging.getLogger(__name__)


class CFRSolver:
    """Discounted CFR solver for 2-player zero-sum poker."""

    def __init__(self):
        # {(player, bucket, history): {action: cumulative_regret}}
        self.regret_sum: Dict[Tuple, Dict[str, float]] = {}
        # {(player, bucket, history): {action: cumulative_strategy_weight}}
        self.strategy_sum: Dict[Tuple, Dict[str, float]] = {}

    def solve(self, root: Node, n_hero_buckets: int, n_villain_buckets: int,
              equity_matrix: Dict[Tuple[int, int], float],
              n_iterations: int = 500,
              hero_bucket_weights: Dict[int, float] = None,
              villain_bucket_weights: Dict[int, float] = None,
              ) -> Dict[Tuple, Dict[str, float]]:
        """Run DCFR and return average strategy profile.

        Args:
            root: game tree root node
            n_hero_buckets: number of hero hand buckets
            n_villain_buckets: number of villain hand buckets
            equity_matrix: {(hero_bucket, villain_bucket): hero_equity}
                           Used at showdown terminals.
            n_iterations: CFR iterations (more = closer to Nash)
            hero_bucket_weights: {bucket: weight} for non-uniform bucket distribution
            villain_bucket_weights: same for villain

        Returns:
            Average strategy: {(player, bucket, history): {action: frequency}}
        """
        self.regret_sum.clear()
        self.strategy_sum.clear()
        self._equity_matrix = equity_matrix
        self._root_pot = root.pot

        hero_buckets = list(range(n_hero_buckets))
        villain_buckets = list(range(n_villain_buckets))

        # Default uniform weights
        if hero_bucket_weights is None:
            hero_bucket_weights = {b: 1.0 / n_hero_buckets for b in hero_buckets}
        if villain_bucket_weights is None:
            villain_bucket_weights = {b: 1.0 / n_villain_buckets for b in villain_buckets}

        for t in range(1, n_iterations + 1):
            # DCFR discount parameters (from the DCFR paper)
            alpha, beta, gamma = 1.5, 0.5, 2.0
            pos_discount = t ** alpha / (t ** alpha + 1.0)
            neg_discount = t ** beta / (t ** beta + 1.0)
            strat_discount = (t / (t + 1.0)) ** gamma

            for hb in hero_buckets:
                for vb in villain_buckets:
                    w = hero_bucket_weights.get(hb, 0) * villain_bucket_weights.get(vb, 0)
                    if w < 1e-12:
                        continue
                    self._cfr_traverse(
                        root, hb, vb, 1.0, 1.0, t,
                        pos_discount, neg_discount, strat_discount
                    )

        # Extract average strategy
        return self._get_average_strategy()

    def _cfr_traverse(self, node: Node, hero_bucket: int, villain_bucket: int,
                      p_hero: float, p_villain: float, t: int,
                      pos_disc: float, neg_disc: float, strat_disc: float) -> float:
        """Single CFR traversal. Returns expected value for hero."""
        if node.is_terminal:
            return self._terminal_payoff(node, hero_bucket, villain_bucket)

        player = node.player
        actions = node.actions
        if not actions:
            return 0.0

        is_hero = (player == Player.HERO)
        bucket = hero_bucket if is_hero else villain_bucket
        info_set = (player, bucket, node.history)

        # Get current strategy from regrets
        strategy = self._get_strategy(info_set, actions)

        action_values = {}
        node_value = 0.0

        for action in actions:
            child = node.children.get(action)
            if child is None:
                continue

            if is_hero:
                av = self._cfr_traverse(
                    child, hero_bucket, villain_bucket,
                    p_hero * strategy[action], p_villain,
                    t, pos_disc, neg_disc, strat_disc
                )
            else:
                av = self._cfr_traverse(
                    child, hero_bucket, villain_bucket,
                    p_hero, p_villain * strategy[action],
                    t, pos_disc, neg_disc, strat_disc
                )
            action_values[action] = av
            node_value += strategy[action] * av

        # Update regrets and strategy sum
        opp_reach = p_villain if is_hero else p_hero
        my_reach = p_hero if is_hero else p_villain

        if info_set not in self.regret_sum:
            self.regret_sum[info_set] = {a: 0.0 for a in actions}
        if info_set not in self.strategy_sum:
            self.strategy_sum[info_set] = {a: 0.0 for a in actions}

        for action in actions:
            if action not in action_values:
                continue
            regret = action_values[action] - node_value

            # DCFR: discount regrets
            old = self.regret_sum[info_set].get(action, 0.0)
            discount = pos_disc if old > 0 else neg_disc
            self.regret_sum[info_set][action] = old * discount + opp_reach * regret

            # Accumulate strategy (for averaging)
            self.strategy_sum[info_set][action] += my_reach * strategy[action] * strat_disc

        return node_value

    def _terminal_payoff(self, node: Node, hero_bucket: int,
                         villain_bucket: int) -> float:
        """Compute hero's payoff at a terminal node."""
        pot = node.pot

        if node.terminal_type == 'fold_hero':
            # Hero folded — hero loses what they put in
            return -self._hero_investment(node)

        elif node.terminal_type == 'fold_villain':
            # Villain folded — hero wins the pot
            return self._hero_winnings(node)

        elif node.terminal_type == 'showdown':
            # Showdown — use pre-computed equity
            equity = self._equity_matrix.get(
                (hero_bucket, villain_bucket), 0.5)
            # Hero's EV = equity * pot - hero's investment
            hero_invested = self._hero_investment(node)
            return equity * pot - hero_invested

        return 0.0

    def _hero_investment(self, node: Node) -> float:
        """How much hero has put into the pot beyond the initial pot."""
        # Initial stacks minus current stacks = amount invested
        # We track this via stacks in the node
        # root stacks[0] - node stacks[0] = hero invested
        return max(0, self._root_pot * 0.5)  # Simplified: assume symmetric initial investment

    def _hero_winnings(self, node: Node) -> float:
        """How much hero wins when villain folds."""
        # Hero wins the pot minus what hero put in
        return node.pot * 0.5  # Simplified: hero wins half the pot (net gain)

    def _get_strategy(self, info_set, actions) -> Dict[str, float]:
        """Regret matching: convert cumulative regrets to strategy."""
        regrets = self.regret_sum.get(info_set, {})
        positive = {a: max(regrets.get(a, 0.0), 0.0) for a in actions}
        total = sum(positive.values())

        if total > 0:
            return {a: positive[a] / total for a in actions}
        # Uniform random when no positive regrets
        n = len(actions)
        return {a: 1.0 / n for a in actions}

    def _get_average_strategy(self) -> Dict[Tuple, Dict[str, float]]:
        """Extract the average strategy (which converges to Nash)."""
        avg = {}
        for info_set, strat_sum in self.strategy_sum.items():
            total = sum(strat_sum.values())
            if total > 0:
                avg[info_set] = {a: v / total for a, v in strat_sum.items()}
            else:
                actions = list(strat_sum.keys())
                n = len(actions)
                avg[info_set] = {a: 1.0 / n for a in actions}
        return avg

    def get_strategy_for_hand(self, avg_strategy: Dict, player: int,
                              bucket: int, history: str = '') -> Dict[str, float]:
        """Look up the solved strategy for a specific hand bucket at a node."""
        info_set = (player, bucket, history)
        return avg_strategy.get(info_set, {})
