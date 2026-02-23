"""
Thread Binding Manager for Discord Sub-Agent Sessions
======================================================
Maps Discord thread IDs to sub-agent targets, providing the
"thread-bound sub-agent" feature from OpenClaw.

When a user runs `/a0 focus <target>` in a Discord thread,
all subsequent messages in that thread are automatically routed
to the specified sub-agent, without needing @mentions or prefixes.

Bindings auto-expire after a configurable TTL (default 24h).
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("agent-zero.plugins.discord.threads")


@dataclass
class ThreadBinding:
    """A single thread → target binding."""
    thread_id: str
    target: str            # Sub-agent ID or model name
    user_id: str           # Who created the binding
    guild_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self):
        """Update last activity timestamp."""
        self.last_active = time.time()
        self.message_count += 1

    def is_expired(self, ttl_hours: float) -> bool:
        """Check if this binding has expired based on TTL."""
        if ttl_hours <= 0:
            return False  # 0 = never expire
        elapsed_hours = (time.time() - self.last_active) / 3600
        return elapsed_hours >= ttl_hours

    def to_dict(self) -> dict:
        """Serialize for display/storage."""
        return {
            "thread_id": self.thread_id,
            "target": self.target,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "message_count": self.message_count,
            "age_hours": round((time.time() - self.created_at) / 3600, 1),
            "idle_hours": round((time.time() - self.last_active) / 3600, 1),
        }


class ThreadBindingManager:
    """
    Manages Discord thread ↔ sub-agent bindings.

    Features:
      - bind/unbind threads to sub-agent targets
      - TTL-based auto-expiry with background cleanup
      - Activity tracking (touch on each message)
      - Auto-thread creation from parent messages
      - Event callbacks for bind/unbind/create/expire
    """

    def __init__(self, ttl_hours: float = 24.0, cleanup_interval: float = 300.0):
        self._bindings: Dict[str, ThreadBinding] = {}  # thread_id -> binding
        self._ttl_hours = ttl_hours
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

        # Callbacks for events
        self._on_bind: Optional[Callable] = None
        self._on_unbind: Optional[Callable] = None
        self._on_expire: Optional[Callable] = None
        self._on_create_thread: Optional[Callable] = None

    @property
    def ttl_hours(self) -> float:
        return self._ttl_hours

    @ttl_hours.setter
    def ttl_hours(self, value: float):
        self._ttl_hours = max(0, value)

    # ─── Binding operations ───

    def bind(
        self,
        thread_id: str,
        target: str,
        user_id: str,
        guild_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ThreadBinding:
        """
        Bind a Discord thread to a sub-agent target.

        If the thread is already bound, the binding is updated.
        Returns the new or updated binding.
        """
        existing = self._bindings.get(thread_id)
        if existing:
            logger.info(
                f"Rebinding thread {thread_id}: {existing.target} → {target}"
            )

        binding = ThreadBinding(
            thread_id=thread_id,
            target=target,
            user_id=user_id,
            guild_id=guild_id,
            metadata=metadata or {},
        )
        self._bindings[thread_id] = binding
        logger.info(f"Thread {thread_id} bound to '{target}' by user {user_id}")

        if self._on_bind:
            asyncio.ensure_future(self._safe_callback(self._on_bind, binding))

        return binding

    def unbind(self, thread_id: str) -> Optional[ThreadBinding]:
        """
        Remove a thread binding. Returns the removed binding (if any).
        """
        binding = self._bindings.pop(thread_id, None)
        if binding:
            logger.info(
                f"Thread {thread_id} unbound from '{binding.target}' "
                f"(had {binding.message_count} messages)"
            )
            if self._on_unbind:
                asyncio.ensure_future(self._safe_callback(self._on_unbind, binding))
        return binding

    def get_binding(self, thread_id: str) -> Optional[ThreadBinding]:
        """
        Get the binding for a thread, or None if not bound.
        Does NOT touch (update activity) — call touch() explicitly.
        """
        return self._bindings.get(thread_id)

    def touch(self, thread_id: str) -> bool:
        """
        Update activity timestamp for a thread binding.
        Returns True if binding exists and was touched.
        """
        binding = self._bindings.get(thread_id)
        if binding:
            binding.touch()
            return True
        return False

    def is_bound(self, thread_id: str) -> bool:
        """Check if a thread is currently bound."""
        return thread_id in self._bindings

    # ─── Query operations ───

    def list_bindings(
        self, guild_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[ThreadBinding]:
        """List active bindings, optionally filtered by guild or user."""
        bindings = list(self._bindings.values())
        if guild_id:
            bindings = [b for b in bindings if b.guild_id == guild_id]
        if user_id:
            bindings = [b for b in bindings if b.user_id == user_id]
        return bindings

    def count(self) -> int:
        """Number of active bindings."""
        return len(self._bindings)

    def get_bindings_for_target(self, target: str) -> List[ThreadBinding]:
        """Find all thread bindings pointing to a specific target."""
        return [b for b in self._bindings.values() if b.target == target]

    def get_targets(self) -> List[str]:
        """List all unique targets that have bindings."""
        return list(set(b.target for b in self._bindings.values()))

    # ─── TTL cleanup ───

    async def start_cleanup_loop(self):
        """Start the background TTL cleanup loop."""
        if self._cleanup_task and not self._cleanup_task.done():
            return  # Already running

        self._cleanup_task = asyncio.ensure_future(self._cleanup_loop())
        logger.info(
            f"Thread binding cleanup started "
            f"(TTL: {self._ttl_hours}h, interval: {self._cleanup_interval}s)"
        )

    async def stop_cleanup_loop(self):
        """Stop the background cleanup loop."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Thread binding cleanup stopped")

    async def _cleanup_loop(self):
        """Periodically check and expire stale bindings."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                expired = self.expire_stale()
                if expired:
                    logger.info(f"Expired {len(expired)} stale thread binding(s)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in thread cleanup loop: {e}")
                await asyncio.sleep(60)  # Back off on error

    def expire_stale(self) -> List[ThreadBinding]:
        """
        Remove all bindings that have exceeded their TTL.
        Returns list of expired bindings.
        """
        if self._ttl_hours <= 0:
            return []  # TTL disabled

        expired = []
        for thread_id in list(self._bindings.keys()):
            binding = self._bindings[thread_id]
            if binding.is_expired(self._ttl_hours):
                self._bindings.pop(thread_id)
                expired.append(binding)
                logger.info(
                    f"Thread {thread_id} binding expired "
                    f"(target: '{binding.target}', idle: "
                    f"{round((time.time() - binding.last_active) / 3600, 1)}h)"
                )
                if self._on_expire:
                    asyncio.ensure_future(
                        self._safe_callback(self._on_expire, binding)
                    )

        return expired

    # ─── Auto-thread creation ───

    async def create_thread_for_subagent(
        self,
        parent_message,  # discord.Message
        target: str,
        user_id: str,
        thread_name: Optional[str] = None,
    ) -> Optional[ThreadBinding]:
        """
        Auto-create a Discord thread from a parent message and bind it.

        This is the core of the "sub-agents get their own threads" feature.

        Args:
            parent_message: The Discord message to create a thread from
            target: Sub-agent ID or model name to bind to
            user_id: ID of the user who triggered the sub-agent
            thread_name: Custom thread name (defaults to "🤖 {target}")

        Returns:
            The ThreadBinding if successful, None on failure
        """
        try:
            name = thread_name or f"🤖 {target}"
            # Truncate to Discord's 100 char thread name limit
            if len(name) > 100:
                name = name[:97] + "..."

            thread = await parent_message.create_thread(
                name=name,
                auto_archive_duration=1440,  # 24 hours
            )

            binding = self.bind(
                thread_id=str(thread.id),
                target=target,
                user_id=user_id,
                guild_id=str(thread.guild.id) if thread.guild else None,
                metadata={
                    "parent_message_id": str(parent_message.id),
                    "parent_channel_id": str(parent_message.channel.id),
                    "auto_created": True,
                },
            )

            # Send greeting in the new thread
            await thread.send(
                f"🔗 **Thread bound to `{target}`**\n"
                f"All messages in this thread will be routed to this sub-agent.\n"
                f"Use `/a0 unfocus` to unbind."
            )

            logger.info(
                f"Auto-created thread '{name}' ({thread.id}) "
                f"bound to '{target}'"
            )

            if self._on_create_thread:
                asyncio.ensure_future(
                    self._safe_callback(self._on_create_thread, binding, thread)
                )

            return binding

        except Exception as e:
            logger.error(f"Failed to create thread for sub-agent '{target}': {e}")
            return None

    # ─── Event callbacks ───

    def on_bind(self, callback: Callable):
        """Register callback for bind events: callback(binding)."""
        self._on_bind = callback

    def on_unbind(self, callback: Callable):
        """Register callback for unbind events: callback(binding)."""
        self._on_unbind = callback

    def on_expire(self, callback: Callable):
        """Register callback for expire events: callback(binding)."""
        self._on_expire = callback

    def on_create_thread(self, callback: Callable):
        """Register callback for thread creation: callback(binding, thread)."""
        self._on_create_thread = callback

    # ─── Helpers ───

    async def _safe_callback(self, callback, *args):
        """Invoke a callback safely, catching any errors."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in thread binding callback: {e}")

    def summary(self) -> str:
        """Human-readable summary of all bindings."""
        if not self._bindings:
            return "No active thread bindings"

        lines = [f"**{self.count()} active binding(s):**"]
        for b in self._bindings.values():
            idle = round((time.time() - b.last_active) / 3600, 1)
            lines.append(
                f"  • Thread `{b.thread_id}` → `{b.target}` "
                f"({b.message_count} msgs, idle {idle}h)"
            )
        return "\n".join(lines)
