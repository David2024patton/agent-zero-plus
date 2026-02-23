### image_gen_tool
Generate, edit, or create variations of images using OpenAI's DALL-E API. Requires OPENAI_API_KEY env var.
Methods: generate (default), edit, variation.
**Example — generate image:**
~~~json
{
    "tool_name": "image_gen_tool",
    "tool_args": {
        "prompt": "A futuristic city at sunset, cyberpunk style",
        "model": "dall-e-3",
        "size": "1024x1024",
        "quality": "hd",
        "style": "vivid"
    }
}
~~~
**Example — edit image (DALL-E 2):**
~~~json
{
    "tool_name": "image_gen_tool",
    "tool_args": {
        "method": "edit",
        "image_path": "/path/to/image.png",
        "prompt": "Add a rainbow in the sky",
        "mask_path": "/path/to/mask.png"
    }
}
~~~
**Example — create variation:**
~~~json
{
    "tool_name": "image_gen_tool",
    "tool_args": {
        "method": "variation",
        "image_path": "/path/to/image.png",
        "save_path": "/tmp/variation.png"
    }
}
~~~
**Parameters:**
- **method**: "generate" (default), "edit", or "variation"
- **prompt** (required for generate/edit): Description of image to generate or edit
- **model**: "dall-e-3" (default) or "dall-e-2"
- **size**: "1024x1024" (default), "1792x1024", "1024x1792"
- **quality**: "standard" (default) or "hd" (DALL-E 3 only)
- **style**: "vivid" (default) or "natural" (DALL-E 3 only)
- **count**: Number of images (DALL-E 2 only, 1-10)
- **save_path**: If set, saves image locally instead of returning URL
- **image_path** (edit/variation): Path to source image (required for edit/variation)
- **mask_path** (edit, optional): Path to mask image for inpainting
