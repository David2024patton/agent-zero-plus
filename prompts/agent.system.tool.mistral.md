### mistral_tool
Call Mistral AI API for chat, code generation, and embeddings. Requires MISTRAL_API_KEY env var.
Methods: chat, codestral, embed, list_models.
**Example — chat:**
~~~json
{
    "tool_name": "mistral_tool",
    "tool_args": {
        "method": "chat",
        "prompt": "Write a Python function to reverse a string",
        "model": "mistral-large-latest"
    }
}
~~~
**Example — code completion (Codestral):**
~~~json
{
    "tool_name": "mistral_tool",
    "tool_args": {
        "method": "codestral",
        "prompt": "def fibonacci(n):",
        "suffix": "return result"
    }
}
~~~
**Parameters by method:**
- **chat**: prompt (required), model, system, temperature, max_tokens
- **codestral**: prompt (required), suffix, model, temperature, max_tokens
- **embed**: text (required), model (default mistral-embed)
- **list_models**: (no args)
