### video_transcript_tool
Download transcripts, subtitles, and audio from videos. Requires yt-dlp and youtube-transcript-api.
Methods: transcript, subtitles, info, download_audio, search_transcript.
**Example — get transcript:**
~~~json
{
    "tool_name": "video_transcript_tool",
    "tool_args": {
        "method": "transcript",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "language": "en",
        "timestamps": "true"
    }
}
~~~
**Example — video info:**
~~~json
{
    "tool_name": "video_transcript_tool",
    "tool_args": {
        "method": "info",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }
}
~~~
**Parameters by method:**
- **transcript**: url (required), language (default "en"), timestamps (true/false), save_path
- **subtitles**: url, language, output_dir, format (srt/vtt/txt)
- **info**: url (required) — shows title, channel, duration, views, subtitle languages
- **download_audio**: url, output_dir, format (mp3/m4a/wav/opus)
- **search_transcript**: url (required), query (required) — finds matching lines with timestamps
