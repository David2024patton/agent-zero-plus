"""
WhatsApp Channel Plugin for Agent Zero
========================================
Connects Agent Zero to WhatsApp via the Meta Cloud API.
Receives messages via webhook and responds via the Graph API.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import WhatsAppChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    phone_number_id = api.get_config("phone_number_id", "")
    access_token_env = api.get_config("access_token_env", "WHATSAPP_ACCESS_TOKEN")
    verify_token_env = api.get_config("verify_token_env", "WHATSAPP_VERIFY_TOKEN")
    allowed_numbers = api.get_config("allowed_numbers", "")

    adapter = WhatsAppChannelAdapter(
        phone_number_id=phone_number_id,
        access_token_env=access_token_env,
        verify_token_env=verify_token_env,
        allowed_numbers=allowed_numbers,
    )

    api.register_channel(adapter)
