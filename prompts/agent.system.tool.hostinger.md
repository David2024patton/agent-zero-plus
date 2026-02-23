### hostinger_tool
Manage Hostinger domains and DNS records. Requires HOSTINGER_API_TOKEN env var.
Methods: list_domains, get_dns, add_dns, update_dns, delete_dns, ssl_status, list_hosting.
**Example — list DNS records:**
~~~json
{
    "tool_name": "hostinger_tool",
    "tool_args": {
        "method": "get_dns",
        "domain": "example.com"
    }
}
~~~
**Example — add DNS record:**
~~~json
{
    "tool_name": "hostinger_tool",
    "tool_args": {
        "method": "add_dns",
        "domain": "example.com",
        "type": "A",
        "name": "@",
        "value": "1.2.3.4",
        "ttl": 14400
    }
}
~~~
**Parameters by method:**
- **list_domains**: (no args)
- **get_dns**: domain (required)
- **add_dns**: domain, type (A/AAAA/CNAME/MX/TXT), name, value, ttl
- **update_dns**: domain, record_id, value, ttl
- **delete_dns**: domain, record_id
- **ssl_status**: domain (required) — checks SSL certificate validity and expiry
- **list_hosting**: (no args) — lists hosting accounts with plan/status
