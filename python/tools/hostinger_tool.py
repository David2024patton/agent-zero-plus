"""
Agent Zero Tool: hostinger_tool
=================================
Manage Hostinger domains and DNS records via the Hostinger API.
Requires HOSTINGER_API_TOKEN environment variable.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://api.hostinger.com/v1"


class HostingerTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        token = os.environ.get("HOSTINGER_API_TOKEN", "").strip()
        if not token:
            return Response(
                message="Error: HOSTINGER_API_TOKEN environment variable is required.",
                break_loop=False,
            )

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        methods = {
            "list_domains": self._list_domains,
            "get_dns": self._get_dns,
            "add_dns": self._add_dns,
            "update_dns": self._update_dns,
            "delete_dns": self._delete_dns,
            "ssl_status": self._ssl_status,
            "list_hosting": self._list_hosting,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"Hostinger tool error: {e}")
            return Response(message=f"Hostinger error: {e}", break_loop=False)

    async def _api(self, http_method: str, path: str, body: dict | None = None) -> dict | list:
        async with aiohttp.ClientSession() as session:
            method_fn = getattr(session, http_method)
            kwargs = {"headers": self._headers, "timeout": aiohttp.ClientTimeout(total=30)}
            if body:
                kwargs["json"] = body
            async with method_fn(f"{BASE_URL}{path}", **kwargs) as resp:
                return await resp.json()

    async def _list_domains(self) -> Response:
        data = await self._api("get", "/domains")
        if not data:
            return Response(message="No domains found.", break_loop=False)
        lines = [f"**Domains ({len(data)}):**\n"]
        for d in data:
            name = d.get("domain", d.get("name", "unknown"))
            status = d.get("status", "unknown")
            lines.append(f"- **{name}** (status: {status})")
        return Response(message="\n".join(lines), break_loop=False)

    async def _get_dns(self) -> Response:
        domain = (self.args.get("domain") or "").strip()
        if not domain:
            return Response(message="Error: 'domain' is required.", break_loop=False)
        data = await self._api("get", f"/domains/{domain}/dns")
        if not data:
            return Response(message=f"No DNS records for {domain}.", break_loop=False)

        records = data if isinstance(data, list) else data.get("records", data.get("data", []))
        lines = [f"**DNS Records for {domain}:**\n"]
        for r in records:
            rtype = r.get("type", "?")
            name = r.get("name", "@")
            value = r.get("value", r.get("content", ""))
            ttl = r.get("ttl", "")
            lines.append(f"- `{rtype}` {name} → {value} (TTL: {ttl})")
        return Response(message="\n".join(lines), break_loop=False)

    async def _add_dns(self) -> Response:
        domain = (self.args.get("domain") or "").strip()
        record_type = (self.args.get("type") or "").strip().upper()
        name = (self.args.get("name") or "").strip()
        value = (self.args.get("value") or "").strip()
        ttl = int(self.args.get("ttl", 14400))

        if not domain or not record_type or not value:
            return Response(
                message="Error: 'domain', 'type', and 'value' are required.",
                break_loop=False,
            )

        body = {"type": record_type, "name": name or "@", "value": value, "ttl": ttl}
        data = await self._api("post", f"/domains/{domain}/dns", body)
        return Response(
            message=f"DNS record added: {record_type} {name or '@'} → {value}",
            break_loop=False,
        )

    async def _update_dns(self) -> Response:
        domain = (self.args.get("domain") or "").strip()
        record_id = (self.args.get("record_id") or "").strip()
        value = (self.args.get("value") or "").strip()
        ttl = self.args.get("ttl")

        if not domain or not record_id or not value:
            return Response(
                message="Error: 'domain', 'record_id', and 'value' are required.",
                break_loop=False,
            )

        body: dict = {"value": value}
        if ttl:
            body["ttl"] = int(ttl)

        data = await self._api("put", f"/domains/{domain}/dns/{record_id}", body)
        return Response(message=f"DNS record `{record_id}` updated → {value}", break_loop=False)

    async def _delete_dns(self) -> Response:
        domain = (self.args.get("domain") or "").strip()
        record_id = (self.args.get("record_id") or "").strip()

        if not domain or not record_id:
            return Response(
                message="Error: 'domain' and 'record_id' are required.",
                break_loop=False,
            )

        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{BASE_URL}/domains/{domain}/dns/{record_id}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 204):
                    return Response(message=f"DNS record `{record_id}` deleted.", break_loop=False)
                data = await resp.json()
                return Response(message=f"Delete failed: {data}", break_loop=False)

    async def _ssl_status(self) -> Response:
        domain = (self.args.get("domain") or "").strip()
        if not domain:
            return Response(message="Error: 'domain' is required.", break_loop=False)

        # Check SSL via the API if available, otherwise use socket check
        import ssl
        import socket
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(10)
                s.connect((domain, 443))
                cert = s.getpeercert()

            issuer = dict(x[0] for x in cert.get("issuer", []))
            subject = dict(x[0] for x in cert.get("subject", []))
            not_after = cert.get("notAfter", "unknown")
            not_before = cert.get("notBefore", "unknown")

            lines = [
                f"**SSL Certificate for {domain}**",
                f"- Issuer: {issuer.get('organizationName', 'unknown')}",
                f"- Subject: {subject.get('commonName', 'unknown')}",
                f"- Valid From: {not_before}",
                f"- Expires: {not_after}",
                f"- Status: ✅ Valid",
            ]
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return Response(message=f"SSL check failed for {domain}: {e}", break_loop=False)

    async def _list_hosting(self) -> Response:
        data = await self._api("get", "/hosting")
        if not data:
            return Response(message="No hosting accounts found (or endpoint not available).", break_loop=False)

        if isinstance(data, list):
            lines = [f"**Hosting Accounts ({len(data)}):**\n"]
            for h in data:
                name = h.get("domain", h.get("name", "unknown"))
                plan = h.get("plan", h.get("type", "unknown"))
                status = h.get("status", "unknown")
                lines.append(f"- **{name}** (plan: {plan}, status: {status})")
            return Response(message="\n".join(lines), break_loop=False)
        else:
            import json
            return Response(message=json.dumps(data, indent=2)[:3000], break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://dns {self.agent.agent_name}: Hostinger DNS",
            content="",
            kvps=kvps,
        )
