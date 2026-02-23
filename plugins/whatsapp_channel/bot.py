"""
WhatsApp Channel Adapter for Agent Zero
=========================================
Uses the Meta Cloud API (Graph API) to send/receive WhatsApp messages.
Incoming messages are received via webhook; outgoing via REST API.

Incorporates fixes from OpenClaw PRs:
  - #22335: Harden E164 normalization against empty/invalid inputs
  - #22359: Classify overloaded/503 errors as timeout → retry, not cooldown

Requires: requests (typically already installed)
"""

from __future__ import annotations
import os
import re
import asyncio
import logging
from typing import List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage

logger = logging.getLogger("agent-zero.plugins.whatsapp")

GRAPH_API_URL = "https://graph.facebook.com/v18.0"


# --- OpenClaw #22335: E164 normalization hardening ---
def normalize_e164(phone: str) -> str:
    """
    Normalize a phone number to E.164 format.
    Returns empty string for invalid inputs instead of bare '+'.
    
    Fixes the OpenClaw bug where normalizeE164("") returned "+"
    which downstream treated as valid, causing:
    - Invalid JIDs ("@s.whatsapp.net")
    - Incorrect matches in isSelfChatMode
    - Bypassed guards ('+' is truthy)
    """
    if not phone:
        return ""
    
    # Strip everything except digits and leading +
    cleaned = phone.strip()
    
    # Remove common prefixes
    if cleaned.lower().startswith("whatsapp:"):
        cleaned = cleaned[9:].strip()
    
    # Extract only digits
    digits = re.sub(r"[^\d]", "", cleaned)
    
    # If no digits found, return empty (not bare '+')
    if not digits:
        return ""
    
    # Ensure leading +
    if not cleaned.startswith("+"):
        return f"+{digits}"
    
    return f"+{digits}"


def validate_phone_number(phone: str) -> Optional[str]:
    """Validate and normalize a phone number. Returns None if invalid."""
    normalized = normalize_e164(phone)
    if not normalized or len(normalized) < 4:  # Minimum: +XXX
        return None
    return normalized


# --- OpenClaw #22359: Overload error classification ---
_OVERLOAD_PATTERNS = re.compile(
    r"(overloaded|service.unavailable|high.demand|503|502|temporarily.unavailable)",
    re.IGNORECASE,
)


def _is_overload_error(error: Exception) -> bool:
    """Classify overloaded/service-unavailable as transient timeout, not rate limit."""
    error_text = str(error)
    return bool(_OVERLOAD_PATTERNS.search(error_text))


def _is_overload_response(resp) -> bool:
    """Check if an HTTP response indicates service overload."""
    if resp is None:
        return False
    return resp.status_code in (502, 503, 429)


class WhatsAppChannelAdapter(ChannelAdapter):
    """
    WhatsApp Cloud API adapter.
    Outgoing messages are sent via the Graph API.
    Incoming messages are received by a webhook handler (registered on the
    Agent Zero web server as /webhook/whatsapp).
    """

    # Retry config (OpenClaw #22359)
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        phone_number_id: str = "",
        access_token_env: str = "WHATSAPP_ACCESS_TOKEN",
        verify_token_env: str = "WHATSAPP_VERIFY_TOKEN",
        allowed_numbers: str = "",
    ):
        super().__init__(channel_id="whatsapp")
        self.phone_number_id = phone_number_id
        self.access_token_env = access_token_env
        self.verify_token_env = verify_token_env
        self.allowed_numbers = [n.strip() for n in allowed_numbers.split(",") if n.strip()] if allowed_numbers else []

    async def start(self):
        """Initialize WhatsApp adapter. Webhook must be configured externally."""
        if not HAS_REQUESTS:
            logger.error("requests library not installed.")
            return

        access_token = os.environ.get(self.access_token_env)
        if not access_token:
            logger.error(f"WhatsApp access token not found in env var: {self.access_token_env}")
            return

        if not self.phone_number_id:
            logger.error("WhatsApp phone_number_id not configured")
            return

        logger.info(f"WhatsApp adapter ready (phone: {self.phone_number_id})")

    async def stop(self):
        """Stop the WhatsApp adapter."""
        logger.info("WhatsApp adapter stopped")

    async def handle_webhook(self, payload: dict):
        """Process an incoming webhook payload from Meta."""
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for msg in messages:
                        if msg.get("type") != "text":
                            continue

                        sender = msg.get("from", "")
                        text = msg.get("text", {}).get("body", "")

                        if not text:
                            continue

                        # OpenClaw #22335: Validate phone number
                        normalized_sender = normalize_e164(sender)
                        if not normalized_sender:
                            logger.warning(f"Invalid sender phone number: '{sender}', skipping")
                            continue

                        # Check allowed numbers (using normalized form)
                        if self.allowed_numbers:
                            allowed_normalized = [normalize_e164(n) for n in self.allowed_numbers]
                            if normalized_sender not in allowed_normalized:
                                continue

                        # Find sender name from contacts
                        sender_name = sender
                        for contact in contacts:
                            if contact.get("wa_id") == sender:
                                profile = contact.get("profile", {})
                                sender_name = profile.get("name", sender)
                                break

                        channel_msg = ChannelMessage(
                            channel_id="whatsapp",
                            sender_id=normalized_sender,
                            sender_name=sender_name,
                            content=text,
                            metadata={
                                "message_id": msg.get("id", ""),
                                "timestamp": msg.get("timestamp", ""),
                                "raw_sender": sender,
                            },
                        )

                        await self._dispatch_message(channel_msg)
        except Exception as e:
            logger.error(f"Error processing WhatsApp webhook: {e}")

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send a message via WhatsApp Cloud API.

        'to' format: "phone:<phone_number>" (e.g. "phone:15551234567")
        """
        access_token = os.environ.get(self.access_token_env)
        if not access_token:
            logger.error("WhatsApp access token not available")
            return False

        try:
            _, phone = to.split(":", 1)
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'phone:<number>'")
            return False

        # OpenClaw #22335: Validate recipient phone number
        validated_phone = validate_phone_number(phone)
        if not validated_phone:
            logger.error(f"Invalid phone number: '{phone}' (normalized to empty)")
            return False
        # Strip leading + for WhatsApp API (it expects digits only)
        phone_digits = validated_phone.lstrip("+")

        url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_digits,
            "type": "text",
            "text": {"body": content[:4096]},  # WhatsApp limit
        }

        # OpenClaw #22359: Retry on overload with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)

                # Check for overload before raising
                if _is_overload_response(resp) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(
                        f"WhatsApp API overloaded (HTTP {resp.status_code}, "
                        f"attempt {attempt + 1}/{self.MAX_RETRIES}), "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                resp.raise_for_status()
                return True
            except requests.exceptions.RequestException as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Send overloaded (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to send WhatsApp message: {e}")
                    return False
        return False
