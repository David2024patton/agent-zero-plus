import os
import base64
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class DocumentToMarkdown(Tool):
    """Convert documents (PDF, DOCX, XLSX, HTML, images, CSV, XML) to clean
    Markdown using the Cloudflare Workers AI toMarkdown API.

    Accepts a local file path. Supports: PDF, DOCX, XLSX, XLS, HTML, JPEG,
    PNG, WebP, SVG, XML, CSV, ODS, ODT, and Apple Numbers files.
    Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN environment
    variables to be configured.
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".xlsx", ".xlsm", ".xlsb", ".xls", ".et",
        ".html", ".htm", ".xml", ".csv",
        ".jpeg", ".jpg", ".png", ".webp", ".svg",
        ".ods", ".odt", ".numbers",
    }

    MIME_MAP = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
        ".xlsb": "application/vnd.ms-excel.sheet.binary.macroenabled.12",
        ".xls": "application/vnd.ms-excel",
        ".et": "application/vnd.ms-excel",
        ".html": "text/html",
        ".htm": "text/html",
        ".xml": "application/xml",
        ".csv": "text/csv",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ods": "application/vnd.oasis.opendocument.spreadsheet",
        ".odt": "application/vnd.oasis.opendocument.text",
        ".numbers": "application/vnd.apple.numbers",
    }

    async def execute(self, file_path: str = "", **kwargs) -> Response:
        # Validate credentials
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

        if not account_id or not api_token:
            return Response(
                message=(
                    "Cloudflare credentials not configured. "
                    "Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN "
                    "environment variables to use this tool."
                ),
                break_loop=False,
            )

        # Validate file path
        if not file_path or not file_path.strip():
            return Response(
                message="file_path is required. Provide the path to a document to convert.",
                break_loop=False,
            )

        file_path = file_path.strip()
        if not os.path.isfile(file_path):
            return Response(
                message=f"File not found: {file_path}",
                break_loop=False,
            )

        # Validate extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(self.SUPPORTED_EXTENSIONS))
            return Response(
                message=f"Unsupported file type '{ext}'. Supported: {supported}",
                break_loop=False,
            )

        mime_type = self.MIME_MAP.get(ext, "application/octet-stream")
        file_name = os.path.basename(file_path)

        self.set_progress(f"Converting {file_name} to Markdown...")

        try:
            # Read file and encode as base64
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            file_size_mb = len(file_bytes) / (1024 * 1024)
            if file_size_mb > 50:
                return Response(
                    message=f"File too large ({file_size_mb:.1f} MB). Maximum size is 50 MB.",
                    break_loop=False,
                )

            # Call Cloudflare Workers AI REST API
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/tomarkdown"
            headers = {
                "Authorization": f"Bearer {api_token}",
            }

            # Build multipart form data
            form = aiohttp.FormData()
            form.add_field(
                "file",
                file_bytes,
                filename=file_name,
                content_type=mime_type,
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    result = await resp.json()

            if not result.get("success", False):
                errors = result.get("errors", [])
                error_msg = "; ".join(e.get("message", str(e)) for e in errors) if errors else "Unknown error"
                return Response(
                    message=f"Cloudflare API error: {error_msg}",
                    break_loop=False,
                )

            # Extract result
            data = result.get("result", {})
            markdown_text = data.get("data", "")
            tokens = data.get("tokens", 0)
            detected_mime = data.get("mimetype", mime_type)

            if not markdown_text:
                return Response(
                    message="Conversion returned empty result. The file may be empty or unsupported.",
                    break_loop=False,
                )

            # Build response
            parts = [
                f"**Converted**: {file_name}",
                f"**Format**: {detected_mime}",
                f"**Estimated tokens**: {tokens}",
                "",
                "---",
                "",
                markdown_text,
            ]

            # Truncate if extremely long
            answer = "\n".join(parts)
            max_chars = 20000
            if len(answer) > max_chars:
                answer = answer[:max_chars] + f"\n\n⚠️ Content truncated at {max_chars} characters."

            self.set_progress(f"Converted {file_name} ({tokens} tokens)")

        except aiohttp.ClientError as e:
            PrintStyle().error(f"Cloudflare API request failed: {e}")
            answer = f"Network error calling Cloudflare API: {e}"
        except Exception as e:
            PrintStyle().error(f"Document conversion error: {e}")
            answer = f"Error converting document: {e}"

        self.log.update(content=answer[:500])
        return Response(message=answer, break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        kvps["model"] = "cloudflare/toMarkdown"
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://description {self.agent.agent_name}: Converting document to Markdown",
            content="",
            kvps=kvps,
        )
