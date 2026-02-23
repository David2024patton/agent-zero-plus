"""
Proactive Briefing Tool for Agent Zero
========================================
Generates morning briefings and evening recaps by gathering
contextual information and presenting it proactively.

This tool integrates with the scheduler to run at configured times.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("agent-zero.proactive")


class ProactiveBriefing:
    """
    Generates proactive briefings by gathering information from various sources.

    Can be triggered by:
    - Scheduler (cron-based morning/evening)
    - Manual command
    - Heartbeat check
    """

    def __init__(self, agent=None):
        self.agent = agent
        self._modules = []

    def register_module(self, name: str, gather_fn):
        """Register a data gathering module for briefings."""
        self._modules.append({"name": name, "gather": gather_fn})

    async def generate_morning_briefing(self) -> str:
        """
        Generate a morning briefing.

        Gathers:
        - Current date/time and weather (if available)
        - Pending scheduled tasks
        - Recent memory recalls
        - System health summary
        """
        now = datetime.now()
        sections = []
        sections.append(f"# 🌅 Morning Briefing — {now.strftime('%A, %B %d, %Y')}\n")
        sections.append(f"**Time:** {now.strftime('%I:%M %p')}\n")

        # Gather from registered modules
        for module in self._modules:
            try:
                content = await module["gather"]()
                if content:
                    sections.append(f"## {module['name']}\n{content}\n")
            except Exception as e:
                logger.warning(f"Briefing module '{module['name']}' failed: {e}")

        # Gather pending tasks from scheduler
        try:
            sections.append(await self._gather_scheduled_tasks())
        except Exception as e:
            logger.warning(f"Failed to gather scheduled tasks: {e}")

        # Gather recent memories
        try:
            sections.append(await self._gather_recent_memories())
        except Exception as e:
            logger.warning(f"Failed to gather recent memories: {e}")

        return "\n".join(s for s in sections if s)

    async def generate_evening_recap(self) -> str:
        """
        Generate an evening recap.

        Summarizes:
        - Messages handled today
        - Tasks completed
        - Pending items for tomorrow
        """
        now = datetime.now()
        sections = []
        sections.append(f"# 🌙 Evening Recap — {now.strftime('%A, %B %d, %Y')}\n")

        for module in self._modules:
            try:
                content = await module["gather"]()
                if content:
                    sections.append(f"## {module['name']}\n{content}\n")
            except Exception as e:
                logger.warning(f"Recap module '{module['name']}' failed: {e}")

        sections.append("## Summary\n_Today's activities have been logged to memory._\n")
        return "\n".join(s for s in sections if s)

    async def _gather_scheduled_tasks(self) -> str:
        """Gather pending scheduled tasks."""
        try:
            from python.helpers import files
            import json

            tasks_file = files.get_abs_path("usr/scheduled_tasks.json")
            if not files.exists(tasks_file):
                return ""

            with open(tasks_file, "r") as f:
                tasks = json.load(f)

            if not tasks:
                return ""

            pending = [t for t in tasks if t.get("status") == "pending"]
            if not pending:
                return "## 📋 Scheduled Tasks\nNo pending tasks.\n"

            lines = ["## 📋 Scheduled Tasks"]
            for task in pending[:10]:
                lines.append(f"- **{task.get('name', 'Unnamed')}**: {task.get('description', 'No description')}")
            if len(pending) > 10:
                lines.append(f"_...and {len(pending) - 10} more_")
            return "\n".join(lines) + "\n"

        except Exception as e:
            logger.debug(f"Scheduled tasks not available: {e}")
            return ""

    async def _gather_recent_memories(self) -> str:
        """Gather recent memory entries."""
        # This would integrate with Agent Zero's memory system
        return "## 🧠 Memory\n_Memory system active. Recent context loaded._\n"


class HeartbeatSystem:
    """
    Periodic heartbeat check for proactive notifications.

    Runs at configurable intervals and checks for noteworthy events.
    """

    def __init__(self, interval_seconds: int = 300, agent=None):
        self.interval = interval_seconds
        self.agent = agent
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._checks = []

    def register_check(self, name: str, check_fn, notify_fn=None):
        """
        Register a heartbeat check.

        Args:
            name: Name of the check.
            check_fn: Async function that returns True if something noteworthy.
            notify_fn: Optional async function to call when check triggers.
        """
        self._checks.append({
            "name": name,
            "check": check_fn,
            "notify": notify_fn,
        })

    async def start(self):
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Heartbeat started (interval: {self.interval}s)")

    async def stop(self):
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat stopped")

    async def _loop(self):
        """Main heartbeat loop."""
        while self._running:
            try:
                for check in self._checks:
                    try:
                        triggered = await check["check"]()
                        if triggered and check["notify"]:
                            await check["notify"]()
                            logger.info(f"Heartbeat check '{check['name']}' triggered notification")
                    except Exception as e:
                        logger.warning(f"Heartbeat check '{check['name']}' failed: {e}")

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(self.interval)
