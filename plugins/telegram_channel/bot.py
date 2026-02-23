"""
Telegram Channel Adapter for Agent Zero
========================================
Uses python-telegram-bot to connect Agent Zero to Telegram.
Supports private messages, group mentions, and command handling.

Incorporates fixes from OpenClaw PRs:
  - #22363: Isolate update offset state by bot token fingerprint
  - #22331: Normalize emoji inputs (trim + NFC normalize)
  - #22359: Classify overloaded/503 errors as timeout → retry, not cooldown
  - #22355: Exponential backoff on reconnect (5s → 5min max)

Requires: pip install python-telegram-bot
"""

from __future__ import annotations
import os
import re
import json
import asyncio
import hashlib
import logging
import unicodedata
from pathlib import Path
from typing import List, Optional

try:
    from telegram import Update
    from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
    from telegram.error import RetryAfter, TimedOut, NetworkError
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage
from python.helpers.lifecycle_reactions import (
    LifecycleTracker, StreamingReply, get_emojis,
    check_dm_access, get_model_override,
)

logger = logging.getLogger("agent-zero.plugins.telegram")

# --- OpenClaw #22363: Token-scoped offset isolation ---
OFFSET_STATE_DIR = Path("usr/plugin_state/telegram")


def _token_fingerprint(token: str) -> str:
    """Create a short fingerprint of the bot token for offset isolation.
    Prevents cross-token offset reuse in multi-bot deployments."""
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def read_telegram_offset(token: str) -> Optional[int]:
    """Read the stored update offset for a specific bot token."""
    fingerprint = _token_fingerprint(token)
    offset_file = OFFSET_STATE_DIR / f"offset_{fingerprint}.json"
    try:
        if offset_file.exists():
            data = json.loads(offset_file.read_text())
            # Migration safety: if file has no fingerprint field, it's legacy v1
            if data.get("fingerprint") != fingerprint:
                logger.info(f"Ignoring legacy offset file (no fingerprint match)")
                return None
            return data.get("offset")
    except Exception as e:
        logger.warning(f"Failed to read offset state: {e}")
    return None


def write_telegram_offset(token: str, offset: int):
    """Write the update offset scoped to a specific bot token."""
    fingerprint = _token_fingerprint(token)
    OFFSET_STATE_DIR.mkdir(parents=True, exist_ok=True)
    offset_file = OFFSET_STATE_DIR / f"offset_{fingerprint}.json"
    try:
        offset_file.write_text(json.dumps({
            "fingerprint": fingerprint,
            "offset": offset,
        }))
    except Exception as e:
        logger.warning(f"Failed to write offset state: {e}")


# --- OpenClaw #22331: Emoji normalization ---
def normalize_emoji(text: str) -> str:
    """Trim and NFC-normalize emoji strings to prevent REACTION_INVALID."""
    if not text:
        return ""
    return unicodedata.normalize("NFC", text.strip())


# --- OpenClaw #22359: Overload error classification ---
_OVERLOAD_PATTERNS = re.compile(
    r"(overloaded|service.unavailable|high.demand|503|502|temporarily.unavailable)",
    re.IGNORECASE,
)


def _is_overload_error(error: Exception) -> bool:
    """Classify overloaded/service-unavailable as transient timeout, not rate limit."""
    error_text = str(error)
    return bool(_OVERLOAD_PATTERNS.search(error_text))


class TelegramChannelAdapter(ChannelAdapter):
    """
    Telegram channel adapter.
    Listens for private messages and group mentions, dispatches them as
    ChannelMessages, and can send messages back.
    """

    # Retry config (OpenClaw #22359)
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2.0

    # Reconnect config (OpenClaw #22355)
    RECONNECT_INITIAL_DELAY = 5.0
    RECONNECT_MAX_DELAY = 300.0  # 5 minutes

    def __init__(
        self,
        bot_token_env: str = "TELEGRAM_BOT_TOKEN",
        allowed_users: str = "",
        respond_to_groups: bool = True,
        respond_to_private: bool = True,
    ):
        super().__init__(channel_id="telegram")
        self.bot_token_env = bot_token_env
        self.allowed_users = [u.strip() for u in allowed_users.split(",") if u.strip()] if allowed_users else []
        self.respond_to_groups = respond_to_groups
        self.respond_to_private = respond_to_private
        self._app: Optional[Application] = None
        self._token: Optional[str] = None
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
        self._should_reconnect = True
        self._reconnect_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the Telegram bot with token-scoped offset tracking."""
        if not HAS_TELEGRAM:
            logger.error("python-telegram-bot is not installed. Run: pip install python-telegram-bot")
            return

        self._token = os.environ.get(self.bot_token_env)
        if not self._token:
            logger.error(f"Telegram bot token not found in env var: {self.bot_token_env}")
            return

        self._app = Application.builder().token(self._token).build()

        # Handle all text messages
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message
        ))

        # OpenClaw #22363: Restore token-scoped offset
        stored_offset = read_telegram_offset(self._token)
        if stored_offset is not None:
            logger.info(f"Resuming from stored offset {stored_offset} "
                        f"(token fingerprint: {_token_fingerprint(self._token)})")

        logger.info("Starting Telegram bot...")

        # OpenClaw #22359: Retry on overload with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                await self._app.initialize()
                await self._app.start()
                await self._app.updater.start_polling(
                    # Use stored offset if available (OpenClaw #22363)
                    offset=stored_offset,
                    allowed_updates=Update.ALL_TYPES,
                )
                logger.info("Telegram bot started successfully")
                return
            except Exception as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        f"Telegram service overloaded (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                        f"retrying in {wait_time}s... ({e})"
                    )
                    await asyncio.sleep(wait_time)
                elif isinstance(e, RetryAfter) if HAS_TELEGRAM else False:
                    logger.warning(f"Telegram rate limited, waiting {e.retry_after}s")
                    await asyncio.sleep(e.retry_after)
                else:
                    logger.error(f"Failed to start Telegram bot: {e}")
                    raise

        # OpenClaw #22355: Start reconnect monitor
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY  # Clear on success
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """OpenClaw #22355: Auto-reconnect with exponential backoff on disconnect."""
        while self._should_reconnect:
            try:
                # Wait for the polling to finish (it shouldn't unless disconnected)
                if self._app and self._app.updater and self._app.updater.running:
                    await asyncio.sleep(10)  # Check every 10s
                    self._reconnect_delay = self.RECONNECT_INITIAL_DELAY  # Clear on success
                    continue

                if not self._should_reconnect:
                    break

                logger.warning(
                    f"Telegram connection lost. Reconnecting in {self._reconnect_delay:.0f}s..."
                )
                await asyncio.sleep(self._reconnect_delay)

                # Escalate backoff (OpenClaw #22355: double each failure, cap at 5min)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self.RECONNECT_MAX_DELAY
                )

                # Attempt reconnect
                try:
                    if self._app:
                        stored_offset = read_telegram_offset(self._token) if self._token else None
                        await self._app.updater.start_polling(
                            offset=stored_offset,
                            allowed_updates=Update.ALL_TYPES,
                        )
                        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY  # Clear on success
                        logger.info("Telegram reconnected successfully")
                except Exception as e:
                    logger.error(f"Telegram reconnect failed: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnect loop error: {e}")
                await asyncio.sleep(self._reconnect_delay)

    async def stop(self):
        """Stop the Telegram bot gracefully and persist offset."""
        self._should_reconnect = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._app:
            # OpenClaw #22363: Save current offset before shutdown
            if self._token and self._app.updater and hasattr(self._app.updater, '_last_update_id'):
                write_telegram_offset(self._token, self._app.updater._last_update_id)
                logger.info(f"Saved offset state (fingerprint: {_token_fingerprint(self._token)})")

            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot disconnected")

    # --- Lifecycle Reaction helpers ---
    async def _react(self, message_ref: dict, emoji: str):
        """Add an emoji reaction to a Telegram message."""
        try:
            if self._app and message_ref:
                await self._app.bot.set_message_reaction(
                    chat_id=int(message_ref["chat_id"]),
                    message_id=int(message_ref["message_id"]),
                    reaction=[{"type": "emoji", "emoji": emoji}],
                )
        except Exception as e:
            logger.debug(f"Could not set reaction {emoji}: {e}")

    async def _unreact(self, message_ref: dict, emoji: str):
        """Remove an emoji reaction from a Telegram message."""
        try:
            if self._app and message_ref:
                await self._app.bot.set_message_reaction(
                    chat_id=int(message_ref["chat_id"]),
                    message_id=int(message_ref["message_id"]),
                    reaction=[],
                )
        except Exception as e:
            logger.debug(f"Could not remove reaction: {e}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming Telegram messages with lifecycle tracking."""
        if not update.message or not update.message.text:
            return

        # OpenClaw #22363: Track offset per message
        if self._token and update.update_id:
            write_telegram_offset(self._token, update.update_id + 1)

        user = update.message.from_user
        chat = update.message.chat
        # OpenClaw #22331: NFC normalize incoming text
        content = normalize_emoji(update.message.text)

        # Check allowed users
        if self.allowed_users and str(user.id) not in self.allowed_users:
            return

        # DM access control check
        if chat.type == "private" and not check_dm_access("telegram", str(user.id)):
            return

        # Private message
        if chat.type == "private":
            if not self.respond_to_private:
                return
        # Group/supergroup
        elif chat.type in ("group", "supergroup"):
            if not self.respond_to_groups:
                return
        else:
            return

        # Build attachments list
        attachments = []
        if update.message.photo:
            photo = update.message.photo[-1]  # highest resolution
            file = await context.bot.get_file(photo.file_id)
            attachments.append(file.file_path)

        # --- Lifecycle reactions ---
        msg_ref = {
            "chat_id": str(chat.id),
            "message_id": str(update.message.message_id),
        }
        tracker = LifecycleTracker(
            channel_id="telegram",
            message_ref=msg_ref,
            react_fn=self._react,
            unreact_fn=self._unreact,
        )

        # Create ChannelMessage with lifecycle tracker
        channel_msg = ChannelMessage(
            channel_id="telegram",
            sender_id=str(user.id),
            sender_name=user.full_name or user.username or str(user.id),
            content=content,
            attachments=attachments,
            metadata={
                "chat_id": str(chat.id),
                "chat_type": chat.type,
                "message_id": str(update.message.message_id),
                "is_private": chat.type == "private",
                "lifecycle_tracker": tracker,
                "model_override": get_model_override("telegram"),
            },
        )

        # Show queued reaction and typing indicator
        await tracker.phase("queued")
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")

        try:
            await tracker.phase("thinking")
            await self._dispatch_message(channel_msg)
            await tracker.done()
        except Exception as e:
            await tracker.error()
            logger.error(f"Error handling Telegram message: {e}")
            raise

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           streaming: bool = False,
                           **kwargs) -> bool:
        """
        Send a message to a Telegram target.

        'to' format: "chat:<chat_id>"
        Set streaming=True to edit the message in-place for a streaming effect.
        """
        if not self._app:
            logger.error("Telegram client not connected")
            return False

        try:
            _, chat_id = to.split(":", 1)
            chat_id = int(chat_id)
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'chat:<chat_id>'")
            return False

        # OpenClaw #22359: Retry on overload for sends too
        for attempt in range(self.MAX_RETRIES):
            try:
                # Telegram message limit: 4096 chars
                chunks = self._split_message(content, max_length=4096)
                for chunk in chunks:
                    await self._app.bot.send_message(chat_id=chat_id, text=chunk)
                return True
            except Exception as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Send overloaded (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                elif isinstance(e, RetryAfter) if HAS_TELEGRAM else False:
                    logger.warning(f"Rate limited, waiting {e.retry_after}s")
                    await asyncio.sleep(e.retry_after)
                else:
                    logger.error(f"Failed to send Telegram message: {e}")
                    return False
        return False

    async def send_streaming(self, chat_id: int, content_chunks) -> bool:
        """
        Send a streaming reply by editing a message in-place.
        Provides real-time feedback as the response is generated.

        Args:
            chat_id: Telegram chat ID.
            content_chunks: Async iterable of text chunks.
        """
        if not self._app:
            return False

        try:
            # Send initial placeholder
            msg = await self._app.bot.send_message(chat_id=chat_id, text="▍")
            buffer = ""
            import time
            last_edit = 0

            async for chunk in content_chunks:
                buffer += chunk
                now = time.time()
                # Edit at most every 0.5s to avoid rate limits
                if now - last_edit >= 0.5:
                    try:
                        await self._app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg.message_id,
                            text=buffer + "▍",
                        )
                        last_edit = now
                    except Exception:
                        pass

            # Final edit with complete text
            if buffer:
                await self._app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=buffer,
                )
            return True

        except Exception as e:
            logger.error(f"Streaming reply failed: {e}")
            return False

    @staticmethod
    def _split_message(content: str, max_length: int = 4096) -> List[str]:
        """Split a long message into chunks that fit Telegram's limit."""
        if len(content) <= max_length:
            return [content]

        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break
            split_at = content.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = content.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length
            chunks.append(content[:split_at])
            content = content[split_at:].lstrip()
        return chunks
