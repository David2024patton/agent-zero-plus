"""
Lifecycle Status Reactions for Agent Zero Channels
====================================================
Provides configurable emoji reactions during agent processing phases:
  queued → thinking → tool-use → done → error

Each channel adapter calls these helpers to show real-time status feedback.
Inspired by OpenClaw's lifecycle reactions system.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, Awaitable

logger = logging.getLogger("agent-zero.lifecycle")


@dataclass
class LifecycleEmojis:
    """Configurable emoji set for processing lifecycle phases."""
    queued: str = "📨"
    thinking: str = "🤔"
    tool_use: str = "⚙️"
    done: str = "✅"
    error: str = "❌"
    streaming: str = "💬"


# Default emoji set
DEFAULT_EMOJIS = LifecycleEmojis()

# Per-channel emoji overrides
_channel_emojis: Dict[str, LifecycleEmojis] = {}


def get_emojis(channel_id: str) -> LifecycleEmojis:
    """Get the emoji set for a channel (falls back to defaults)."""
    return _channel_emojis.get(channel_id, DEFAULT_EMOJIS)


def set_emojis(channel_id: str, emojis: LifecycleEmojis):
    """Override emojis for a specific channel."""
    _channel_emojis[channel_id] = emojis


class LifecycleTracker:
    """
    Tracks the processing lifecycle for a single message.

    Usage:
        tracker = LifecycleTracker(
            channel_id="telegram",
            react_fn=telegram_react_fn,
        )
        await tracker.phase("queued")
        await tracker.phase("thinking")
        await tracker.phase("tool_use")
        await tracker.phase("done")
    """

    def __init__(
        self,
        channel_id: str,
        message_ref: Any = None,
        react_fn: Optional[Callable[..., Awaitable]] = None,
        unreact_fn: Optional[Callable[..., Awaitable]] = None,
    ):
        """
        Args:
            channel_id: Channel identifier (telegram, discord, slack, etc.)
            message_ref: Platform-specific reference (message object, chat_id+msg_id, etc.)
            react_fn: Async function to add a reaction: react_fn(message_ref, emoji)
            unreact_fn: Async function to remove a reaction: unreact_fn(message_ref, emoji)
        """
        self.channel_id = channel_id
        self.message_ref = message_ref
        self._react_fn = react_fn
        self._unreact_fn = unreact_fn
        self._current_phase: Optional[str] = None
        self._emojis = get_emojis(channel_id)

    async def phase(self, phase_name: str):
        """Transition to a new lifecycle phase."""
        emoji = getattr(self._emojis, phase_name, None)
        if not emoji:
            logger.warning(f"Unknown lifecycle phase: {phase_name}")
            return

        # Remove previous reaction if transitioning
        if self._current_phase and self._current_phase != phase_name:
            old_emoji = getattr(self._emojis, self._current_phase, None)
            if old_emoji and self._unreact_fn:
                try:
                    await self._unreact_fn(self.message_ref, old_emoji)
                except Exception as e:
                    logger.debug(f"Could not remove reaction {old_emoji}: {e}")

        # Add new reaction
        self._current_phase = phase_name
        if self._react_fn:
            try:
                await self._react_fn(self.message_ref, emoji)
            except Exception as e:
                logger.debug(f"Could not add reaction {emoji}: {e}")

    async def done(self):
        """Mark processing as complete."""
        await self.phase("done")

    async def error(self):
        """Mark processing as failed."""
        await self.phase("error")


# --- Streaming Reply Support ---

class StreamingReply:
    """
    Manages a streaming reply by editing a message in-place.

    Usage:
        stream = StreamingReply(
            send_fn=telegram_send_fn,    # async fn that returns message_ref
            edit_fn=telegram_edit_fn,    # async fn(message_ref, new_text)
            chunk_interval=0.5,          # seconds between edits
        )
        await stream.start(chat_ref)
        await stream.append("Hello ")
        await stream.append("world!")
        await stream.finish()
    """

    def __init__(
        self,
        send_fn: Optional[Callable] = None,
        edit_fn: Optional[Callable] = None,
        chunk_interval: float = 0.5,
        typing_indicator: str = "▍",
    ):
        self._send_fn = send_fn
        self._edit_fn = edit_fn
        self._chunk_interval = chunk_interval
        self._typing_indicator = typing_indicator
        self._message_ref: Any = None
        self._buffer: str = ""
        self._last_edit_time: float = 0
        self._finished = False

    async def start(self, chat_ref: Any):
        """Start streaming by sending an initial placeholder message."""
        if self._send_fn:
            self._message_ref = await self._send_fn(chat_ref, self._typing_indicator)

    async def append(self, text: str):
        """Append text to the streaming buffer and update if interval elapsed."""
        import time
        self._buffer += text
        now = time.time()
        if now - self._last_edit_time >= self._chunk_interval and self._edit_fn and self._message_ref:
            display_text = self._buffer + self._typing_indicator
            try:
                await self._edit_fn(self._message_ref, display_text)
                self._last_edit_time = now
            except Exception as e:
                logger.debug(f"Stream edit failed: {e}")

    async def finish(self):
        """Finalize the stream with the complete text."""
        self._finished = True
        if self._edit_fn and self._message_ref and self._buffer:
            try:
                await self._edit_fn(self._message_ref, self._buffer)
            except Exception as e:
                logger.debug(f"Stream finish failed: {e}")

    @property
    def content(self) -> str:
        return self._buffer


# --- Sub-Agent Spawning ---

@dataclass
class SubAgentConfig:
    """Configuration for nested sub-agent spawning."""
    max_spawn_depth: int = 2
    max_children_per_agent: int = 5
    thread_bound: bool = True  # Bind sub-agent to a specific thread/channel


class SubAgentManager:
    """
    Manages spawned sub-agents for a channel.
    Tracks active sub-agents, enforces depth/count limits.
    """

    def __init__(self, config: Optional[SubAgentConfig] = None):
        self.config = config or SubAgentConfig()
        self._active: Dict[str, Dict[str, Any]] = {}  # parent_id -> {child_id: info}

    def can_spawn(self, parent_id: str, current_depth: int = 0) -> bool:
        """Check if a new sub-agent can be spawned."""
        if current_depth >= self.config.max_spawn_depth:
            logger.warning(f"Max spawn depth ({self.config.max_spawn_depth}) reached")
            return False

        children = self._active.get(parent_id, {})
        if len(children) >= self.config.max_children_per_agent:
            logger.warning(f"Max children ({self.config.max_children_per_agent}) reached for {parent_id}")
            return False

        return True

    def register_child(self, parent_id: str, child_id: str, info: Dict[str, Any] = None):
        """Register a spawned sub-agent."""
        if parent_id not in self._active:
            self._active[parent_id] = {}
        self._active[parent_id][child_id] = info or {}
        logger.info(f"Sub-agent {child_id} spawned by {parent_id}")

    def remove_child(self, parent_id: str, child_id: str):
        """Remove a completed sub-agent."""
        if parent_id in self._active:
            self._active[parent_id].pop(child_id, None)
            if not self._active[parent_id]:
                del self._active[parent_id]

    def list_children(self, parent_id: str) -> Dict[str, Any]:
        """List active sub-agents for a parent."""
        return dict(self._active.get(parent_id, {}))

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all active sub-agents."""
        return dict(self._active)


# --- Per-Channel Model Override ---

_channel_model_overrides: Dict[str, str] = {}


def set_model_override(channel_id: str, model: str):
    """Set a model override for a specific channel."""
    _channel_model_overrides[channel_id] = model
    logger.info(f"Model override for {channel_id}: {model}")


def get_model_override(channel_id: str) -> Optional[str]:
    """Get the model override for a channel, or None for default."""
    return _channel_model_overrides.get(channel_id)


def clear_model_override(channel_id: str):
    """Remove model override for a channel."""
    _channel_model_overrides.pop(channel_id, None)


# --- DM Access Control ---

@dataclass
class DMPolicy:
    """Unified DM access control policy."""
    mode: str = "all"           # "all", "allowlist", "owner_only", "none"
    allow_from: list = field(default_factory=list)  # List of allowed user IDs


_channel_dm_policies: Dict[str, DMPolicy] = {}


def set_dm_policy(channel_id: str, policy: DMPolicy):
    """Set DM access control policy for a channel."""
    _channel_dm_policies[channel_id] = policy


def get_dm_policy(channel_id: str) -> DMPolicy:
    """Get DM policy for a channel (defaults to allow all)."""
    return _channel_dm_policies.get(channel_id, DMPolicy())


def check_dm_access(channel_id: str, user_id: str) -> bool:
    """Check if a user has DM access on a channel."""
    policy = get_dm_policy(channel_id)
    if policy.mode == "none":
        return False
    if policy.mode == "all":
        return True
    if policy.mode == "allowlist":
        return user_id in policy.allow_from
    if policy.mode == "owner_only":
        return len(policy.allow_from) > 0 and user_id == policy.allow_from[0]
    return True
