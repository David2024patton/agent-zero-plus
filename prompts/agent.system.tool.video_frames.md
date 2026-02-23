### video_frames_tool
Extract frames, thumbnails, and info from videos, or convert to GIF. Requires ffmpeg installed.
Methods: extract, thumbnail, info, gif, resize.
**Example — extract frames at 1fps:**
~~~json
{
    "tool_name": "video_frames_tool",
    "tool_args": {
        "method": "extract",
        "video_path": "/path/to/video.mp4",
        "output_dir": "/tmp/frames",
        "fps": "1"
    }
}
~~~
**Example — get video info:**
~~~json
{
    "tool_name": "video_frames_tool",
    "tool_args": {
        "method": "info",
        "video_path": "/path/to/video.mp4"
    }
}
~~~
**Parameters by method:**
- **extract**: video_path, output_dir, fps, format (jpg/png), start_time, duration, max_frames
- **thumbnail**: video_path, output_path, timestamp (default "00:00:01")
- **info**: video_path (shows duration, resolution, codecs, size)
- **gif**: video_path, output_path, fps, width, start_time, duration
- **resize**: video_path (required), width, height (at least one required), output_path
