"""
API endpoint: /webhook_incoming
Methods: GET, POST
No auth required (uses Bearer token validation internally).

Receives inbound webhook calls for channel plugins (WhatsApp, generic Webhook).
Routes payloads to the appropriate ChannelAdapter's handle_webhook() method.

GET  /webhook_incoming?hub.mode=subscribe&...  →  WhatsApp verification challenge
POST /webhook_incoming                         →  Incoming message payload
"""

import json
import logging
from python.helpers.api import ApiHandler, Input, Output, Request, Response
from python.helpers import files

logger = logging.getLogger("agent-zero.api.webhook_incoming")


class Webhook_incoming(ApiHandler):
    """
    Webhook receiver for channel plugins.
    Auto-discovered by the Flask loader (filename = route name).
    """

    @classmethod
    def requires_auth(cls) -> bool:
        """Webhooks must not require UI auth — platforms (Meta, etc.) call this."""
        return False

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def requires_loopback(cls) -> bool:
        """Allow external webhook calls (not just loopback)."""
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: Input, request: Request) -> Output:
        method = request.method

        # --- GET: WhatsApp verification challenge ---
        if method == "GET":
            return self._handle_verification(request)

        # --- POST: Incoming message payload ---
        if method == "POST":
            return await self._handle_incoming(input, request)

        return Response("Method Not Allowed", status=405)

    def _handle_verification(self, request: Request) -> Output:
        """
        Handle Meta/WhatsApp webhook verification.
        Meta sends: GET ?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<challenge>
        """
        mode = request.args.get("hub.mode", "")
        token = request.args.get("hub.verify_token", "")
        challenge = request.args.get("hub.challenge", "")

        if mode == "subscribe" and token and challenge:
            # Load the expected verify token from plugin config
            import os
            expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
            if token == expected_token:
                logger.info("WhatsApp webhook verified successfully")
                return Response(challenge, status=200, mimetype="text/plain")
            else:
                logger.warning("WhatsApp webhook verification failed (token mismatch)")
                return Response("Forbidden", status=403, mimetype="text/plain")

        return {"ok": True, "message": "Webhook endpoint active"}

    async def _handle_incoming(self, input: Input, request: Request) -> Output:
        """
        Route incoming POST payloads to the appropriate adapter.
        
        Supports:
        - WhatsApp Cloud API (detected by 'object' field = 'whatsapp_business_account')
        - Generic webhook (Bearer token auth, raw payload passthrough)
        """
        payload = input or {}

        # --- Detect WhatsApp ---
        if payload.get("object") == "whatsapp_business_account":
            return await self._route_to_whatsapp(payload)

        # --- Generic webhook ---
        return await self._route_to_generic(payload, request)

    async def _route_to_whatsapp(self, payload: dict) -> Output:
        """Forward to WhatsApp adapter's handle_webhook()."""
        try:
            from python.helpers.plugin_loader import get_channel_adapter
            adapter = get_channel_adapter("whatsapp")
            if adapter and hasattr(adapter, "handle_webhook"):
                await adapter.handle_webhook(payload)
                return {"ok": True, "channel": "whatsapp"}
            else:
                logger.warning("WhatsApp adapter not loaded or missing handle_webhook")
                return {"ok": False, "error": "WhatsApp adapter not available"}
        except Exception as e:
            logger.error(f"Error routing to WhatsApp: {e}")
            return {"ok": False, "error": str(e)}

    async def _route_to_generic(self, payload: dict, request: Request) -> Output:
        """Forward to generic Webhook adapter."""
        # Validate Bearer token
        auth_header = request.headers.get("Authorization", "")
        import os
        expected_token = os.environ.get("WEBHOOK_AUTH_TOKEN", "")

        if expected_token:
            if not auth_header.startswith("Bearer "):
                return Response("Unauthorized", status=401, mimetype="text/plain")
            provided_token = auth_header[7:]  # Strip "Bearer "
            if provided_token != expected_token:
                return Response("Forbidden", status=403, mimetype="text/plain")

        try:
            from python.helpers.plugin_loader import get_channel_adapter
            adapter = get_channel_adapter("webhook")
            if adapter and hasattr(adapter, "handle_webhook"):
                await adapter.handle_webhook(payload)
                return {"ok": True, "channel": "webhook"}
            else:
                # Still accept the webhook even if adapter isn't loaded
                logger.info(f"Webhook received but no adapter loaded: {json.dumps(payload)[:200]}")
                return {"ok": True, "message": "Webhook received (no adapter)"}
        except Exception as e:
            logger.error(f"Error routing to webhook: {e}")
            return {"ok": False, "error": str(e)}
