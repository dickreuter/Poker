"""
ULTRATHINK - Advanced Meta-Learning & Reasoning System

This is the advanced thinking layer that enables Claude sessions to:
1. Collectively learn and improve the system service
2. Track what works and what doesn't across sessions
3. Generate improvement hypotheses
4. Test and validate improvements
5. Evolve strategies based on accumulated experience

Philosophy:
    Each Claude session contributes observations. UltraThink synthesizes these
    into actionable improvements. Over time, the system becomes more intelligent
    about system service optimization.

Architecture:
    +------------------------------------------------------------------+
    |                        ULTRATHINK CORE                            |
    +------------------------------------------------------------------+
    |                                                                   |
    |  +--------------+    +---------------+    +------------------+   |
    |  | OBSERVATION  |    | HYPOTHESIS    |    | EXPERIMENTATION  |   |
    |  |   LAYER      |    |   LAYER       |    |     LAYER        |   |
    |  +--------------+    +---------------+    +------------------+   |
    |        |                    |                      |             |
    |        v                    v                      v             |
    |  +--------------+    +---------------+    +------------------+   |
    |  | Pattern      |    | Improvement   |    | A/B Testing      |   |
    |  | Detection    |    | Generation    |    | Framework        |   |
    |  +--------------+    +---------------+    +------------------+   |
    |        |                    |                      |             |
    |        +--------------------+----------------------+             |
    |                             |                                    |
    |                             v                                    |
    |                    +-----------------+                           |
    |                    | KNOWLEDGE       |                           |
    |                    | CONSOLIDATION   |                           |
    |                    +-----------------+                           |
    |                             |                                    |
    |                             v                                    |
    |                    +-----------------+                           |
    |                    | EVOLUTION       |                           |
    |                    | ENGINE          |                           |
    |                    +-----------------+                           |
    +------------------------------------------------------------------+

Usage:
    from sys_core.tools.ultrathink import UltraThinkCore

    # Initialize
    ut = UltraThinkCore()

    # Record observation
    ut.observe(
        category="card_detection",
        event="template_match_failed",
        context={"score": 0.36, "expected": 0.15},
        outcome="cards_not_detected"
    )

    # Generate improvement hypothesis
    hypothesis = ut.hypothesize("card_detection")

    # Run experiment
    result = ut.experiment(
        hypothesis_id=hypothesis.id,
        test_function=test_adaptive_threshold,
        iterations=100
    )

    # Get recommended improvements
    improvements = ut.recommend_improvements(area="card_detection", top_k=5)
"""

import json
import os
import time
import uuid
import hashlib
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import logging

log = logging.getLogger(__name__)

# Base directory
ULTRATHINK_DIR = Path("/Users/sebastian/Developer/Gamble/sys_core/claude_brain_data/ultrathink")


class ObservationType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ANOMALY = "anomaly"
    PERFORMANCE = "performance"
    ERROR = "error"
    PATTERN = "pattern"


class HypothesisStatus(Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


@dataclass
class Observation:
    """A single observation from a Claude session"""
    id: str
    category: str
    event: str
    type: ObservationType
    context: Dict[str, Any]
    outcome: str
    session_id: str
    timestamp: float
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d['type'] = self.type.value
        return d

    @classmethod
    def from_dict(cls, d):
        d['type'] = ObservationType(d['type'])
        return cls(**d)


@dataclass
class Pattern:
    """A detected pattern across observations"""
    id: str
    category: str
    name: str
    description: str
    observations: List[str]  # Observation IDs
    frequency: int
    confidence: float
    first_seen: float
    last_seen: float
    conditions: Dict[str, Any]  # When this pattern occurs
    correlations: Dict[str, float]  # What correlates with this pattern

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class Hypothesis:
    """A hypothesis about how to improve the system"""
    id: str
    category: str
    title: str
    description: str
    based_on: List[str]  # Pattern IDs that led to this hypothesis
    proposed_change: str
    expected_improvement: float  # 0.0 to 1.0
    status: HypothesisStatus
    created_at: float
    tested_at: Optional[float]
    test_results: Optional[Dict[str, Any]]
    votes: int

    def to_dict(self):
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d):
        d['status'] = HypothesisStatus(d['status'])
        return cls(**d)


@dataclass
class Experiment:
    """An experiment to test a hypothesis"""
    id: str
    hypothesis_id: str
    name: str
    description: str
    baseline_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    improvement: Dict[str, float]
    sample_size: int
    started_at: float
    completed_at: Optional[float]
    conclusion: Optional[str]
    success: Optional[bool]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class PatternDetector:
    """Detects patterns in observations"""

    def __init__(self, observations_dir: Path):
        self.observations_dir = observations_dir

    def detect_patterns(self, category: str = None, min_frequency: int = 3) -> List[Pattern]:
        """Detect patterns in observations"""
        # Load observations
        observations = self._load_observations(category)

        if len(observations) < min_frequency:
            return []

        patterns = []

        # Group by event type
        event_groups = defaultdict(list)
        for obs in observations:
            event_groups[obs.event].append(obs)

        # Detect frequency patterns
        for event, obs_list in event_groups.items():
            if len(obs_list) >= min_frequency:
                pattern = self._create_pattern_from_event_group(event, obs_list)
                patterns.append(pattern)

        # Detect correlation patterns
        correlation_patterns = self._detect_correlations(observations)
        patterns.extend(correlation_patterns)

        # Detect time-based patterns
        time_patterns = self._detect_time_patterns(observations)
        patterns.extend(time_patterns)

        return patterns

    def _load_observations(self, category: str = None) -> List[Observation]:
        observations = []
        for filepath in self.observations_dir.glob("*.json"):
            with open(filepath) as f:
                obs = Observation.from_dict(json.load(f))
            if category and obs.category != category:
                continue
            observations.append(obs)
        return observations

    def _create_pattern_from_event_group(self, event: str, obs_list: List[Observation]) -> Pattern:
        """Create a pattern from a group of similar observations"""
        # Find common context elements
        common_context = {}
        if obs_list:
            first_context = obs_list[0].context
            for key in first_context:
                values = [obs.context.get(key) for obs in obs_list if key in obs.context]
                if len(set(str(v) for v in values)) == 1:  # All same value
                    common_context[key] = values[0]

        return Pattern(
            id=str(uuid.uuid4())[:8],
            category=obs_list[0].category,
            name=f"Repeated: {event}",
            description=f"Event '{event}' occurred {len(obs_list)} times",
            observations=[obs.id for obs in obs_list],
            frequency=len(obs_list),
            confidence=min(0.9, len(obs_list) / 10),  # More observations = more confidence
            first_seen=min(obs.timestamp for obs in obs_list),
            last_seen=max(obs.timestamp for obs in obs_list),
            conditions=common_context,
            correlations={}
        )

    def _detect_correlations(self, observations: List[Observation]) -> List[Pattern]:
        """Detect correlations between events and outcomes"""
        patterns = []

        # Group by outcome
        outcome_groups = defaultdict(list)
        for obs in observations:
            outcome_groups[obs.outcome].append(obs)

        # Look for common conditions leading to each outcome
        for outcome, obs_list in outcome_groups.items():
            if len(obs_list) >= 3:
                # Find metrics that correlate with this outcome
                metric_values = defaultdict(list)
                for obs in obs_list:
                    for metric, value in obs.metrics.items():
                        metric_values[metric].append(value)

                correlations = {}
                for metric, values in metric_values.items():
                    if len(values) >= 3:
                        avg = statistics.mean(values)
                        correlations[metric] = avg

                if correlations:
                    patterns.append(Pattern(
                        id=str(uuid.uuid4())[:8],
                        category=obs_list[0].category,
                        name=f"Correlated: {outcome}",
                        description=f"Found metrics correlated with outcome '{outcome}'",
                        observations=[obs.id for obs in obs_list],
                        frequency=len(obs_list),
                        confidence=min(0.8, len(obs_list) / 15),
                        first_seen=min(obs.timestamp for obs in obs_list),
                        last_seen=max(obs.timestamp for obs in obs_list),
                        conditions={},
                        correlations=correlations
                    ))

        return patterns

    def _detect_time_patterns(self, observations: List[Observation]) -> List[Pattern]:
        """Detect time-based patterns (e.g., failures at certain times)"""
        patterns = []

        # Sort by time
        sorted_obs = sorted(observations, key=lambda x: x.timestamp)

        # Look for bursts (many events in short time)
        window_seconds = 60
        for i, obs in enumerate(sorted_obs):
            burst = [obs]
            for j in range(i + 1, len(sorted_obs)):
                if sorted_obs[j].timestamp - obs.timestamp <= window_seconds:
                    burst.append(sorted_obs[j])
                else:
                    break

            if len(burst) >= 5:  # 5+ events in 60 seconds = burst
                patterns.append(Pattern(
                    id=str(uuid.uuid4())[:8],
                    category=burst[0].category,
                    name="Burst detected",
                    description=f"Detected {len(burst)} events in {window_seconds}s window",
                    observations=[o.id for o in burst],
                    frequency=len(burst),
                    confidence=0.7,
                    first_seen=burst[0].timestamp,
                    last_seen=burst[-1].timestamp,
                    conditions={'window_seconds': window_seconds},
                    correlations={'burst_size': len(burst)}
                ))
                break  # One burst pattern is enough

        return patterns


class HypothesisGenerator:
    """Generates improvement hypotheses from patterns"""

    # Known improvement strategies - map keywords to solutions
    STRATEGIES = {
        'template': [
            ("Increase threshold", "Use adaptive threshold chain instead of fixed value", 0.7),
            ("Update template", "Capture fresh template from current UI", 0.8),
            ("Add normalization", "Normalize brightness/contrast before matching", 0.6),
        ],
        'card': [
            ("Adaptive threshold", "Use multiple thresholds [0.15, 0.20, 0.25, 0.30, 0.35]", 0.8),
            ("Template normalization", "Resize all templates to consistent size", 0.7),
            ("Position-based fallback", "Use known card positions when template fails", 0.75),
        ],
        'button': [
            ("Color detection", "Find buttons by HSV color instead of fixed coordinates", 0.85),
            ("Add verification", "Verify button was clicked by checking UI state change", 0.7),
            ("Retry mechanism", "Retry click if button still visible after action", 0.65),
        ],
        'table': [
            ("Window API fallback", "Use macOS window API instead of template matching", 0.9),
            ("Increase threshold", "Try higher thresholds [0.01, 0.05, 0.10, 0.15, 0.20, 0.25]", 0.7),
            ("Green felt detection", "Find table by detecting green felt color", 0.6),
        ],
        'click': [
            ("Coordinate verification", "Verify coordinates are within expected bounds", 0.6),
            ("Retina scaling check", "Ensure proper 2x scaling for Retina displays", 0.8),
            ("Focus window first", "Focus the target window before clicking", 0.7),
        ],
        'failed': [
            ("Add logging", "Add detailed logging to diagnose failure cause", 0.5),
            ("Retry with backoff", "Implement exponential backoff retry mechanism", 0.6),
            ("Fallback strategy", "Implement fallback when primary method fails", 0.7),
        ],
        'repeated': [
            ("Add caching", "Cache results to avoid repeated operations", 0.6),
            ("Batch processing", "Batch multiple operations together", 0.5),
            ("Debounce mechanism", "Add debouncing to prevent rapid repeats", 0.55),
        ],
    }

    def __init__(self, patterns_dir: Path):
        self.patterns_dir = patterns_dir

    def generate(self, patterns: List[Pattern]) -> List[Hypothesis]:
        """Generate hypotheses from detected patterns"""
        hypotheses = []
        seen = set()  # Avoid duplicate hypotheses

        for pattern in patterns:
            # Look for matching strategies based on keywords
            search_text = f"{pattern.name} {pattern.description} {pattern.category}".lower()

            for keyword, strategies in self.STRATEGIES.items():
                if keyword.lower() in search_text:
                    for title, description, expected_improvement in strategies:
                        # Create unique key to avoid duplicates
                        key = f"{pattern.category}_{title}"
                        if key in seen:
                            continue
                        seen.add(key)

                        hypothesis = Hypothesis(
                            id=str(uuid.uuid4())[:8],
                            category=pattern.category,
                            title=title,
                            description=description,
                            based_on=[pattern.id],
                            proposed_change=description,
                            expected_improvement=expected_improvement * pattern.confidence,
                            status=HypothesisStatus.PROPOSED,
                            created_at=time.time(),
                            tested_at=None,
                            test_results=None,
                            votes=0
                        )
                        hypotheses.append(hypothesis)

            # Generate hypothesis from correlations
            if pattern.correlations:
                for metric, avg_value in pattern.correlations.items():
                    hypothesis = Hypothesis(
                        id=str(uuid.uuid4())[:8],
                        category=pattern.category,
                        title=f"Adjust {metric}",
                        description=f"Pattern shows {metric} averages {avg_value:.2f} when "
                                   f"'{pattern.name}' occurs. Consider adjusting this threshold.",
                        based_on=[pattern.id],
                        proposed_change=f"Modify {metric} threshold based on observed average",
                        expected_improvement=0.5 * pattern.confidence,
                        status=HypothesisStatus.PROPOSED,
                        created_at=time.time(),
                        tested_at=None,
                        test_results=None,
                        votes=0
                    )
                    hypotheses.append(hypothesis)

        return hypotheses


class UltraThinkCore:
    """
    The core UltraThink engine.

    Coordinates observation, pattern detection, hypothesis generation,
    experimentation, and knowledge consolidation.
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"ultrathink_{uuid.uuid4().hex[:6]}"

        # Create directories
        self.observations_dir = ULTRATHINK_DIR / "observations"
        self.patterns_dir = ULTRATHINK_DIR / "patterns"
        self.hypotheses_dir = ULTRATHINK_DIR / "hypotheses"
        self.experiments_dir = ULTRATHINK_DIR / "experiments"
        self.knowledge_dir = ULTRATHINK_DIR / "knowledge"

        for d in [self.observations_dir, self.patterns_dir, self.hypotheses_dir,
                  self.experiments_dir, self.knowledge_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.pattern_detector = PatternDetector(self.observations_dir)
        self.hypothesis_generator = HypothesisGenerator(self.patterns_dir)

        # Load meta info
        self.meta_file = ULTRATHINK_DIR / "meta.json"
        self._load_meta()

        log.info(f"UltraThink initialized: session={self.session_id}")

    def _load_meta(self):
        if self.meta_file.exists():
            with open(self.meta_file) as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                'total_observations': 0,
                'total_patterns': 0,
                'total_hypotheses': 0,
                'total_experiments': 0,
                'validated_hypotheses': 0,
                'implemented_improvements': 0,
                'categories': {},
                'sessions': [],
                'created_at': time.time(),
                'last_updated': time.time()
            }
            self._save_meta()

    def _save_meta(self):
        self.meta['last_updated'] = time.time()
        with open(self.meta_file, 'w') as f:
            json.dump(self.meta, f, indent=2)

    def observe(self, category: str, event: str, context: Dict[str, Any],
                outcome: str, obs_type: ObservationType = ObservationType.FAILURE,
                metrics: Dict[str, float] = None) -> Observation:
        """
        Record an observation from a Claude session.

        This is the main input to UltraThink - observations feed the
        pattern detection and hypothesis generation pipeline.
        """
        obs = Observation(
            id=str(uuid.uuid4())[:8],
            category=category,
            event=event,
            type=obs_type,
            context=context,
            outcome=outcome,
            session_id=self.session_id,
            timestamp=time.time(),
            metrics=metrics or {}
        )

        # Save observation
        filepath = self.observations_dir / f"{category}_{obs.id}.json"
        with open(filepath, 'w') as f:
            json.dump(obs.to_dict(), f, indent=2)

        # Update meta
        self.meta['total_observations'] += 1
        if category not in self.meta['categories']:
            self.meta['categories'][category] = {'observations': 0, 'patterns': 0, 'hypotheses': 0}
        self.meta['categories'][category]['observations'] += 1
        if self.session_id not in self.meta['sessions']:
            self.meta['sessions'].append(self.session_id)
        self._save_meta()

        log.info(f"UltraThink: Observed [{obs_type.value}] {category}/{event}: {outcome}")
        return obs

    def detect_patterns(self, category: str = None, min_frequency: int = 3) -> List[Pattern]:
        """
        Run pattern detection on accumulated observations.

        Call this periodically or when you have accumulated enough observations.
        """
        patterns = self.pattern_detector.detect_patterns(category, min_frequency)

        # Save new patterns
        for pattern in patterns:
            filepath = self.patterns_dir / f"{pattern.category}_{pattern.id}.json"
            if not filepath.exists():  # Don't overwrite existing patterns
                with open(filepath, 'w') as f:
                    json.dump(pattern.to_dict(), f, indent=2)
                self.meta['total_patterns'] += 1
                self.meta['categories'].setdefault(pattern.category, {})['patterns'] = \
                    self.meta['categories'].get(pattern.category, {}).get('patterns', 0) + 1

        self._save_meta()
        log.info(f"UltraThink: Detected {len(patterns)} patterns")
        return patterns

    def hypothesize(self, category: str = None) -> List[Hypothesis]:
        """
        Generate improvement hypotheses based on detected patterns.
        """
        # First detect patterns
        patterns = self.detect_patterns(category)

        # Generate hypotheses
        hypotheses = self.hypothesis_generator.generate(patterns)

        # Save hypotheses
        for hyp in hypotheses:
            filepath = self.hypotheses_dir / f"{hyp.category}_{hyp.id}.json"
            with open(filepath, 'w') as f:
                json.dump(hyp.to_dict(), f, indent=2)
            self.meta['total_hypotheses'] += 1
            self.meta['categories'].setdefault(hyp.category, {})['hypotheses'] = \
                self.meta['categories'].get(hyp.category, {}).get('hypotheses', 0) + 1

        self._save_meta()
        log.info(f"UltraThink: Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def experiment(self, hypothesis_id: str,
                   test_function: Callable[[], Tuple[bool, Dict[str, float]]],
                   iterations: int = 10,
                   name: str = None) -> Experiment:
        """
        Run an experiment to test a hypothesis.

        Args:
            hypothesis_id: ID of hypothesis to test
            test_function: Function that returns (success: bool, metrics: dict)
            iterations: Number of test iterations
            name: Optional experiment name

        Returns:
            Experiment with results
        """
        # Load hypothesis
        hypothesis = None
        for filepath in self.hypotheses_dir.glob(f"*_{hypothesis_id}.json"):
            with open(filepath) as f:
                hypothesis = Hypothesis.from_dict(json.load(f))
            break

        if not hypothesis:
            raise ValueError(f"Hypothesis {hypothesis_id} not found")

        # Update hypothesis status
        hypothesis.status = HypothesisStatus.TESTING

        # Create experiment
        experiment = Experiment(
            id=str(uuid.uuid4())[:8],
            hypothesis_id=hypothesis_id,
            name=name or f"Test: {hypothesis.title}",
            description=hypothesis.description,
            baseline_metrics={},
            test_metrics={},
            improvement={},
            sample_size=iterations,
            started_at=time.time(),
            completed_at=None,
            conclusion=None,
            success=None
        )

        # Run tests
        successes = 0
        all_metrics = defaultdict(list)

        for i in range(iterations):
            try:
                success, metrics = test_function()
                if success:
                    successes += 1
                for key, value in metrics.items():
                    all_metrics[key].append(value)
            except Exception as e:
                log.warning(f"Experiment iteration {i} failed: {e}")

        # Calculate results
        experiment.test_metrics = {
            'success_rate': successes / iterations,
            **{key: statistics.mean(values) for key, values in all_metrics.items() if values}
        }
        experiment.completed_at = time.time()
        experiment.success = experiment.test_metrics['success_rate'] >= 0.7

        # Update hypothesis
        hypothesis.status = HypothesisStatus.VALIDATED if experiment.success else HypothesisStatus.REJECTED
        hypothesis.tested_at = time.time()
        hypothesis.test_results = experiment.test_metrics

        # Save results
        exp_filepath = self.experiments_dir / f"{experiment.id}.json"
        with open(exp_filepath, 'w') as f:
            json.dump(experiment.to_dict(), f, indent=2)

        # Update hypothesis file
        for filepath in self.hypotheses_dir.glob(f"*_{hypothesis_id}.json"):
            with open(filepath, 'w') as f:
                json.dump(hypothesis.to_dict(), f, indent=2)

        # Update meta
        self.meta['total_experiments'] += 1
        if experiment.success:
            self.meta['validated_hypotheses'] += 1
        self._save_meta()

        log.info(f"UltraThink: Experiment completed - {'SUCCESS' if experiment.success else 'FAILED'}")
        return experiment

    def recommend_improvements(self, area: str = None, top_k: int = 5) -> List[Hypothesis]:
        """
        Get top recommended improvements based on hypotheses.

        Returns validated hypotheses sorted by expected improvement.
        """
        hypotheses = []

        for filepath in self.hypotheses_dir.glob("*.json"):
            with open(filepath) as f:
                hyp = Hypothesis.from_dict(json.load(f))

            if area and hyp.category != area:
                continue

            # Prefer validated hypotheses, then by expected improvement
            hypotheses.append(hyp)

        # Sort: validated first, then by expected improvement
        def sort_key(h):
            status_priority = {
                HypothesisStatus.VALIDATED: 0,
                HypothesisStatus.PROPOSED: 1,
                HypothesisStatus.TESTING: 2,
                HypothesisStatus.REJECTED: 3,
                HypothesisStatus.IMPLEMENTED: 4  # Already done
            }
            return (status_priority.get(h.status, 99), -h.expected_improvement)

        hypotheses.sort(key=sort_key)
        return hypotheses[:top_k]

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of UltraThink state"""
        return {
            'session_id': self.session_id,
            'total_observations': self.meta['total_observations'],
            'total_patterns': self.meta['total_patterns'],
            'total_hypotheses': self.meta['total_hypotheses'],
            'total_experiments': self.meta['total_experiments'],
            'validated_hypotheses': self.meta['validated_hypotheses'],
            'implemented_improvements': self.meta['implemented_improvements'],
            'categories': self.meta['categories'],
            'contributing_sessions': len(self.meta['sessions']),
            'created': datetime.fromtimestamp(self.meta['created_at']).isoformat(),
            'last_updated': datetime.fromtimestamp(self.meta['last_updated']).isoformat()
        }

    def think(self, question: str, context: str = "") -> str:
        """
        Deep thinking about a question using accumulated knowledge.

        Synthesizes observations, patterns, and hypotheses to provide
        informed answers.
        """
        response_parts = [
            "# UltraThink Analysis",
            f"**Question:** {question}",
            f"**Context:** {context}" if context else "",
            ""
        ]

        # Get relevant patterns
        all_patterns = []
        for filepath in self.patterns_dir.glob("*.json"):
            with open(filepath) as f:
                pattern = Pattern.from_dict(json.load(f))
            if context.lower() in pattern.category.lower() or \
               context.lower() in pattern.name.lower():
                all_patterns.append(pattern)

        if all_patterns:
            response_parts.append("## Relevant Patterns")
            for p in sorted(all_patterns, key=lambda x: -x.confidence)[:5]:
                response_parts.append(f"- **{p.name}** (confidence: {p.confidence:.0%})")
                response_parts.append(f"  {p.description}")
            response_parts.append("")

        # Get relevant hypotheses
        recommendations = self.recommend_improvements(area=context if context else None, top_k=5)
        if recommendations:
            response_parts.append("## Recommended Improvements")
            for h in recommendations:
                status_emoji = {
                    HypothesisStatus.VALIDATED: "[VALIDATED]",
                    HypothesisStatus.PROPOSED: "[PROPOSED]",
                    HypothesisStatus.TESTING: "[TESTING]",
                    HypothesisStatus.REJECTED: "[REJECTED]",
                    HypothesisStatus.IMPLEMENTED: "[DONE]"
                }.get(h.status, "")
                response_parts.append(f"- **{h.title}** {status_emoji}")
                response_parts.append(f"  {h.description}")
                response_parts.append(f"  Expected improvement: {h.expected_improvement:.0%}")
            response_parts.append("")

        # Get observation stats
        obs_count = self.meta['total_observations']
        if obs_count > 0:
            response_parts.append("## Observation Summary")
            response_parts.append(f"- Total observations: {obs_count}")
            response_parts.append(f"- Patterns detected: {self.meta['total_patterns']}")
            response_parts.append(f"- Hypotheses generated: {self.meta['total_hypotheses']}")
            response_parts.append(f"- Experiments run: {self.meta['total_experiments']}")

        return "\n".join(response_parts)


# Convenience functions
_core: Optional[UltraThinkCore] = None

def get_core(session_id: str = None) -> UltraThinkCore:
    global _core
    if _core is None:
        _core = UltraThinkCore(session_id)
    return _core

def observe(category: str, event: str, context: Dict, outcome: str, **kwargs):
    """Quick observe function"""
    return get_core().observe(category, event, context, outcome, **kwargs)

def think(question: str, context: str = "") -> str:
    """Quick think function"""
    return get_core().think(question, context)

def recommend(area: str = None, top_k: int = 5) -> List[Hypothesis]:
    """Quick recommendations function"""
    return get_core().recommend_improvements(area, top_k)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("ULTRATHINK - Advanced Meta-Learning System")
    print("=" * 60)

    # Initialize
    ut = UltraThinkCore(session_id="test_ultrathink")

    # Add some observations
    print("\n1. Recording observations...")
    ut.observe(
        category="card_detection",
        event="template_match_failed",
        context={"score": 0.36, "threshold": 0.15, "template": "Ac"},
        outcome="card_not_detected",
        metrics={"match_score": 0.36}
    )

    ut.observe(
        category="card_detection",
        event="template_match_failed",
        context={"score": 0.32, "threshold": 0.15, "template": "Kh"},
        outcome="card_not_detected",
        metrics={"match_score": 0.32}
    )

    ut.observe(
        category="card_detection",
        event="template_match_failed",
        context={"score": 0.38, "threshold": 0.15, "template": "Qs"},
        outcome="card_not_detected",
        metrics={"match_score": 0.38}
    )

    ut.observe(
        category="button_detection",
        event="button_click_missed",
        context={"button": "fold", "x": 557, "y": 1254},
        outcome="action_not_executed",
        metrics={"y_offset": -150}
    )

    # Detect patterns
    print("\n2. Detecting patterns...")
    patterns = ut.detect_patterns()
    for p in patterns:
        print(f"   - {p.name}: {p.description}")

    # Generate hypotheses
    print("\n3. Generating hypotheses...")
    hypotheses = ut.hypothesize()
    for h in hypotheses:
        print(f"   - {h.title}: {h.description[:60]}...")

    # Get recommendations
    print("\n4. Top recommendations:")
    recommendations = ut.recommend_improvements(top_k=3)
    for r in recommendations:
        print(f"   - [{r.status.value}] {r.title} (expected: {r.expected_improvement:.0%})")

    # Think about a question
    print("\n5. UltraThink analysis:")
    analysis = ut.think("How to improve card detection?", context="card_detection")
    print(analysis)

    # Summary
    print("\n6. Summary:")
    print(json.dumps(ut.get_summary(), indent=2))
