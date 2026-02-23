"""
Agent Zero Tool: video_frames_tool
======================================
Extract frames from videos using ffmpeg subprocess.
Requires ffmpeg installed.
"""

import os
import asyncio
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class VideoFramesTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "extract").strip().lower()
        video_path = (self.args.get("video_path") or "").strip()

        if not video_path:
            return Response(message="Error: 'video_path' is required.", break_loop=False)

        if not os.path.exists(video_path):
            return Response(message=f"Error: Video not found: {video_path}", break_loop=False)

        methods = {
            "extract": self._extract_frames,
            "thumbnail": self._thumbnail,
            "info": self._info,
            "gif": self._to_gif,
            "resize": self._resize,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method](video_path)
        except Exception as e:
            PrintStyle().error(f"Video frames error: {e}")
            return Response(message=f"Video frames error: {e}", break_loop=False)

    async def _run_cmd(self, *args: str) -> tuple[str, str, int]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
            proc.returncode or 0,
        )

    async def _extract_frames(self, video_path: str) -> Response:
        output_dir = (self.args.get("output_dir") or "").strip()
        fps = (self.args.get("fps") or "1").strip()
        format_type = (self.args.get("format") or "jpg").strip()
        start_time = (self.args.get("start_time") or "").strip()
        duration = (self.args.get("duration") or "").strip()
        max_frames = int(self.args.get("max_frames", 0))

        if not output_dir:
            output_dir = os.path.join(os.path.dirname(video_path), "frames")

        os.makedirs(output_dir, exist_ok=True)

        cmd = ["ffmpeg", "-i", video_path]
        if start_time:
            cmd.extend(["-ss", start_time])
        if duration:
            cmd.extend(["-t", duration])
        cmd.extend(["-vf", f"fps={fps}"])
        if max_frames:
            cmd.extend(["-frames:v", str(max_frames)])
        cmd.extend(["-q:v", "2", os.path.join(output_dir, f"frame_%04d.{format_type}")])

        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"ffmpeg error: {err[:500]}", break_loop=False)

        # Count extracted frames
        frames = [f for f in os.listdir(output_dir) if f.startswith("frame_")]
        return Response(
            message=f"Extracted **{len(frames)} frames** to `{output_dir}` at {fps} fps.",
            break_loop=False,
        )

    async def _thumbnail(self, video_path: str) -> Response:
        output_path = (self.args.get("output_path") or "").strip()
        timestamp = (self.args.get("timestamp") or "00:00:01").strip()

        if not output_path:
            base = os.path.splitext(video_path)[0]
            output_path = f"{base}_thumb.jpg"

        cmd = ["ffmpeg", "-i", video_path, "-ss", timestamp, "-frames:v", "1", "-q:v", "2", "-y", output_path]
        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"ffmpeg error: {err[:500]}", break_loop=False)

        return Response(message=f"Thumbnail saved to `{output_path}`", break_loop=False)

    async def _info(self, video_path: str) -> Response:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path,
        ]
        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"ffprobe error: {err[:500]}", break_loop=False)

        import json
        try:
            data = json.loads(out)
        except Exception:
            return Response(message=out[:3000], break_loop=False)

        fmt = data.get("format", {})
        streams = data.get("streams", [])

        lines = [
            f"**Video Info: {os.path.basename(video_path)}**",
            f"- Duration: {fmt.get('duration', 'N/A')}s",
            f"- Size: {int(fmt.get('size', 0)) / 1024 / 1024:.1f}MB",
            f"- Format: {fmt.get('format_long_name', 'N/A')}",
        ]

        for s in streams:
            if s.get("codec_type") == "video":
                lines.append(f"- Video: {s.get('codec_name', '?')} {s.get('width', '?')}x{s.get('height', '?')} @ {s.get('r_frame_rate', '?')} fps")
            elif s.get("codec_type") == "audio":
                lines.append(f"- Audio: {s.get('codec_name', '?')} {s.get('sample_rate', '?')}Hz {s.get('channels', '?')}ch")

        return Response(message="\n".join(lines), break_loop=False)

    async def _to_gif(self, video_path: str) -> Response:
        output_path = (self.args.get("output_path") or "").strip()
        fps = (self.args.get("fps") or "10").strip()
        width = (self.args.get("width") or "320").strip()
        start_time = (self.args.get("start_time") or "").strip()
        duration = (self.args.get("duration") or "5").strip()

        if not output_path:
            base = os.path.splitext(video_path)[0]
            output_path = f"{base}.gif"

        cmd = ["ffmpeg", "-i", video_path]
        if start_time:
            cmd.extend(["-ss", start_time])
        cmd.extend(["-t", duration, "-vf", f"fps={fps},scale={width}:-1:flags=lanczos", "-y", output_path])

        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"ffmpeg error: {err[:500]}", break_loop=False)

        size_mb = os.path.getsize(output_path) / 1024 / 1024
        return Response(message=f"GIF saved to `{output_path}` ({size_mb:.1f}MB)", break_loop=False)

    async def _resize(self) -> Response:
        video_path = (self.args.get("video_path") or "").strip()
        width = (self.args.get("width") or "").strip()
        height = (self.args.get("height") or "").strip()
        output_path = (self.args.get("output_path") or "").strip()

        if not video_path:
            return Response(message="Error: 'video_path' is required.", break_loop=False)
        if not os.path.exists(video_path):
            return Response(message=f"Error: File not found: {video_path}", break_loop=False)
        if not width and not height:
            return Response(message="Error: at least one of 'width' or 'height' is required.", break_loop=False)

        if not output_path:
            name, ext = os.path.splitext(video_path)
            output_path = f"{name}_resized{ext}"

        # Build scale filter — use -1 to maintain aspect ratio
        w = width if width else "-1"
        h = height if height else "-1"
        scale_filter = f"scale={w}:{h}"

        out, err, rc = await self._run_cmd(
            "ffmpeg", "-y", "-i", video_path,
            "-vf", scale_filter,
            output_path,
        )

        if rc != 0:
            return Response(message=f"Resize failed: {err}", break_loop=False)

        return Response(message=f"Resized video saved to `{output_path}` (scale: {scale_filter})", break_loop=False)
    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://movie {self.agent.agent_name}: Video Frames",
            content="",
            kvps=kvps,
        )
