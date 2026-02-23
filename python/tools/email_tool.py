"""
Agent Zero Tool: email_tool
============================
Send and read emails via SMTP/IMAP using Titan Email credentials.
Requires EMAIL_ADDRESS, EMAIL_PASSWORD environment variables.
"""

import os
import asyncio
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


# Email server defaults (configurable via env vars, Titan fallback)
SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.titan.email")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "465"))
IMAP_HOST = os.environ.get("EMAIL_IMAP_HOST", "imap.titan.email")
IMAP_PORT = int(os.environ.get("EMAIL_IMAP_PORT", "993"))


class EmailTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        addr = os.environ.get("EMAIL_ADDRESS", "").strip()
        pwd = os.environ.get("EMAIL_PASSWORD", "").strip()

        if not addr or not pwd:
            return Response(
                message="Error: EMAIL_ADDRESS and EMAIL_PASSWORD environment variables are required.",
                break_loop=False,
            )

        try:
            if method == "send":
                return await asyncio.to_thread(self._send, addr, pwd)
            elif method == "read":
                return await asyncio.to_thread(self._read, addr, pwd)
            elif method == "count":
                return await asyncio.to_thread(self._count, addr, pwd)
            else:
                return Response(
                    message="Error: 'method' is required. Supported: send, read, count.",
                    break_loop=False,
                )
        except Exception as e:
            PrintStyle().error(f"Email tool error: {e}")
            return Response(message=f"Email error: {e}", break_loop=False)

    def _send(self, addr: str, pwd: str) -> Response:
        to = (self.args.get("to") or "").strip()
        subject = (self.args.get("subject") or "").strip()
        body = (self.args.get("body") or "").strip()
        html = (self.args.get("html") or "").strip()

        if not to:
            return Response(message="Error: 'to' is required.", break_loop=False)
        if not subject:
            return Response(message="Error: 'subject' is required.", break_loop=False)

        msg = MIMEMultipart("alternative")
        msg["From"] = addr
        msg["To"] = to
        msg["Subject"] = subject

        if body:
            msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))
        elif not body:
            return Response(message="Error: 'body' or 'html' is required.", break_loop=False)

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(addr, pwd)
            server.send_message(msg)

        self.log.update(status="sent", to=to)
        return Response(message=f"Email sent to {to}: \"{subject}\"", break_loop=False)

    def _read(self, addr: str, pwd: str) -> Response:
        count = int(self.args.get("count", 5))
        folder = self.args.get("folder", "INBOX").strip()

        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
            mail.login(addr, pwd)
            mail.select(folder)

            _, data = mail.search(None, "ALL")
            ids = data[0].split()

            if not ids:
                return Response(message="No emails found.", break_loop=False)

            # Get last N emails
            recent_ids = ids[-count:]
            recent_ids.reverse()

            results = []
            for eid in recent_ids:
                _, msg_data = mail.fetch(eid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = self._decode_header(msg["Subject"])
                from_addr = self._decode_header(msg["From"])
                date = msg["Date"] or "Unknown"

                # Extract body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                body_preview = body[:300].strip() if body else "(empty)"
                results.append(
                    f"**From:** {from_addr}\n"
                    f"**Date:** {date}\n"
                    f"**Subject:** {subject}\n"
                    f"**Preview:** {body_preview}\n"
                )

        return Response(message="\n---\n".join(results), break_loop=False)

    def _count(self, addr: str, pwd: str) -> Response:
        folder = self.args.get("folder", "INBOX").strip()

        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
            mail.login(addr, pwd)
            _, data = mail.select(folder)
            total = int(data[0])

            _, unseen_data = mail.search(None, "UNSEEN")
            unseen = len(unseen_data[0].split()) if unseen_data[0] else 0

        return Response(
            message=f"**{folder}**: {total} total, {unseen} unread",
            break_loop=False,
        )

    def _decode_header(self, header_val):
        if not header_val:
            return ""
        decoded_parts = decode_header(header_val)
        parts = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return "".join(parts)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        kvps.pop("body", None)  # don't log email body
        kvps.pop("html", None)
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://email {self.agent.agent_name}: Email",
            content="",
            kvps=kvps,
        )
