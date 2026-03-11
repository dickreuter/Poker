#!/usr/bin/env python3
"""
CLAUDE SESSION - Unified Entry Point for Claude Inter-Session Communication

This is the main entry point for Claude sessions to communicate with each other.
It integrates:
1. ClaudeBrain - Message passing and shared insights
2. UltraThink - Meta-learning and improvement tracking
3. Coordinator - Task delegation and coordination

Usage:
    # Start an interactive Claude session
    python -m gamble.tools.claude_session

    # Start with a specific session ID
    python -m gamble.tools.claude_session --id poker_analyzer

    # Join as a specific role
    python -m gamble.tools.claude_session --role card_detector

    # Read messages without interactive mode
    python -m gamble.tools.claude_session --read

    # Share an insight
    python -m gamble.tools.claude_session --share "card_detection" "Threshold 0.35 works best"

    # Ask a question
    python -m gamble.tools.claude_session --ask "How to improve button detection?"
"""

import argparse
import json
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from gamble.tools.claude_brain import ClaudeBrain, UltraThink, Message, MessagePriority
from gamble.tools.ultrathink import UltraThinkCore, observe as ut_observe, think as ut_think
from gamble.tools.claude_coordinator import Coordinator, CoordinatorCLI

log = logging.getLogger(__name__)


class ClaudeSession:
    """
    A unified Claude session that integrates all communication systems.

    This is what each Claude Code session should use to communicate with others.
    """

    def __init__(self, session_id: str = None, role: str = None):
        """
        Initialize a Claude session.

        Args:
            session_id: Unique identifier for this session
            role: Role this session plays (e.g., "card_detector", "button_handler")
        """
        self.session_id = session_id
        self.role = role

        # Initialize subsystems
        self.brain = ClaudeBrain(session_id=session_id)
        self.ultrathink = UltraThinkCore(session_id=self.brain.session_id)
        self.coordinator = Coordinator(session_id=self.brain.session_id)

        # Update session ID from brain (it may have generated one)
        self.session_id = self.brain.session_id

        # Register role as capability if provided
        if role:
            self.coordinator.register_capability(role)
            self.brain.broadcast(
                f"Session {self.session_id} online with role: {role}",
                priority=MessagePriority.LOW
            )

        log.info(f"ClaudeSession initialized: {self.session_id} (role: {role or 'general'})")

    # === Messaging ===

    def broadcast(self, message: str, priority: MessagePriority = MessagePriority.NORMAL):
        """Broadcast a message to all Claude sessions"""
        return self.brain.broadcast(message, priority=priority)

    def send_to(self, target_session: str, message: str):
        """Send a direct message to another session"""
        return self.brain.send(target_session, message)

    def get_messages(self) -> List[Message]:
        """Get all pending messages"""
        return self.brain.receive()

    # === Knowledge Sharing ===

    def share_insight(self, area: str, title: str, content: str,
                      evidence: List[str] = None, tags: List[str] = None):
        """Share an insight with all sessions"""
        # Add to both brain and ultrathink
        self.brain.share_insight(area, title, content, evidence, tags)
        self.ultrathink.observe(
            category=area,
            event="insight_shared",
            context={"title": title},
            outcome="shared",
            metrics={}
        )

    def get_knowledge(self, area: str = None) -> List[Dict]:
        """Get accumulated knowledge"""
        insights = self.brain.ultrathink.get_insights(area)
        return [i.to_dict() for i in insights]

    # === Thinking ===

    def think(self, question: str, context: str = "") -> str:
        """
        Deep thinking using accumulated knowledge.

        Combines insights from brain's ultrathink and the ultrathink core.
        """
        # Get analysis from both systems
        brain_analysis = self.brain.ask(question, context)
        ultrathink_analysis = self.ultrathink.think(question, context)

        # Combine
        combined = f"""
# Combined Analysis

## Brain (Inter-Session Knowledge)
{brain_analysis}

## UltraThink (Meta-Learning)
{ultrathink_analysis}
"""
        return combined

    def ask(self, question: str) -> str:
        """Quick ask and broadcast to other sessions"""
        # Broadcast the question
        self.brain.broadcast(
            f"Question from {self.session_id}: {question}",
            priority=MessagePriority.NORMAL
        )

        # Return immediate thinking
        return self.think(question)

    # === Observations ===

    def observe_success(self, category: str, event: str, context: Dict):
        """Record a success observation"""
        from gamble.tools.ultrathink import ObservationType
        return self.ultrathink.observe(
            category=category,
            event=event,
            context=context,
            outcome="success",
            obs_type=ObservationType.SUCCESS
        )

    def observe_failure(self, category: str, event: str, context: Dict, error: str = None):
        """Record a failure observation"""
        from gamble.tools.ultrathink import ObservationType
        return self.ultrathink.observe(
            category=category,
            event=event,
            context={**context, 'error': error} if error else context,
            outcome="failure",
            obs_type=ObservationType.FAILURE
        )

    def observe_anomaly(self, category: str, event: str, context: Dict, description: str):
        """Record an anomaly observation"""
        from gamble.tools.ultrathink import ObservationType
        return self.ultrathink.observe(
            category=category,
            event=event,
            context={**context, 'description': description},
            outcome="anomaly",
            obs_type=ObservationType.ANOMALY
        )

    # === Improvements ===

    def suggest_improvement(self, area: str, problem: str, solution: str,
                           code_changes: str = None):
        """Suggest an improvement"""
        return self.brain.ultrathink.suggest_improvement(
            area=area,
            problem=problem,
            solution=solution,
            code_changes=code_changes,
            session_id=self.session_id
        )

    def get_improvements(self, area: str = None) -> List[Dict]:
        """Get suggested improvements"""
        return [i.to_dict() for i in self.brain.ultrathink.get_improvements(area)]

    def get_recommendations(self, area: str = None, top_k: int = 5) -> List[Dict]:
        """Get top improvement recommendations"""
        return [h.to_dict() for h in self.ultrathink.recommend_improvements(area, top_k)]

    # === Task Coordination ===

    def request_help(self, capability: str, description: str, data: Dict = None):
        """Request help from sessions with a specific capability"""
        return self.coordinator.request_help(capability, description, data)

    def offer_help(self, capability: str):
        """Offer to help with a specific capability"""
        self.coordinator.register_capability(capability)
        self.broadcast(f"{self.session_id} can help with: {capability}")

    def get_active_sessions(self) -> List[str]:
        """Get list of active sessions"""
        return [s.id for s in self.coordinator.get_active_sessions()]

    # === Status ===

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status"""
        return {
            'session_id': self.session_id,
            'role': self.role,
            'brain': {
                'active_sessions': len(self.brain.get_active_sessions()),
                'pending_messages': len(self.get_messages()),
                'ultrathink': self.brain.ultrathink.get_summary()
            },
            'ultrathink': self.ultrathink.get_summary(),
            'coordinator': {
                'status': self.coordinator.session.status.value,
                'capabilities': self.coordinator.session.capabilities,
                'tasks_completed': self.coordinator.session.tasks_completed
            }
        }

    # === Cleanup ===

    def close(self):
        """Close the session"""
        self.brain.close()
        self.coordinator.close()
        log.info(f"Session {self.session_id} closed")


class ClaudeSessionCLI:
    """Interactive CLI for Claude sessions"""

    def __init__(self, session_id: str = None, role: str = None):
        self.session = ClaudeSession(session_id=session_id, role=role)
        self.running = True

    def run(self):
        """Run interactive CLI"""
        print("=" * 70)
        print("CLAUDE SESSION - Inter-Session Communication")
        print("=" * 70)
        print(f"Session ID: {self.session.session_id}")
        print(f"Role: {self.session.role or 'general'}")
        print("=" * 70)
        print("\nCommands: broadcast, share, ask, think, observe, improve, status, help, quit")
        print()

        # Show any pending messages
        messages = self.session.get_messages()
        if messages:
            print(f"\n[{len(messages)} pending messages]")
            for msg in messages[:5]:
                print(f"  From {msg.from_session}: {msg.content[:60]}...")
            print()

        while self.running:
            try:
                cmd = input("claude> ").strip()
                self.handle_command(cmd)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nUse 'quit' to exit")

        self.session.close()
        print("Session closed.")

    def handle_command(self, cmd: str):
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if command == "quit" or command == "exit":
            self.running = False

        elif command == "broadcast" or command == "say":
            if args:
                self.session.broadcast(args)
                print("Broadcasted!")
            else:
                print("Usage: broadcast <message>")

        elif command == "share":
            self.share_interactive()

        elif command == "ask":
            if args:
                answer = self.session.ask(args)
                print("\n" + answer)
            else:
                print("Usage: ask <question>")

        elif command == "think":
            if args:
                # Parse: think "context" "question"
                analysis = self.session.think(args)
                print("\n" + analysis)
            else:
                print("Usage: think <question>")

        elif command == "observe":
            self.observe_interactive()

        elif command == "improve":
            self.improve_interactive()

        elif command == "status":
            status = self.session.get_status()
            print("\nSession Status:")
            print(json.dumps(status, indent=2, default=str))

        elif command == "messages" or command == "inbox":
            messages = self.session.get_messages()
            print(f"\nMessages ({len(messages)}):")
            for msg in messages:
                print(f"  [{msg.priority.name}] From {msg.from_session}: {msg.content}")

        elif command == "sessions":
            sessions = self.session.get_active_sessions()
            print(f"\nActive Sessions ({len(sessions)}):")
            for s in sessions:
                print(f"  - {s}")

        elif command == "knowledge":
            area = args or None
            knowledge = self.session.get_knowledge(area)
            print(f"\nKnowledge ({len(knowledge)} items):")
            for k in knowledge[:10]:
                print(f"  [{k['area']}] {k['title']}")
                print(f"    {k['content'][:80]}...")

        elif command == "recommendations" or command == "rec":
            area = args or None
            recs = self.session.get_recommendations(area)
            print(f"\nRecommendations ({len(recs)}):")
            for r in recs:
                print(f"  [{r['status']}] {r['title']}")
                print(f"    {r['description'][:80]}...")
                print(f"    Expected improvement: {r['expected_improvement']:.0%}")

        elif command == "help":
            self.show_help()

        elif command == "":
            pass

        else:
            print(f"Unknown command: {command}")
            self.show_help()

    def share_interactive(self):
        print("\nShare an insight:")
        area = input("  Area (e.g., card_detection): ").strip()
        title = input("  Title: ").strip()
        content = input("  Content: ").strip()

        if area and title and content:
            self.session.share_insight(area, title, content)
            print("Insight shared!")
        else:
            print("Cancelled - all fields required")

    def observe_interactive(self):
        print("\nRecord an observation:")
        category = input("  Category: ").strip()
        event = input("  Event: ").strip()
        outcome = input("  Outcome (success/failure/anomaly): ").strip().lower()

        if category and event and outcome:
            context = {}
            print("  Context (key=value, empty to finish):")
            while True:
                kv = input("    > ").strip()
                if not kv:
                    break
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    context[k.strip()] = v.strip()

            if outcome == "success":
                self.session.observe_success(category, event, context)
            elif outcome == "failure":
                self.session.observe_failure(category, event, context)
            elif outcome == "anomaly":
                desc = input("  Description: ").strip()
                self.session.observe_anomaly(category, event, context, desc)
            else:
                print("Invalid outcome type")
                return

            print("Observation recorded!")
        else:
            print("Cancelled")

    def improve_interactive(self):
        print("\nSuggest an improvement:")
        area = input("  Area: ").strip()
        problem = input("  Problem: ").strip()
        solution = input("  Solution: ").strip()

        if area and problem and solution:
            self.session.suggest_improvement(area, problem, solution)
            print("Improvement suggested!")
        else:
            print("Cancelled - all fields required")

    def show_help(self):
        print("""
Commands:
  broadcast <msg>  - Send message to all sessions
  share           - Share an insight (interactive)
  ask <question>  - Ask a question and broadcast it
  think <query>   - Deep thinking using accumulated knowledge
  observe         - Record an observation (interactive)
  improve         - Suggest an improvement (interactive)
  messages        - Show pending messages
  sessions        - Show active sessions
  knowledge       - Show accumulated knowledge
  recommendations - Show improvement recommendations
  status          - Show session status
  quit            - Exit
""")


def main():
    parser = argparse.ArgumentParser(description="Claude Session - Inter-Session Communication")
    parser.add_argument("--id", default=None, help="Session ID")
    parser.add_argument("--role", default=None, help="Session role")
    parser.add_argument("--read", action="store_true", help="Read messages and exit")
    parser.add_argument("--share", nargs=2, metavar=("AREA", "CONTENT"),
                       help="Share an insight")
    parser.add_argument("--ask", type=str, help="Ask a question")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')

    # Handle quick commands
    if args.read:
        session = ClaudeSession(session_id=args.id, role=args.role)
        messages = session.get_messages()
        for msg in messages:
            print(f"[{msg.priority.name}] {msg.from_session}: {msg.content}")
        session.close()
        return

    if args.share:
        session = ClaudeSession(session_id=args.id, role=args.role)
        session.share_insight(args.share[0], "Quick share", args.share[1])
        print("Shared!")
        session.close()
        return

    if args.ask:
        session = ClaudeSession(session_id=args.id, role=args.role)
        answer = session.ask(args.ask)
        print(answer)
        session.close()
        return

    if args.status:
        session = ClaudeSession(session_id=args.id, role=args.role)
        print(json.dumps(session.get_status(), indent=2, default=str))
        session.close()
        return

    # Interactive mode
    cli = ClaudeSessionCLI(session_id=args.id, role=args.role)
    cli.run()


if __name__ == "__main__":
    main()
