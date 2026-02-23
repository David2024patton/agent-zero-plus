"""
Email Channel Adapter for Agent Zero
======================================
Uses Python's built-in imaplib + smtplib to poll for incoming emails
and send replies. No external dependencies required.

IMAP polling runs in an async loop, checking for unseen emails at a
configurable interval. Replies are sent via SMTP with HTML formatting.
"""

from __future__ import annotations
import os
import asyncio
import imaplib
import re
import smtplib
import email
import email.utils
import html
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import List, Optional

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage

logger = logging.getLogger("agent-zero.plugins.email")


def _decode_header_value(value: str) -> str:
    """Decode an email header value that may be encoded (RFC 2047)."""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    """Extract the plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            # Skip attachments
            if "attachment" in content_disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            elif content_type == "text/html":
                # Fallback to HTML if no plain text
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


class EmailChannelAdapter(ChannelAdapter):
    """
    Email channel adapter.
    Polls IMAP for new unread emails, dispatches them as ChannelMessages,
    and replies via SMTP.
    """

    def __init__(
        self,
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_password: str = "",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        use_tls: bool = True,
        poll_interval: int = 30,
        allowed_senders: str = "",
    ):
        super().__init__(channel_id="email")
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_user = imap_user
        self.imap_password = imap_password
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.use_tls = use_tls
        self.poll_interval = max(poll_interval, 10)  # Minimum 10s
        self.allowed_senders = [
            s.strip().lower()
            for s in allowed_senders.split(",")
            if s.strip()
        ] if allowed_senders else []
        self._poll_task: Optional[asyncio.Task] = None
        self._should_poll = True
        self._imap: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None

    async def start(self):
        """Start the email polling loop."""
        if not self.imap_host or not self.imap_user:
            logger.error("Email plugin: IMAP host and user are required")
            return

        # Also need IMAP password (from env or config)
        password = self.imap_password or os.environ.get("EMAIL_IMAP_PASSWORD", "")
        if not password:
            logger.error("Email plugin: IMAP password is required")
            return

        self.imap_password = password

        # Resolve SMTP password if not set
        if not self.smtp_password:
            self.smtp_password = os.environ.get("EMAIL_SMTP_PASSWORD", self.imap_password)

        # Default SMTP user to IMAP user if not set
        if not self.smtp_user:
            self.smtp_user = self.imap_user

        logger.info(
            f"Starting email polling: {self.imap_user}@{self.imap_host}:{self.imap_port} "
            f"(every {self.poll_interval}s, TLS={'on' if self.use_tls else 'off'})"
        )

        self._should_poll = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop the email polling loop and close connections."""
        self._should_poll = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

        logger.info("Email polling stopped")

    async def _poll_loop(self):
        """Main polling loop — runs in background, checks IMAP for unseen emails."""
        while self._should_poll:
            try:
                await self._check_inbox()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Email poll error: {e}")
                # Close stale connection so next cycle reconnects
                if self._imap:
                    try:
                        self._imap.logout()
                    except Exception:
                        pass
                    self._imap = None

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    def _connect_imap(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Create and authenticate an IMAP connection."""
        if self.use_tls:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        else:
            conn = imaplib.IMAP4(self.imap_host, self.imap_port)
        conn.login(self.imap_user, self.imap_password)
        return conn

    async def _check_inbox(self):
        """Check for unseen emails and dispatch them as ChannelMessages."""
        # Run blocking IMAP operations in a thread
        loop = asyncio.get_event_loop()
        messages = await loop.run_in_executor(None, self._fetch_unseen)

        for msg_data in messages:
            sender_email = msg_data["from_email"]
            sender_name = msg_data["from_name"]
            subject = msg_data["subject"]
            body = msg_data["body"]
            message_id = msg_data["message_id"]
            uid = msg_data["uid"]

            # Frame the email with composition instructions for the agent
            email_instructions = (
                f"📧 INCOMING EMAIL\n"
                f"From: {sender_name} <{sender_email}>\n"
                f"Subject: {subject}\n"
                f"---\n"
                f"{body}\n"
                f"---\n\n"
                f"IMPORTANT — You are responding via EMAIL, not chat. Follow these rules:\n"
                f"1. RESPOND DIRECTLY to what they asked. Do NOT just summarize their email back to them.\n"
                f"2. If they ask a question (e.g. 'what's the latest AI news'), USE YOUR TOOLS to research it first, "
                f"then compose a thorough, well-researched answer.\n"
                f"3. Include REAL URLs/links (e.g. https://example.com/article) — search the web to find actual sources.\n"
                f"4. Use the email_tool with the 'html' parameter and the branded HTML template from your instructions.\n"
                f"5. ALL content (greeting, articles, links, summaries) must go in ONE SINGLE email.\n"
                f"6. Call email_tool EXACTLY ONCE. After sending, use the 'response' tool to confirm in chat.\n"
                f"7. NEVER send a second email to confirm or summarize. One email, that's it.\n"
                f"8. Sign off as 'Agent Zero' or the configured agent name.\n\n"
                f"Send the email to {sender_email} using the email_tool."
            )
            content = email_instructions

            channel_msg = ChannelMessage(
                channel_id="email",
                sender_id=sender_email,
                sender_name=sender_name or sender_email,
                content=content,
                attachments=[],
                metadata={
                    "message_id": message_id,
                    "uid": uid,
                    "subject": subject,
                    "from_email": sender_email,
                    "is_email": True,
                },
            )

            try:
                await self._dispatch_message(channel_msg)
            except Exception as e:
                logger.error(f"Error processing email from {sender_email}: {e}")

    def _fetch_unseen(self) -> list:
        """Blocking: connect to IMAP, fetch unseen messages, mark as read."""
        results = []

        try:
            # Reconnect if needed
            if self._imap is None:
                self._imap = self._connect_imap()

            self._imap.select("INBOX")
            status, data = self._imap.search(None, "UNSEEN")

            if status != "OK" or not data[0]:
                return results

            uids = data[0].split()
            for uid in uids:
                try:
                    status, msg_data = self._imap.fetch(uid, "(RFC822)")
                    if status != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Parse sender
                    from_header = msg.get("From", "")
                    from_name, from_email = email.utils.parseaddr(from_header)
                    from_name = _decode_header_value(from_name)
                    from_email = from_email.lower()

                    # Check allowed senders
                    if self.allowed_senders and from_email not in self.allowed_senders:
                        logger.debug(f"Ignoring email from non-allowed sender: {from_email}")
                        continue

                    # Parse subject and body
                    subject = _decode_header_value(msg.get("Subject", ""))
                    body = _extract_body(msg)
                    message_id = msg.get("Message-ID", "")

                    results.append({
                        "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                        "from_email": from_email,
                        "from_name": from_name,
                        "subject": subject,
                        "body": body.strip(),
                        "message_id": message_id,
                    })

                    # Mark as read
                    self._imap.store(uid, "+FLAGS", "\\Seen")

                except Exception as e:
                    logger.error(f"Error parsing email UID {uid}: {e}")

        except imaplib.IMAP4.abort:
            logger.warning("IMAP connection aborted, will reconnect next cycle")
            self._imap = None
        except Exception as e:
            logger.error(f"IMAP fetch error: {e}")
            self._imap = None

        return results

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send an email reply via SMTP.

        'to' formats:
          - "email:<address>" — e.g. "email:user@example.com"
          - Raw email address — e.g. "user@example.com"
        """
        if not self.smtp_host or not self.smtp_user:
            logger.error("Email plugin: SMTP not configured")
            return False

        # Parse destination
        if to.startswith("email:"):
            recipient = to.split(":", 1)[1].strip()
        elif "@" in to:
            recipient = to.strip()
        else:
            logger.error(f"Invalid email 'to' format: {to}")
            return False

        # Get subject from kwargs or generate default
        subject = kwargs.get("subject", "Re: Agent Zero")

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_smtp,
                recipient,
                subject,
                content,
            )
            logger.info(f"Email sent to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False

    def _markdown_to_html(self, text: str) -> str:
        """Convert markdown-ish text to HTML for rich email rendering."""
        # Escape HTML entities first
        text = html.escape(text)

        # Convert markdown bold **text** to <strong>
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Convert markdown italic *text* to <em> (but not inside strong)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)

        # Convert markdown headers
        text = re.sub(r'^### (.+)$', r'<h3 style="color:#2563eb;margin:16px 0 8px 0;">\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2 style="color:#1d4ed8;margin:20px 0 10px 0;">\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1 style="color:#1e40af;margin:24px 0 12px 0;">\1</h1>', text, flags=re.MULTILINE)

        # Convert markdown links [text](url) to <a href>
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color:#2563eb;">\1</a>', text)

        # Convert bare URLs to clickable links
        text = re.sub(
            r'(?<!href=")(https?://[^\s<>"\)]+)',
            r'<a href="\1" style="color:#2563eb;">\1</a>',
            text
        )

        # Convert unordered lists (- item or * item)
        text = re.sub(r'^[\-\*] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        # Wrap consecutive <li> items in <ul>
        text = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul style="margin:8px 0;padding-left:24px;">\1</ul>', text)

        # Convert numbered lists (1. item)
        text = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        # Note: numbered <li> items also get wrapped; could enhance further

        # Convert --- horizontal rules
        text = re.sub(r'^---+$', r'<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">', text, flags=re.MULTILINE)

        # Convert line breaks to <br> for remaining plain text lines
        text = re.sub(r'\n(?!<)', r'<br>\n', text)

        return text

    def _load_template(self) -> str:
        """Load the HTML email template, with caching."""
        if hasattr(self, "_cached_template") and self._cached_template:
            return self._cached_template

        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "email_template.html"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                self._cached_template = f.read()
            logger.info("Loaded email template from %s", template_path)
            return self._cached_template
        except FileNotFoundError:
            logger.warning("email_template.html not found, using fallback")
            return ""

    def _send_smtp(self, recipient: str, subject: str, body: str):
        """Blocking: send an email via SMTP with HTML formatting."""
        from datetime import datetime

        msg = MIMEMultipart("alternative")
        msg["From"] = self.smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject

        # Plain text fallback
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Rich HTML version — use template if available
        html_body = self._markdown_to_html(body)
        template = self._load_template()

        if template:
            # Inject content into the branded template
            html_email = template.replace("{{CONTENT}}", html_body)
            html_email = html_email.replace("{{SUBJECT}}", html.escape(subject))
            html_email = html_email.replace("{{DATE}}", datetime.now().strftime("%b %d, %Y • %I:%M %p"))
            html_email = html_email.replace("{{SENDER_EMAIL}}", html.escape(self.smtp_user or ""))
        else:
            # Fallback: inline HTML (no template file)
            html_email = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 15px; line-height: 1.6; color: #1f2937; max-width: 680px; margin: 0 auto;
            padding: 20px;">
{html_body}
<br>
<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
<p style="font-size:12px;color:#6b7280;">Sent by Agent Zero &bull; Powered by iTaK</p>
</body>
</html>"""

        msg.attach(MIMEText(html_email, "html", "utf-8"))

        if self.use_tls and self.smtp_port == 465:
            # SSL/TLS on connect (port 465)
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
        else:
            # STARTTLS (port 587) or plain
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
