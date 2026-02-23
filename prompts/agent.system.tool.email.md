### email_tool
Send and read emails via SMTP/IMAP. Requires EMAIL_ADDRESS and EMAIL_PASSWORD env vars.
Optionally set EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_IMAP_HOST, EMAIL_IMAP_PORT (defaults: Titan Email).
Methods: send, read, count.

## CRITICAL: Email formatting rules
- **Always send ONE email per request. Never send two emails for the same task.**
- **Always use the `html` parameter** for outgoing emails so they render beautifully.
- **Always provide a plain `body` fallback** alongside the `html` for email clients that don't render HTML.
- When summarizing news, articles, or research: include a short summary of each item AND a clickable reference link in the same email.
- Use the branded HTML template below as your starting point for all outgoing emails.

**Send email (HTML with links — use this pattern always):**
~~~json
{
    "thoughts": ["I need to send one polished email with summaries and clickable reference links using the html parameter..."],
    "headline": "Sending email",
    "tool_name": "email_tool",
    "tool_args": {
        "method": "send",
        "to": "recipient@example.com",
        "subject": "Your subject here",
        "body": "Plain text fallback of the email content with URLs as raw text.",
        "html": "<html>...branded HTML template with inline styles...</html>"
    }
}
~~~

## Branded HTML email template
When composing ANY outgoing email, wrap your content in this template. Adapt the content section for each use case.
All styles MUST be inline (no external CSS). Keep it clean, professional, and mobile-friendly.

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#1a73e8,#4285f4);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:22px;">🤖 Agent Zero</h1>
    <p style="margin:4px 0 0;color:rgba(255,255,255,0.85);font-size:12px;letter-spacing:1px;">INTELLIGENT TASK AUTOMATION</p>
  </td>
  <td style="background:linear-gradient(135deg,#1a73e8,#4285f4);padding:24px 32px;text-align:right;">
    <span style="color:rgba(255,255,255,0.85);font-size:12px;">{{DATE}}</span>
  </td></tr>

  <!-- Subject line -->
  <tr><td colspan="2" style="padding:20px 32px 8px;">
    <h2 style="margin:0;color:#1a73e8;font-size:18px;">{{SUBJECT_LINE}}</h2>
  </td></tr>

  <!-- Content area — adapt this for each email -->
  <tr><td colspan="2" style="padding:12px 32px 24px;color:#333;font-size:14px;line-height:1.7;">

    {{CONTENT_HERE}}

    <!-- Example: article summary with reference link -->
    <!--
    <div style="margin:16px 0;padding:14px 18px;background:#f8f9fa;border-left:4px solid #1a73e8;border-radius:6px;">
      <strong style="color:#1a73e8;">📰 Article Title</strong><br>
      <span style="color:#555;font-size:13px;">Source Name</span><br>
      <p style="margin:8px 0;color:#333;">Brief summary of the article content here...</p>
      <a href="https://example.com/article" style="color:#1a73e8;text-decoration:none;font-size:13px;">🔗 Read full article →</a>
    </div>
    -->

  </td></tr>

  <!-- Footer -->
  <tr><td colspan="2" style="background:#f8f9fa;padding:16px 32px;border-top:1px solid #e8e8e8;">
    <p style="margin:0;color:#999;font-size:11px;text-align:center;">Sent by Agent Zero • Intelligent Task Automation</p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>
```

## How to format article/news summaries in email
When the user asks about news, research, or articles, format EACH item using this pattern inside the content area:
```html
<div style="margin:16px 0;padding:14px 18px;background:#f8f9fa;border-left:4px solid #1a73e8;border-radius:6px;">
  <strong style="color:#1a73e8;">📰 Article Title Here</strong><br>
  <span style="color:#888;font-size:12px;">Source Name • Date</span>
  <p style="margin:8px 0 6px;color:#333;font-size:14px;">2-3 sentence summary of what this article covers and why it matters...</p>
  <a href="https://actual-url.com/article" style="color:#1a73e8;text-decoration:none;font-size:13px;font-weight:bold;">🔗 Read full article →</a>
</div>
```
- Every article MUST have a clickable `<a href>` reference link
- Every article MUST have a 2-3 sentence summary
- Include the source name and date when available
- Use emoji icons to categorize (📰 news, 💰 finance, 🔬 research, 🤖 AI, etc.)

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
- **body** (send): Plain text fallback (always include this alongside html)
- **html** (send): HTML body with inline styles — **always use this for outgoing emails**
- **count** (read): Number of recent emails to fetch (default 5)
- **folder** (read/count): Mailbox folder (default "INBOX")
