"""
Email Channel Plugin for Agent Zero
=====================================
Connects Agent Zero to email via IMAP/SMTP.
Polls IMAP for incoming emails and replies via SMTP.
No external dependencies — uses Python's built-in imaplib + smtplib.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import EmailChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    imap_host = api.get_config("imap_host", "")
    imap_port = int(api.get_config("imap_port", 993))
    imap_user = api.get_config("imap_user", "")
    imap_password = api.get_config("imap_password", "")
    smtp_host = api.get_config("smtp_host", "")
    smtp_port = int(api.get_config("smtp_port", 587))
    smtp_user = api.get_config("smtp_user", "")
    smtp_password = api.get_config("smtp_password", "")
    use_tls = api.get_config("use_tls", True)
    poll_interval = int(api.get_config("poll_interval", 30))
    allowed_senders = api.get_config("allowed_senders", "")

    adapter = EmailChannelAdapter(
        imap_host=imap_host,
        imap_port=imap_port,
        imap_user=imap_user,
        imap_password=imap_password,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        use_tls=use_tls,
        poll_interval=poll_interval,
        allowed_senders=allowed_senders,
    )

    api.register_channel(adapter)
