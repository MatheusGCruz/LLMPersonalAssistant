from mcp.server.fastmcp import FastMCP
from yt_dlp import YoutubeDL

mcp = FastMCP("youtube-search")


def _format_duration(seconds) -> str:
    if not seconds:
        return "n/a"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


@mcp.tool()
def youtube_search(query: str, max_results: int = 5) -> str:
    """Search YouTube videos and return titles, channels, durations and watch URLs."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }
    count = max(1, min(int(max_results), 20))
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
    except Exception as exc:
        return f"youtube search error: {exc}"
    entries = (info or {}).get("entries") or []
    if not entries:
        return f"no youtube results for {query!r}"
    lines = []
    for index, entry in enumerate(entries, 1):
        video_id = entry.get("id")
        watch_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else "n/a"
        title = str(entry.get("title") or "untitled")
        channel = str(entry.get("channel") or entry.get("uploader") or "n/a")
        duration = _format_duration(entry.get("duration"))
        lines.append(f"{index}. {title}\n   {watch_url}\n   Channel: {channel} | Duration: {duration}")
    return "\n\n".join(lines)


if __name__ == "__main__":
    mcp.run()