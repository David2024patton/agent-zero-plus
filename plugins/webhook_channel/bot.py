"""
Generic Webhook Channel Adapter for Agent Zero
=================================================
Exposes an HTTP endpoint for sending JSON messages to Agent Zero.
No external dependencies required beyond what Agent Zero already uses.

Expected JSON payload:
{
    "sender_id": "user123",
    "sender_name": "John",
    "message": "Hello Agent Zero",
    "attachments": []
}
"""

from __future__ import annotations
import os
import logging
from typing import List, Optional

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage

logger = logging.getLogger("agent-zero.plugins.webhook")


class WebhookChannelAdapter(ChannelAdapter):
    """
    Generic webhook adapter.
    Receives messages via HTTP POST and dispatches them to Agent Zero.
    Responses are either synchronous (wait for agent reply) or async
    (return a task ID immediately).
    """

    def __init__(
        self,
        webhook_path: str = "/webhook/agent",
        auth_token_env: str = "WEBHOOK_AUTH_TOKEN",
        response_mode: str = "sync",  # "sync" or "async"
    ):
        super().__init__(channel_id="webhook")
        self.webhook_path = webhook_path
        self.auth_token_env = auth_token_env
        self.response_mode = response_mode
        self._responses: dict = {}  # message_id -> response

    async def start(self):
        """Initialize webhook adapter."""
        auth_token = os.environ.get(self.auth_token_env, "")
        if auth_token:
            logger.info(f"Webhook adapter ready at {self.webhook_path} (auth enabled)")
        else:
            logger.info(f"Webhook adapter ready at {self.webhook_path} (no auth)")

    async def stop(self):
        """Stop the webhook adapter."""
        logger.info("Webhook adapter stopped")

    async def handle_webhook(self, payload: dict, auth_header: str = "") -> dict:
        """
        Process an incoming webhook request.

        Returns:
            dict with response data
        """
        # Check auth
        expected_token = os.environ.get(self.auth_token_env, "")
        if expected_token:
            if auth_header != f"Bearer {expected_token}":
                return {"ok": False, "error": "Unauthorized"}

        sender_id = payload.get("sender_id", "webhook_user")
        sender_name = payload.get("sender_name", sender_id)
        message = payload.get("message", "")
        attachments = payload.get("attachments", [])

        if not message:
            return {"ok": False, "error": "No message provided"}

        channel_msg = ChannelMessage(
            channel_id="webhook",
            sender_id=sender_id,
            sender_name=sender_name,
            content=message,
            attachments=attachments,
            metadata={
                "response_mode": self.response_mode,
            },
        )

        await self._dispatch_message(channel_msg)

        return {"ok": True, "message": "Message received"}

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Store a response for webhook retrieval.

        'to' format: "webhook:<request_id>"
        """
        try:
            _, request_id = to.split(":", 1)
            self._responses[request_id] = {
                "content": content,
                "attachments": attachments or [],
            }
            return True
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'webhook:<request_id>'")
            return False
