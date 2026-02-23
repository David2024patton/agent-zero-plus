### summarize_tool
Summarize URLs, files, YouTube videos, or raw text using available LLM APIs.
Requires OPENAI_API_KEY or GEMINI_API_KEY env var.
Supports multiple summary styles: concise, detailed, bullets, eli5, technical, academic.
**Example — summarize URL:**
~~~json
{
    "tool_name": "summarize_tool",
    "tool_args": {
        "source": "https://example.com/article",
        "style": "bullets",
        "max_length": 300
    }
}
~~~
**Example — summarize YouTube video:**
~~~json
{
    "tool_name": "summarize_tool",
    "tool_args": {
        "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "style": "concise"
    }
}
~~~
**Parameters:**
- **source** (required): URL, file path, or raw text to summarize
- **style**: "concise" (default), "detailed", "bullets", "eli5", "technical", "academic"
- **max_length**: Maximum word count for summary (default 500)
