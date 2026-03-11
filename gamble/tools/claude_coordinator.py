"""
CLAUDE COORDINATOR - Real-Time Session Coordination

This module provides real-time coordination between Claude sessions:
1. Session discovery and registration
2. Real-time message routing
3. Task coordination and delegation
4. Collective decision making
5. Resource locking for shared state

Can run as:
1. A background daemon watching for coordination needs
2. An interactive CLI for manual coordination
3. A library imported by other scripts

Usage:
    # As a background daemon
    python -m gamble.tools.claude_coordinator daemon

    # Interactive CLI
    python -m gamble.tools.claude_coordinator cli

    # As a library
    from gamble.tools.claude_coordinator import Coordinator

    coord = Coordinator(session_id="my_session")
    coord.register_capability("card_detection")
    coord.announce("I can handle card detection tasks")
    coord.request_help("button_detection", "Need help with fold button position")
"""

import json
import os
import sys
import time
import uuid
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import select

log = logging.getLogger(__name__)

# Base directory
COORD_DIR = Path("/Users/sebastian/Developer/Gamble/gamble/claude_brain_data/coordination")


class TaskStatus(Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionStatus(Enum):
    ACTIVE = "active"
    BUSY = "busy"
    IDLE = "idle"
    OFFLINE = "offline"


@dataclass
class Session:
    """Represents a Claude session"""
    id: str
    status: SessionStatus
    capabilities: List[str]
    started_at: float
    last_heartbeat: float
    current_task: Optional[str]
    tasks_completed: int
    metadata: Dict[str, Any]

    def to_dict(self):
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d):
        d['status'] = SessionStatus(d['status'])
        return cls(**d)


@dataclass
class Task:
    """A task that can be delegated between sessions"""
    id: str
    type: str
    description: str
    priority: int  # 1 = highest
    status: TaskStatus
    created_by: str
    assigned_to: Optional[str]
    created_at: float
    claimed_at: Optional[float]
    completed_at: Optional[float]
    requirements: List[str]  # Required capabilities
    data: Dict[str, Any]
    result: Optional[Dict[str, Any]]

    def to_dict(self):
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d):
        d['status'] = TaskStatus(d['status'])
        return cls(**d)


@dataclass
class Lock:
    """A distributed lock for shared resources"""
    resource: str
    owner: str
    acquired_at: float
    expires_at: float
    metadata: Dict[str, Any]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class Coordinator:
    """
    The main coordination hub for Claude sessions.

    Handles session registration, task delegation, and resource locking.
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"coord_{uuid.uuid4().hex[:6]}"

        # Directories
        self.sessions_dir = COORD_DIR / "sessions"
        self.tasks_dir = COORD_DIR / "tasks"
        self.locks_dir = COORD_DIR / "locks"
        self.announcements_dir = COORD_DIR / "announcements"

        for d in [self.sessions_dir, self.tasks_dir, self.locks_dir, self.announcements_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Session info
        self.session = Session(
            id=self.session_id,
            status=SessionStatus.ACTIVE,
            capabilities=[],
            started_at=time.time(),
            last_heartbeat=time.time(),
            current_task=None,
            tasks_completed=0,
            metadata={}
        )

        # Register session
        self._save_session()

        # Heartbeat thread
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        log.info(f"Coordinator initialized: session={self.session_id}")

    def _save_session(self):
        """Save session info to file"""
        filepath = self.sessions_dir / f"{self.session_id}.json"
        with open(filepath, 'w') as f:
            json.dump(self.session.to_dict(), f, indent=2)

    def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self._heartbeat_running:
            self.session.last_heartbeat = time.time()
            self._save_session()
            time.sleep(10)  # Heartbeat every 10 seconds

    def register_capability(self, capability: str):
        """Register a capability this session can handle"""
        if capability not in self.session.capabilities:
            self.session.capabilities.append(capability)
            self._save_session()
            log.info(f"Registered capability: {capability}")

    def unregister_capability(self, capability: str):
        """Unregister a capability"""
        if capability in self.session.capabilities:
            self.session.capabilities.remove(capability)
            self._save_session()

    def set_status(self, status: SessionStatus):
        """Update session status"""
        self.session.status = status
        self._save_session()

    def get_active_sessions(self, timeout_seconds: int = 60) -> List[Session]:
        """Get all active sessions"""
        sessions = []
        cutoff = time.time() - timeout_seconds

        for filepath in self.sessions_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    session = Session.from_dict(json.load(f))
                if session.last_heartbeat >= cutoff:
                    sessions.append(session)
            except Exception as e:
                log.warning(f"Error loading session {filepath}: {e}")

        return sessions

    def find_session_with_capability(self, capability: str) -> Optional[Session]:
        """Find an active session with a specific capability"""
        for session in self.get_active_sessions():
            if capability in session.capabilities and session.status == SessionStatus.IDLE:
                return session
        return None

    def announce(self, message: str, priority: int = 2):
        """Make an announcement to all sessions"""
        announcement = {
            'id': str(uuid.uuid4())[:8],
            'from': self.session_id,
            'message': message,
            'priority': priority,
            'timestamp': time.time(),
            'expires': time.time() + 3600  # 1 hour
        }

        filepath = self.announcements_dir / f"{announcement['id']}.json"
        with open(filepath, 'w') as f:
            json.dump(announcement, f, indent=2)

        log.info(f"Announcement: {message}")

    def get_announcements(self, since: float = None) -> List[Dict]:
        """Get recent announcements"""
        since = since or (time.time() - 3600)  # Default: last hour
        announcements = []

        for filepath in self.announcements_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    ann = json.load(f)
                if ann['timestamp'] >= since and ann.get('expires', 0) > time.time():
                    announcements.append(ann)
            except Exception as e:
                log.warning(f"Error loading announcement: {e}")

        return sorted(announcements, key=lambda x: x['timestamp'], reverse=True)

    # Task Management
    def create_task(self, task_type: str, description: str,
                    requirements: List[str] = None,
                    priority: int = 2,
                    data: Dict = None) -> Task:
        """Create a new task for delegation"""
        task = Task(
            id=str(uuid.uuid4())[:8],
            type=task_type,
            description=description,
            priority=priority,
            status=TaskStatus.PENDING,
            created_by=self.session_id,
            assigned_to=None,
            created_at=time.time(),
            claimed_at=None,
            completed_at=None,
            requirements=requirements or [],
            data=data or {},
            result=None
        )

        filepath = self.tasks_dir / f"{task.id}.json"
        with open(filepath, 'w') as f:
            json.dump(task.to_dict(), f, indent=2)

        log.info(f"Created task: {task_type} - {description}")
        return task

    def claim_task(self, task_id: str) -> bool:
        """Claim a pending task"""
        filepath = self.tasks_dir / f"{task_id}.json"
        if not filepath.exists():
            return False

        with open(filepath) as f:
            task = Task.from_dict(json.load(f))

        if task.status != TaskStatus.PENDING:
            return False

        task.status = TaskStatus.CLAIMED
        task.assigned_to = self.session_id
        task.claimed_at = time.time()

        with open(filepath, 'w') as f:
            json.dump(task.to_dict(), f, indent=2)

        self.session.current_task = task_id
        self.session.status = SessionStatus.BUSY
        self._save_session()

        log.info(f"Claimed task: {task_id}")
        return True

    def complete_task(self, task_id: str, result: Dict = None, success: bool = True):
        """Mark a task as completed"""
        filepath = self.tasks_dir / f"{task_id}.json"
        if not filepath.exists():
            return

        with open(filepath) as f:
            task = Task.from_dict(json.load(f))

        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task.completed_at = time.time()
        task.result = result or {}

        with open(filepath, 'w') as f:
            json.dump(task.to_dict(), f, indent=2)

        self.session.current_task = None
        self.session.status = SessionStatus.IDLE
        self.session.tasks_completed += 1
        self._save_session()

        log.info(f"Completed task: {task_id} - {'SUCCESS' if success else 'FAILED'}")

    def get_pending_tasks(self, task_type: str = None) -> List[Task]:
        """Get pending tasks, optionally filtered by type"""
        tasks = []

        for filepath in self.tasks_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    task = Task.from_dict(json.load(f))
                if task.status == TaskStatus.PENDING:
                    if task_type is None or task.type == task_type:
                        tasks.append(task)
            except Exception as e:
                log.warning(f"Error loading task: {e}")

        return sorted(tasks, key=lambda t: t.priority)

    def request_help(self, capability: str, description: str, data: Dict = None) -> Optional[Task]:
        """Request help from a session with a specific capability"""
        # Find a session that can help
        helper = self.find_session_with_capability(capability)

        # Create task
        task = self.create_task(
            task_type=f"help_{capability}",
            description=description,
            requirements=[capability],
            priority=1,
            data=data
        )

        # If we found a helper, notify them
        if helper:
            self.announce(
                f"Help needed: {description} (task: {task.id})",
                priority=1
            )

        return task

    # Resource Locking
    def acquire_lock(self, resource: str, timeout_seconds: int = 30) -> bool:
        """Acquire a lock on a shared resource"""
        filepath = self.locks_dir / f"{resource}.json"

        # Check existing lock
        if filepath.exists():
            with open(filepath) as f:
                lock = Lock.from_dict(json.load(f))

            # Check if expired
            if lock.expires_at > time.time() and lock.owner != self.session_id:
                log.warning(f"Lock on {resource} held by {lock.owner}")
                return False

        # Create new lock
        lock = Lock(
            resource=resource,
            owner=self.session_id,
            acquired_at=time.time(),
            expires_at=time.time() + timeout_seconds,
            metadata={}
        )

        with open(filepath, 'w') as f:
            json.dump(lock.to_dict(), f, indent=2)

        log.info(f"Acquired lock: {resource}")
        return True

    def release_lock(self, resource: str):
        """Release a lock"""
        filepath = self.locks_dir / f"{resource}.json"
        if filepath.exists():
            with open(filepath) as f:
                lock = Lock.from_dict(json.load(f))

            if lock.owner == self.session_id:
                filepath.unlink()
                log.info(f"Released lock: {resource}")

    def close(self):
        """Shutdown coordinator"""
        self._heartbeat_running = False
        self.session.status = SessionStatus.OFFLINE
        self._save_session()
        log.info(f"Coordinator {self.session_id} closed")


class CoordinatorCLI:
    """Interactive CLI for the coordinator"""

    def __init__(self):
        self.coordinator = Coordinator()
        self.running = True

    def run(self):
        """Run interactive CLI"""
        print("=" * 60)
        print("CLAUDE COORDINATOR - Interactive Session")
        print(f"Session ID: {self.coordinator.session_id}")
        print("=" * 60)
        print("\nCommands: sessions, announce, tasks, help, claim, complete, quit")
        print()

        while self.running:
            try:
                cmd = input("coord> ").strip().lower()
                self.handle_command(cmd)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nUse 'quit' to exit")

        self.coordinator.close()
        print("Goodbye!")

    def handle_command(self, cmd: str):
        parts = cmd.split(maxsplit=1)
        command = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if command == "quit" or command == "exit":
            self.running = False
        elif command == "sessions":
            self.show_sessions()
        elif command == "announce":
            if args:
                self.coordinator.announce(args)
                print("Announced!")
            else:
                print("Usage: announce <message>")
        elif command == "tasks":
            self.show_tasks()
        elif command == "help":
            self.show_help()
        elif command == "claim":
            if args:
                if self.coordinator.claim_task(args):
                    print(f"Claimed task {args}")
                else:
                    print(f"Could not claim task {args}")
            else:
                print("Usage: claim <task_id>")
        elif command == "complete":
            if self.coordinator.session.current_task:
                self.coordinator.complete_task(self.coordinator.session.current_task)
                print("Task completed!")
            else:
                print("No current task")
        elif command == "capability":
            if args:
                self.coordinator.register_capability(args)
                print(f"Registered capability: {args}")
            else:
                print("Usage: capability <name>")
        elif command == "create":
            self.create_task_interactive()
        elif command == "messages":
            self.show_announcements()
        elif command == "status":
            self.show_status()
        elif command == "":
            pass
        else:
            print(f"Unknown command: {command}")
            print("Commands: sessions, announce, tasks, help, claim, complete, capability, create, messages, status, quit")

    def show_sessions(self):
        sessions = self.coordinator.get_active_sessions()
        print(f"\nActive Sessions ({len(sessions)}):")
        for s in sessions:
            print(f"  {s.id}")
            print(f"    Status: {s.status.value}")
            print(f"    Capabilities: {', '.join(s.capabilities) or 'none'}")
            print(f"    Tasks completed: {s.tasks_completed}")
            ago = int(time.time() - s.last_heartbeat)
            print(f"    Last seen: {ago}s ago")
        print()

    def show_tasks(self):
        tasks = self.coordinator.get_pending_tasks()
        print(f"\nPending Tasks ({len(tasks)}):")
        for t in tasks:
            print(f"  [{t.id}] {t.type}")
            print(f"    {t.description}")
            print(f"    Priority: {t.priority}")
            print(f"    Requirements: {', '.join(t.requirements) or 'none'}")
        print()

    def show_announcements(self):
        announcements = self.coordinator.get_announcements()
        print(f"\nRecent Announcements ({len(announcements)}):")
        for a in announcements[:10]:
            ago = int(time.time() - a['timestamp'])
            print(f"  [{ago}s ago] {a['from']}: {a['message']}")
        print()

    def show_status(self):
        s = self.coordinator.session
        print(f"\nCurrent Session Status:")
        print(f"  ID: {s.id}")
        print(f"  Status: {s.status.value}")
        print(f"  Capabilities: {', '.join(s.capabilities) or 'none'}")
        print(f"  Current task: {s.current_task or 'none'}")
        print(f"  Tasks completed: {s.tasks_completed}")
        print()

    def show_help(self):
        print("""
Commands:
  sessions    - List active Claude sessions
  announce    - Broadcast a message to all sessions
  tasks       - List pending tasks
  claim <id>  - Claim a pending task
  complete    - Mark current task as complete
  capability  - Register a capability
  create      - Create a new task
  messages    - Show recent announcements
  status      - Show current session status
  quit        - Exit the CLI
""")

    def create_task_interactive(self):
        print("\nCreate new task:")
        task_type = input("  Type: ").strip()
        description = input("  Description: ").strip()
        priority = input("  Priority (1-5, 1=highest): ").strip() or "2"

        task = self.coordinator.create_task(
            task_type=task_type,
            description=description,
            priority=int(priority)
        )
        print(f"Created task: {task.id}")


def daemon_mode():
    """Run coordinator as a background daemon"""
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(levelname)s - %(message)s')

    print("Starting Claude Coordinator daemon...")
    coord = Coordinator(session_id="daemon")
    coord.register_capability("daemon")
    coord.register_capability("coordination")

    try:
        while True:
            # Process pending tasks
            tasks = coord.get_pending_tasks()
            if tasks:
                log.info(f"Pending tasks: {len(tasks)}")

            # Clean up expired locks
            for filepath in coord.locks_dir.glob("*.json"):
                try:
                    with open(filepath) as f:
                        lock = Lock.from_dict(json.load(f))
                    if lock.expires_at < time.time():
                        filepath.unlink()
                        log.info(f"Cleaned up expired lock: {lock.resource}")
                except:
                    pass

            # Clean up old announcements
            for filepath in coord.announcements_dir.glob("*.json"):
                try:
                    with open(filepath) as f:
                        ann = json.load(f)
                    if ann.get('expires', 0) < time.time():
                        filepath.unlink()
                except:
                    pass

            time.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down daemon...")
        coord.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "daemon":
            daemon_mode()
        elif mode == "cli":
            cli = CoordinatorCLI()
            cli.run()
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python claude_coordinator.py [daemon|cli]")
    else:
        # Default to CLI
        cli = CoordinatorCLI()
        cli.run()
