### gemini_tool
Call Google Gemini API for text generation, vision, and embeddings. Requires GEMINI_API_KEY env var.
Methods: generate, vision, embed, list_models, count_tokens.
**Example — generate text:**
~~~json
{
    "tool_name": "gemini_tool",
    "tool_args": {
        "method": "generate",
        "prompt": "Explain quantum computing in 3 sentences",
        "model": "gemini-2.0-flash",
        "temperature": 0.7
    }
}
~~~
**Example — analyze image:**
~~~json
{
    "tool_name": "gemini_tool",
    "tool_args": {
        "method": "vision",
        "prompt": "What's in this image?",
        "image_path": "/path/to/image.jpg"
    }
}
~~~
**Parameters by method:**
- **generate**: prompt (required), model, system_instruction, temperature, max_tokens
- **vision**: prompt, image_path or image_url (one required), model
- **embed**: text (required), model (default text-embedding-004)
- **list_models**: (no args)
- **count_tokens**: text (required), model (optional)
