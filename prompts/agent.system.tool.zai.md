### zai_tool
Call Zhipu AI (Z.AI) API for chat completions and embeddings. Requires Z_AI_API_KEY env var.
Methods: chat, embed, list_models.
**Example — chat:**
~~~json
{
    "tool_name": "zai_tool",
    "tool_args": {
        "method": "chat",
        "prompt": "Write a haiku about programming",
        "model": "glm-4-plus"
    }
}
~~~
**Parameters by method:**
- **chat**: prompt (required), model (default glm-4-plus), system, temperature, max_tokens
- **embed**: text (required), model (default embedding-3)
- **list_models**: (no args)
