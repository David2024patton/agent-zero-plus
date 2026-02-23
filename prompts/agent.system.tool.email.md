### email_tool
Send and read emails via SMTP/IMAP. Requires EMAIL_ADDRESS and EMAIL_PASSWORD env vars.
Optionally set EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_IMAP_HOST, EMAIL_IMAP_PORT (defaults: Titan Email).
Methods: send, read, count.
**Send email:**
~~~json
{
    "thoughts": ["User wants to send an email..."],
    "headline": "Sending email",
    "tool_name": "email_tool",
    "tool_args": {
        "method": "send",
        "to": "recipient@example.com",
        "subject": "Hello",
        "body": "Message content here"
    }
}
~~~
**Read inbox (last N emails):**
~~~json
{
    "tool_name": "email_tool",
    "tool_args": {
        "method": "read",
        "count": 5,
        "folder": "INBOX"
    }
}
~~~
**Count emails:**
~~~json
{
    "tool_name": "email_tool",
    "tool_args": {
        "method": "count",
        "folder": "INBOX"
    }
}
~~~
**Parameters:**
- **method** (required): "send", "read", or "count"
- **to** (send): Recipient email address
- **subject** (send): Email subject line
- **body** (send): Plain text body
- **html** (send, optional): HTML body
- **count** (read): Number of recent emails to fetch (default 5)
- **folder** (read/count): Mailbox folder (default "INBOX")
