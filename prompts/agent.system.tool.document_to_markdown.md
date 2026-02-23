### document_to_markdown
Convert documents (PDF, DOCX, XLSX, PPTX, images) to Markdown format using Cloudflare Workers AI.
Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN env vars.
**Example usage:**
~~~json
{
    "tool_name": "document_to_markdown",
    "tool_args": {
        "file_path": "/path/to/document.pdf"
    }
}
~~~
**Parameters:**
- **file_path** (required): Path to the document to convert
- Supported formats: PDF, DOCX, XLSX, PPTX, JPG, PNG, GIF, WEBP
