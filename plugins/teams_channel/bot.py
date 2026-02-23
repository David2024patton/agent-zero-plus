"""
Microsoft Teams Channel Adapter for Agent Zero
=================================================
Uses the Bot Framework SDK to connect Agent Zero to Microsoft Teams.
Supports 1:1 chats, group chats, and channel @mentions.

Incorporates fixes from OpenClaw PRs:
  - #22359: Classify overloaded/503 errors as timeout → retry, not cooldown

Requires: pip install botbuilder-core botbuilder-schema aiohttp
"""

from __future__ import annotations
import os
import re
import asyncio
import logging
from typing import List, Optional

try:
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
    from botbuilder.schema import Activity, ActivityTypes
    HAS_BOTBUILDER = True
except ImportError:
    HAS_BOTBUILDER = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage

logger = logging.getLogger("agent-zero.plugins.teams")


# --- OpenClaw #22359: Overload error classification ---
_OVERLOAD_PATTERNS = re.compile(
    r"(overloaded|service.unavailable|high.demand|503|502|temporarily.unavailable)",
    re.IGNORECASE,
)


def _is_overload_error(error: Exception) -> bool:
    """Classify overloaded/service-unavailable as transient timeout, not rate limit."""
    return bool(_OVERLOAD_PATTERNS.search(str(error)))


class TeamsChannelAdapter(ChannelAdapter):
    """
    Microsoft Teams adapter using the Bot Framework SDK.
    Receives messages via the Bot Framework messaging endpoint
    and sends responses back through the same framework.
    """

    # Retry config (OpenClaw #22359)
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        app_id: str = "",
        app_password_env: str = "TEAMS_APP_PASSWORD",
        tenant_id: str = "",
        respond_to_personal: bool = True,
        respond_to_channels: bool = True,
    ):
        super().__init__(channel_id="teams")
        self.app_id = app_id
        self.app_password_env = app_password_env
        self.tenant_id = tenant_id
        self.respond_to_personal = respond_to_personal
        self.respond_to_channels = respond_to_channels
        self._adapter: Optional[BotFrameworkAdapter] = None

    async def start(self):
        """Initialize the Bot Framework adapter."""
        if not HAS_BOTBUILDER:
            logger.error("botbuilder-core is not installed. Run: pip install botbuilder-core botbuilder-schema")
            return

        app_password = os.environ.get(self.app_password_env, "")
        if not self.app_id:
            logger.error("Teams App ID not configured")
            return
        if not app_password:
            logger.error(f"Teams app password not found in env var: {self.app_password_env}")
            return

        settings = BotFrameworkAdapterSettings(
            app_id=self.app_id,
            app_password=app_password,
        )
        self._adapter = BotFrameworkAdapter(settings)

        logger.info(f"Teams adapter ready (App ID: {self.app_id})")

    async def stop(self):
        """Stop the Teams adapter."""
        logger.info("Teams adapter stopped")

    async def handle_activity(self, activity: Activity):
        """
        Process an incoming Bot Framework Activity.
        Called by the web server's /api/messages endpoint.
        """
        if not self._adapter:
            return

        async def _on_turn(turn_context: TurnContext):
            if turn_context.activity.type == ActivityTypes.message:
                await self._handle_message(turn_context)

        await self._adapter.process_activity(activity, "", _on_turn)

    async def _handle_message(self, turn_context: TurnContext):
        """Handle incoming Teams messages."""
        activity = turn_context.activity
        text = activity.text or ""
        conversation_type = activity.conversation.conversation_type if activity.conversation else ""

        # Remove @mention text
        if activity.entities:
            for entity in activity.entities:
                if entity.type == "mention" and hasattr(entity, "text"):
                    text = text.replace(entity.text, "").strip()

        if not text:
            return

        # Check conversation type
        if conversation_type == "personal":
            if not self.respond_to_personal:
                return
        elif conversation_type == "channel":
            if not self.respond_to_channels:
                return

        sender_id = activity.from_property.id if activity.from_property else ""
        sender_name = activity.from_property.name if activity.from_property else ""

        channel_msg = ChannelMessage(
            channel_id="teams",
            sender_id=sender_id,
            sender_name=sender_name,
            content=text,
            metadata={
                "conversation_id": activity.conversation.id if activity.conversation else "",
                "conversation_type": conversation_type,
                "activity_id": activity.id or "",
                "service_url": activity.service_url or "",
            },
        )

        # Store turn context for reply
        self._last_turn_context = turn_context
        await self._dispatch_message(channel_msg)

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send a message to a Teams conversation.

        'to' format: "conversation:<conversation_id>"
        Uses the turn context from the last received message for replies.
        """
        if not self._adapter:
            logger.error("Teams adapter not initialized")
            return False

        # OpenClaw #22359: Retry on overload with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                # For simple reply, use the stored turn context
                if hasattr(self, "_last_turn_context") and self._last_turn_context:
                    await self._last_turn_context.send_activity(
                        Activity(
                            type=ActivityTypes.message,
                            text=content[:28000],  # Teams limit ~28KB
                        )
                    )
                    return True
                else:
                    logger.error("No turn context available for sending")
                    return False
            except Exception as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Teams API overloaded (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to send Teams message: {e}")
                    return False
        return False
