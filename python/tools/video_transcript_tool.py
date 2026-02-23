"""
Agent Zero Tool: video_transcript_tool
==========================================
Download video transcripts and subtitles using yt-dlp and youtube-transcript-api.
Requires yt-dlp installed (pip install yt-dlp youtube-transcript-api).
"""

import os
import asyncio
import json
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class VideoTranscriptTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "transcript").strip().lower()
        url = (self.args.get("url") or "").strip()

        if not url:
            return Response(message="Error: 'url' is required.", break_loop=False)

        methods = {
            "transcript": self._get_transcript,
            "subtitles": self._download_subtitles,
            "info": self._video_info,
            "download_audio": self._download_audio,
            "search_transcript": self._search_transcript,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method](url)
        except Exception as e:
            PrintStyle().error(f"Video transcript error: {e}")
            return Response(message=f"Video transcript error: {e}", break_loop=False)

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

    def _extract_video_id(self, url: str) -> str:
        """Extracts video ID from a YouTube URL."""
        if "v=" in url:
            return url.split("v=")[-1].split("&")[0]
        elif "youtu.be/" in url:
            return url.split("youtu.be/")[-1].split("?")[0]
        else:
            # Assume the URL itself is the video ID or a direct link to the video
            return url.split("/")[-1].split("?")[0]

    async def _get_transcript(self, url: str) -> Response:
        language = (self.args.get("language") or "en").strip()
        timestamps = str(self.args.get("timestamps", "false")).lower() == "true"
        save_path = (self.args.get("save_path") or "").strip()

        # Try youtube-transcript-api first (faster, no download needed)
        script = f"""
import json
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    # Extract video ID from URL
    url = "{url}"
    vid = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]
    transcript = YouTubeTranscriptApi.get_transcript(vid, languages=["{language}", "en"])
    for entry in transcript:
        ts = f"[{{int(entry['start'])//60}}:{{int(entry['start'])%60:02d}}] " if {timestamps} else ""
        print(f"{{ts}}{{entry['text']}}")
except Exception as e:
    print(f"FALLBACK_NEEDED:{{e}}")
"""
        out, err, rc = await self._run_cmd("python", "-c", script)

        if "FALLBACK_NEEDED" in out or rc != 0:
            # Fallback to yt-dlp
            cmd = ["yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", language,
                   "--sub-format", "txt", "--print", "%(subtitles)j", url]
            out, err, rc = await self._run_cmd(*cmd)
            if rc != 0:
                return Response(message=f"Could not get transcript: {err[:500]}", break_loop=False)

        if save_path:
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(out)
            return Response(
                message=f"Transcript saved to `{save_path}` ({len(out)} chars)\n\n{out[:2000]}",
                break_loop=False,
            )

        return Response(message=out[:5000], break_loop=False)

    async def _download_subtitles(self, url: str) -> Response:
        language = (self.args.get("language") or "en").strip()
        output_dir = (self.args.get("output_dir") or "/tmp").strip()
        fmt = (self.args.get("format") or "srt").strip()

        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            "yt-dlp", "--skip-download",
            "--write-sub", "--write-auto-sub",
            "--sub-lang", language,
            "--sub-format", fmt,
            "-o", os.path.join(output_dir, "%(title)s.%(ext)s"),
            url,
        ]
        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"yt-dlp error: {err[:500]}", break_loop=False)

        return Response(message=f"Subtitles downloaded to `{output_dir}`\n{out}", break_loop=False)

    async def _video_info(self, url: str) -> Response:
        cmd = ["yt-dlp", "--dump-json", "--skip-download", url]
        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"yt-dlp error: {err[:500]}", break_loop=False)

        try:
            data = json.loads(out)
        except Exception:
            return Response(message=out[:3000], break_loop=False)

        duration_m = int(data.get("duration", 0)) // 60
        duration_s = int(data.get("duration", 0)) % 60

        lines = [
            f"**{data.get('title', 'Unknown')}**",
            f"- Channel: {data.get('channel', 'N/A')}",
            f"- Duration: {duration_m}:{duration_s:02d}",
            f"- Views: {data.get('view_count', 'N/A'):,}" if isinstance(data.get('view_count'), int) else f"- Views: {data.get('view_count', 'N/A')}",
            f"- Upload: {data.get('upload_date', 'N/A')}",
            f"- Description: {data.get('description', 'N/A')[:300]}",
        ]

        subs = data.get("subtitles", {})
        auto_subs = data.get("automatic_captions", {})
        if subs:
            lines.append(f"- Subtitles: {', '.join(list(subs.keys())[:10])}")
        if auto_subs:
            lines.append(f"- Auto captions: {', '.join(list(auto_subs.keys())[:10])}")

        return Response(message="\n".join(lines), break_loop=False)

    async def _download_audio(self, url: str) -> Response:
        output_dir = (self.args.get("output_dir") or "/tmp").strip()
        fmt = (self.args.get("format") or "mp3").strip()

        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            "yt-dlp", "-x", "--audio-format", fmt,
            "-o", os.path.join(output_dir, "%(title)s.%(ext)s"),
            url,
        ]
        out, err, rc = await self._run_cmd(*cmd)
        if rc != 0:
            return Response(message=f"yt-dlp error: {err[:500]}", break_loop=False)

        return Response(message=f"Audio downloaded to `{output_dir}`\n{out}", break_loop=False)

    async def _search_transcript(self, url: str) -> Response:
        query = (self.args.get("query") or "").strip()

        if not url or not query:
            return Response(message="Error: 'url' and 'query' are required.", break_loop=False)

        video_id = self._extract_video_id(url)

        # Run in subprocess for API version isolation
        script = f"""
import json
query = {json.dumps(query)}.lower()
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        transcript = YouTubeTranscriptApi.get_transcript("{video_id}")
    except AttributeError:
        ytt = YouTubeTranscriptApi()
        t_obj = ytt.fetch("{video_id}")
        transcript = [{{"text": s.text, "start": s.start}} for s in t_obj]
    matches = []
    for e in transcript:
        if query in e.get("text", "").lower():
            s = e.get("start", 0)
            matches.append(f"[{{int(s//60)}}:{{int(s%60):02d}}] {{e['text']}}")
    if matches:
        print(f"FOUND:{{len(matches)}}")
        for m in matches[:30]:
            print(m)
    else:
        print("NONE")
except Exception as ex:
    print(f"ERROR:{{ex}}")
"""
        out, err, rc = await self._run_cmd("python", "-c", script)

        if out.startswith("ERROR:"):
            return Response(message=f"Transcript error: {out[6:]}", break_loop=False)

        if out.startswith("NONE"):
            return Response(message=f"No matches for '{query}' in transcript.", break_loop=False)

        lines = out.strip().split("\n")
        header_line = lines[0] if lines else ""
        count = header_line.replace("FOUND:", "") if "FOUND:" in header_line else "?"
        result_lines = lines[1:] if len(lines) > 1 else []

        header = f"**Found {count} match(es) for '{query}':**\n"
        return Response(message=header + "\n".join(f"- {l}" for l in result_lines), break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://subtitles {self.agent.agent_name}: Video Transcript",
            content="",
            kvps=kvps,
        )
