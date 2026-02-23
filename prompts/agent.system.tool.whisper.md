### whisper_tool
Transcribe or translate audio using OpenAI Whisper API. Requires OPENAI_API_KEY env var.
Supports mp3, mp4, mpeg, mpga, m4a, wav, webm files (max 25MB).
**Example — transcribe audio:**
~~~json
{
    "tool_name": "whisper_tool",
    "tool_args": {
        "file_path": "/path/to/audio.mp3",
        "format": "text"
    }
}
~~~
**Example — translate to English:**
~~~json
{
    "tool_name": "whisper_tool",
    "tool_args": {
        "method": "translate",
        "file_path": "/path/to/spanish_audio.mp3",
        "save_path": "/tmp/translation.txt"
    }
}
~~~
**Parameters:**
- **file_path** (required): Path to audio file
- **method**: "transcribe" (default) or "translate" (to English)
- **model**: "whisper-1" (default)
- **language**: ISO-639-1 code (e.g. "en", "es", "fr")
- **format**: "text" (default), "json", "srt", "vtt", "verbose_json"
- **prompt**: Hint text to guide transcription style
- **save_path**: Optional — save transcription to file
