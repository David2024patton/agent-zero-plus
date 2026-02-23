### huggingface_tool
Interact with HuggingFace Hub for inference, model info, and search. Requires HUGGINGFACE_TOKEN env var.
Methods: inference, model_info, search_models, search_datasets, whoami.
**Example — run inference:**
~~~json
{
    "tool_name": "huggingface_tool",
    "tool_args": {
        "method": "inference",
        "model": "mistralai/Mistral-7B-Instruct-v0.2",
        "inputs": "Explain machine learning in one paragraph",
        "max_tokens": 200
    }
}
~~~
**Example — search models:**
~~~json
{
    "tool_name": "huggingface_tool",
    "tool_args": {
        "method": "search_models",
        "query": "code generation",
        "limit": 5
    }
}
~~~
**Parameters by method:**
- **inference**: model, inputs (required), task, max_tokens, temperature
- **model_info**: model (required)
- **search_models**: query (required), limit
- **search_datasets**: query (required), limit
- **whoami**: (no args)
