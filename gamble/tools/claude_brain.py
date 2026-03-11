"""
CLAUDE BRAIN - Inter-Session Communication & Ultrathink System

This module enables Claude sessions to:
1. Communicate with each other via shared message queue
2. Share observations, insights, and improvements
3. Build accumulated knowledge (ultrathink) across sessions
4. Coordinate on complex multi-session tasks

Architecture:
    +-----------------+     +-----------------+     +-----------------+
    | Claude Session  |     | Claude Session  |     | Claude Session  |
    |    (Agent 1)    |     |    (Agent 2)    |     |    (Agent 3)    |
    +-------+---------+     +--------+--------+     +--------+--------+
            |                        |                       |
            v                        v                       v
    +---------------------------------------------------------------+
    |                    MESSAGE BUS (File-based)                   |
    |  - Inbox per session                                          |
    |  - Broadcast channel                                          |
    |  - Priority queue                                             |
    +---------------------------------------------------------------+
            |                        |                       |
            v                        v                       v
    +---------------------------------------------------------------+
    |                      ULTRATHINK LAYER                         |
    |  - Accumulated insights                                       |
    |  - Pattern recognition across sessions                        |
    |  - Improvement suggestions                                    |
    |  - Meta-learning                                             |
    +---------------------------------------------------------------+
            |
            v
    +---------------------------------------------------------------+
    |                     KNOWLEDGE BASE                            |
    |  - Bot strategy improvements                                  |
    |  - Bug reports and fixes                                      |
    |  - Performance metrics                                        |
    |  - Calibration data                                          |
    +---------------------------------------------------------------+

Usage:
    from gamble.tools.claude_brain import ClaudeBrain, UltraThink

    # Initialize brain for this session
    brain = ClaudeBrain(session_id="claude_poker_1")

    # Send message to other sessions
    brain.broadcast("Found pattern: GGPoker changes button Y position after update")

    # Get accumulated knowledge
    insights = brain.ultrathink.get_insights("button_detection")

    # Add improvement suggestion
    brain.ultrathink.suggest_improvement(
        area="card_detection",
        problem="Templates fail at night due to screen brightness",
        solution="Add adaptive brightness normalization before template matching"
    )

    # Check for messages from other sessions
    messages = brain.receive()
    for msg in messages:
        print(f"From {msg['from']}: {msg['content']}")
"""

import json
import os
import time
import uuid
import hashlib
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

log = logging.getLogger(__name__)

# Base directory for all Claude brain data
BRAIN_DIR = Path("/Users/sebastian/Developer/Gamble/gamble/claude_brain_data")


class MessagePriority(Enum):
    CRITICAL = 0    # Emergency - immediate action needed
    HIGH = 1        # Important insight or bug
    NORMAL = 2      # Standard communication
    LOW = 3         # FYI, background info


class MessageType(Enum):
    BROADCAST = "broadcast"         # To all sessions
    DIRECT = "direct"               # To specific session
    INSIGHT = "insight"             # Knowledge contribution
    IMPROVEMENT = "improvement"     # Improvement suggestion
    BUG_REPORT = "bug_report"       # Bug discovered
    QUESTION = "question"           # Asking other sessions
    ANSWER = "answer"               # Response to question
    STATUS = "status"               # Session status update
    EMERGENCY = "emergency"         # Critical alert


@dataclass
class Message:
    id: str
    type: MessageType
    priority: MessagePriority
    from_session: str
    to_session: Optional[str]  # None for broadcast
    content: str
    data: Dict[str, Any]
    timestamp: float
    expires: Optional[float]  # None = never expires

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type.value,
            'priority': self.priority.value,
            'from_session': self.from_session,
            'to_session': self.to_session,
            'content': self.content,
            'data': self.data,
            'timestamp': self.timestamp,
            'expires': self.expires
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d['id'],
            type=MessageType(d['type']),
            priority=MessagePriority(d['priority']),
            from_session=d['from_session'],
            to_session=d.get('to_session'),
            content=d['content'],
            data=d.get('data', {}),
            timestamp=d['timestamp'],
            expires=d.get('expires')
        )


@dataclass
class Insight:
    """A piece of accumulated knowledge"""
    id: str
    area: str  # e.g., "card_detection", "button_clicking", "template_matching"
    title: str
    content: str
    evidence: List[str]  # Supporting observations
    confidence: float  # 0.0 to 1.0
    created_by: str
    created_at: float
    updated_at: float
    votes: int  # Other sessions can upvote
    tags: List[str]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class Improvement:
    """A suggested improvement to the system"""
    id: str
    area: str
    problem: str
    solution: str
    code_changes: Optional[str]  # Suggested code
    priority: int
    status: str  # "proposed", "accepted", "implemented", "rejected"
    created_by: str
    created_at: float
    implemented_at: Optional[float]
    votes: int

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class UltraThink:
    """
    The accumulated knowledge and thinking layer.

    Persists insights, improvements, and patterns across all Claude sessions.
    """

    def __init__(self):
        self.insights_dir = BRAIN_DIR / "insights"
        self.improvements_dir = BRAIN_DIR / "improvements"
        self.patterns_dir = BRAIN_DIR / "patterns"
        self.meta_file = BRAIN_DIR / "ultrathink_meta.json"

        self._ensure_dirs()
        self._load_meta()

    def _ensure_dirs(self):
        self.insights_dir.mkdir(parents=True, exist_ok=True)
        self.improvements_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

    def _load_meta(self):
        if self.meta_file.exists():
            with open(self.meta_file) as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                'total_insights': 0,
                'total_improvements': 0,
                'sessions_contributed': [],
                'areas': {},
                'last_updated': time.time()
            }
            self._save_meta()

    def _save_meta(self):
        self.meta['last_updated'] = time.time()
        with open(self.meta_file, 'w') as f:
            json.dump(self.meta, f, indent=2)

    def add_insight(self, area: str, title: str, content: str,
                    evidence: List[str] = None, tags: List[str] = None,
                    session_id: str = "unknown") -> Insight:
        """Add a new insight to the knowledge base"""
        insight = Insight(
            id=str(uuid.uuid4())[:8],
            area=area,
            title=title,
            content=content,
            evidence=evidence or [],
            confidence=0.5,  # Start at neutral
            created_by=session_id,
            created_at=time.time(),
            updated_at=time.time(),
            votes=0,
            tags=tags or []
        )

        # Save insight
        filepath = self.insights_dir / f"{area}_{insight.id}.json"
        with open(filepath, 'w') as f:
            json.dump(insight.to_dict(), f, indent=2)

        # Update meta
        self.meta['total_insights'] += 1
        if session_id not in self.meta['sessions_contributed']:
            self.meta['sessions_contributed'].append(session_id)
        if area not in self.meta['areas']:
            self.meta['areas'][area] = {'insights': 0, 'improvements': 0}
        self.meta['areas'][area]['insights'] += 1
        self._save_meta()

        log.info(f"UltraThink: Added insight '{title}' to area '{area}'")
        return insight

    def get_insights(self, area: str = None, min_confidence: float = 0.0) -> List[Insight]:
        """Get all insights, optionally filtered by area"""
        insights = []

        for filepath in self.insights_dir.glob("*.json"):
            with open(filepath) as f:
                insight = Insight.from_dict(json.load(f))

            if area and not filepath.name.startswith(area):
                continue
            if insight.confidence < min_confidence:
                continue

            insights.append(insight)

        # Sort by confidence then by votes
        insights.sort(key=lambda x: (x.confidence, x.votes), reverse=True)
        return insights

    def suggest_improvement(self, area: str, problem: str, solution: str,
                           code_changes: str = None, priority: int = 2,
                           session_id: str = "unknown") -> Improvement:
        """Suggest an improvement to the system"""
        improvement = Improvement(
            id=str(uuid.uuid4())[:8],
            area=area,
            problem=problem,
            solution=solution,
            code_changes=code_changes,
            priority=priority,
            status="proposed",
            created_by=session_id,
            created_at=time.time(),
            implemented_at=None,
            votes=0
        )

        # Save improvement
        filepath = self.improvements_dir / f"{area}_{improvement.id}.json"
        with open(filepath, 'w') as f:
            json.dump(improvement.to_dict(), f, indent=2)

        # Update meta
        self.meta['total_improvements'] += 1
        if area not in self.meta['areas']:
            self.meta['areas'][area] = {'insights': 0, 'improvements': 0}
        self.meta['areas'][area]['improvements'] += 1
        self._save_meta()

        log.info(f"UltraThink: Improvement suggested for '{area}': {problem[:50]}...")
        return improvement

    def get_improvements(self, area: str = None, status: str = None) -> List[Improvement]:
        """Get all improvements, optionally filtered"""
        improvements = []

        for filepath in self.improvements_dir.glob("*.json"):
            with open(filepath) as f:
                improvement = Improvement.from_dict(json.load(f))

            if area and improvement.area != area:
                continue
            if status and improvement.status != status:
                continue

            improvements.append(improvement)

        # Sort by priority then by votes
        improvements.sort(key=lambda x: (x.priority, -x.votes))
        return improvements

    def vote_insight(self, insight_id: str, upvote: bool = True):
        """Vote on an insight"""
        for filepath in self.insights_dir.glob(f"*_{insight_id}.json"):
            with open(filepath) as f:
                insight = Insight.from_dict(json.load(f))

            insight.votes += 1 if upvote else -1
            insight.confidence = min(1.0, max(0.0, 0.5 + insight.votes * 0.1))
            insight.updated_at = time.time()

            with open(filepath, 'w') as f:
                json.dump(insight.to_dict(), f, indent=2)

            log.info(f"UltraThink: Voted {'up' if upvote else 'down'} on insight {insight_id}")
            return insight

        return None

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of accumulated knowledge"""
        return {
            'total_insights': self.meta['total_insights'],
            'total_improvements': self.meta['total_improvements'],
            'contributing_sessions': len(self.meta['sessions_contributed']),
            'areas': self.meta['areas'],
            'last_updated': datetime.fromtimestamp(self.meta['last_updated']).isoformat()
        }

    def think(self, context: str, question: str) -> str:
        """
        Ultra-think: Use accumulated knowledge to reason about a question.

        This method searches relevant insights and improvements to provide
        informed answers based on collective Claude session knowledge.
        """
        # Find relevant insights
        relevant_insights = []
        for insight in self.get_insights():
            if any(word in insight.content.lower() or word in insight.title.lower()
                   for word in context.lower().split()):
                relevant_insights.append(insight)

        if not relevant_insights:
            return f"No accumulated knowledge found for context: {context}"

        # Build response from accumulated knowledge
        response_parts = [
            f"## UltraThink Analysis",
            f"Context: {context}",
            f"Question: {question}",
            f"",
            f"### Relevant Knowledge ({len(relevant_insights)} insights found):",
            ""
        ]

        for insight in relevant_insights[:5]:  # Top 5 most relevant
            response_parts.append(f"**{insight.title}** (confidence: {insight.confidence:.0%})")
            response_parts.append(f"  {insight.content}")
            response_parts.append("")

        # Check for relevant improvements
        relevant_improvements = self.get_improvements(status="proposed")
        if relevant_improvements:
            response_parts.append("### Pending Improvements:")
            for imp in relevant_improvements[:3]:
                response_parts.append(f"- [{imp.area}] {imp.problem[:50]}...")

        return "\n".join(response_parts)


class ClaudeBrain:
    """
    The main inter-session communication hub.

    Each Claude session creates its own ClaudeBrain instance with a unique session_id.
    Messages are stored in files and can be read by other sessions.
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"claude_{uuid.uuid4().hex[:6]}"
        self.messages_dir = BRAIN_DIR / "messages"
        self.inbox_dir = self.messages_dir / "inbox" / self.session_id
        self.broadcast_dir = self.messages_dir / "broadcast"
        self.sessions_file = BRAIN_DIR / "active_sessions.json"

        self._ensure_dirs()
        self._register_session()

        # Shared ultrathink layer
        self.ultrathink = UltraThink()

        log.info(f"ClaudeBrain initialized: session={self.session_id}")

    def _ensure_dirs(self):
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.broadcast_dir.mkdir(parents=True, exist_ok=True)

    def _register_session(self):
        """Register this session as active"""
        sessions = self._load_sessions()
        sessions[self.session_id] = {
            'started': time.time(),
            'last_seen': time.time(),
            'status': 'active'
        }
        self._save_sessions(sessions)

    def _load_sessions(self) -> Dict:
        if self.sessions_file.exists():
            with open(self.sessions_file) as f:
                return json.load(f)
        return {}

    def _save_sessions(self, sessions: Dict):
        with open(self.sessions_file, 'w') as f:
            json.dump(sessions, f, indent=2)

    def heartbeat(self):
        """Update this session's last_seen timestamp"""
        sessions = self._load_sessions()
        if self.session_id in sessions:
            sessions[self.session_id]['last_seen'] = time.time()
            self._save_sessions(sessions)

    def get_active_sessions(self, timeout_seconds: int = 300) -> List[str]:
        """Get list of active sessions (seen in last N seconds)"""
        sessions = self._load_sessions()
        cutoff = time.time() - timeout_seconds
        return [
            sid for sid, info in sessions.items()
            if info.get('last_seen', 0) > cutoff and sid != self.session_id
        ]

    def send(self, to_session: str, content: str,
             msg_type: MessageType = MessageType.DIRECT,
             priority: MessagePriority = MessagePriority.NORMAL,
             data: Dict = None, ttl_seconds: int = None) -> Message:
        """Send a message to a specific session"""
        msg = Message(
            id=str(uuid.uuid4())[:8],
            type=msg_type,
            priority=priority,
            from_session=self.session_id,
            to_session=to_session,
            content=content,
            data=data or {},
            timestamp=time.time(),
            expires=time.time() + ttl_seconds if ttl_seconds else None
        )

        # Write to recipient's inbox
        inbox = self.messages_dir / "inbox" / to_session
        inbox.mkdir(parents=True, exist_ok=True)
        filepath = inbox / f"{msg.priority.value}_{msg.id}.json"

        with open(filepath, 'w') as f:
            json.dump(msg.to_dict(), f, indent=2)

        log.info(f"ClaudeBrain: Sent message to {to_session}: {content[:50]}...")
        return msg

    def broadcast(self, content: str,
                  msg_type: MessageType = MessageType.BROADCAST,
                  priority: MessagePriority = MessagePriority.NORMAL,
                  data: Dict = None, ttl_seconds: int = 3600) -> Message:
        """Broadcast a message to all sessions"""
        msg = Message(
            id=str(uuid.uuid4())[:8],
            type=msg_type,
            priority=priority,
            from_session=self.session_id,
            to_session=None,  # Broadcast
            content=content,
            data=data or {},
            timestamp=time.time(),
            expires=time.time() + ttl_seconds if ttl_seconds else None
        )

        # Write to broadcast directory
        filepath = self.broadcast_dir / f"{msg.priority.value}_{msg.id}.json"
        with open(filepath, 'w') as f:
            json.dump(msg.to_dict(), f, indent=2)

        log.info(f"ClaudeBrain: Broadcast message: {content[:50]}...")
        return msg

    def receive(self, include_broadcast: bool = True,
                delete_after_read: bool = True) -> List[Message]:
        """Receive all pending messages"""
        messages = []
        now = time.time()

        # Read from inbox
        for filepath in sorted(self.inbox_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    msg = Message.from_dict(json.load(f))

                # Check expiration
                if msg.expires and msg.expires < now:
                    filepath.unlink()
                    continue

                messages.append(msg)

                if delete_after_read:
                    filepath.unlink()
            except Exception as e:
                log.warning(f"Error reading message {filepath}: {e}")

        # Read from broadcast (don't delete broadcast messages)
        if include_broadcast:
            for filepath in sorted(self.broadcast_dir.glob("*.json")):
                try:
                    with open(filepath) as f:
                        msg = Message.from_dict(json.load(f))

                    # Skip own messages
                    if msg.from_session == self.session_id:
                        continue

                    # Check expiration
                    if msg.expires and msg.expires < now:
                        filepath.unlink()  # Clean up expired broadcasts
                        continue

                    messages.append(msg)
                except Exception as e:
                    log.warning(f"Error reading broadcast {filepath}: {e}")

        # Sort by priority then timestamp
        messages.sort(key=lambda m: (m.priority.value, m.timestamp))
        return messages

    def report_bug(self, area: str, description: str,
                   stacktrace: str = None,
                   steps_to_reproduce: List[str] = None):
        """Report a bug found during this session"""
        data = {
            'area': area,
            'description': description,
            'stacktrace': stacktrace,
            'steps_to_reproduce': steps_to_reproduce or [],
            'session_state': {
                'session_id': self.session_id,
                'time': datetime.now().isoformat()
            }
        }

        # Broadcast bug report
        self.broadcast(
            content=f"BUG FOUND in {area}: {description}",
            msg_type=MessageType.BUG_REPORT,
            priority=MessagePriority.HIGH,
            data=data,
            ttl_seconds=86400 * 7  # Keep for 7 days
        )

        # Add to ultrathink as insight
        self.ultrathink.add_insight(
            area=area,
            title=f"Bug: {description[:50]}",
            content=description,
            evidence=[stacktrace] if stacktrace else [],
            tags=['bug'],
            session_id=self.session_id
        )

    def ask(self, question: str, context: str = "") -> str:
        """
        Ask a question and get answer from ultrathink + broadcast to other sessions.
        """
        # First, check ultrathink for accumulated knowledge
        ultrathink_answer = self.ultrathink.think(context, question)

        # Broadcast question to other sessions
        self.broadcast(
            content=question,
            msg_type=MessageType.QUESTION,
            priority=MessagePriority.NORMAL,
            data={'context': context},
            ttl_seconds=3600
        )

        return ultrathink_answer

    def share_insight(self, area: str, title: str, content: str,
                      evidence: List[str] = None, tags: List[str] = None):
        """Share an insight with all sessions via ultrathink"""
        insight = self.ultrathink.add_insight(
            area=area,
            title=title,
            content=content,
            evidence=evidence,
            tags=tags,
            session_id=self.session_id
        )

        # Broadcast to other sessions
        self.broadcast(
            content=f"New insight: {title}",
            msg_type=MessageType.INSIGHT,
            priority=MessagePriority.NORMAL,
            data={'insight_id': insight.id, 'area': area},
            ttl_seconds=86400  # 24 hours
        )

        return insight

    def close(self):
        """Mark session as inactive"""
        sessions = self._load_sessions()
        if self.session_id in sessions:
            sessions[self.session_id]['status'] = 'closed'
            sessions[self.session_id]['closed_at'] = time.time()
            self._save_sessions(sessions)
        log.info(f"ClaudeBrain session {self.session_id} closed")


# Singleton brain instance for the current session
_brain: Optional[ClaudeBrain] = None

def get_brain(session_id: str = None) -> ClaudeBrain:
    """Get or create the brain for this session"""
    global _brain
    if _brain is None:
        _brain = ClaudeBrain(session_id)
    return _brain


# Quick access functions
def broadcast(message: str, priority: MessagePriority = MessagePriority.NORMAL):
    """Quick broadcast to all Claude sessions"""
    return get_brain().broadcast(message, priority=priority)

def share(area: str, title: str, content: str):
    """Quick share an insight"""
    return get_brain().share_insight(area, title, content)

def ask_all(question: str) -> str:
    """Quick ask using ultrathink"""
    return get_brain().ask(question)

def get_knowledge(area: str = None) -> List[Insight]:
    """Quick get accumulated knowledge"""
    return get_brain().ultrathink.get_insights(area)


if __name__ == "__main__":
    # Demo/test
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("CLAUDE BRAIN - Inter-Session Communication System")
    print("=" * 60)

    # Initialize brain
    brain = ClaudeBrain(session_id="test_session")

    # Share an insight
    brain.share_insight(
        area="card_detection",
        title="Adaptive threshold improves card recognition",
        content="Using thresholds [0.15, 0.20, 0.25, 0.30, 0.35] instead of fixed 0.15 "
                "dramatically improves card detection in varying lighting conditions.",
        evidence=["Detection rate improved from 70% to 95%"],
        tags=["card_detection", "threshold", "lighting"]
    )

    # Suggest an improvement
    brain.ultrathink.suggest_improvement(
        area="template_matching",
        problem="Template matching fails when GGPoker window has green focus border",
        solution="Use adaptive threshold chain [0.01, 0.05, 0.10, 0.15, 0.20, 0.25] "
                "and accept first threshold that finds exactly 1 match",
        priority=1,
        session_id=brain.session_id
    )

    # Print summary
    print("\nUltraThink Summary:")
    print(json.dumps(brain.ultrathink.get_summary(), indent=2))

    # Ask a question
    print("\nAsking ultrathink about card detection:")
    answer = brain.ask("How to improve card detection?", context="card_detection")
    print(answer)

    brain.close()
    print("\nSession closed.")
