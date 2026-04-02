#!/usr/bin/env python3
"""
Fetch transcript and title from a YouTube video.
Outputs JSON with video_title and transcript_text.
"""

import sys
import json
import re
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def fetch_title(video_id: str) -> str:
    """Fetch video title via oEmbed (no API key needed)."""
    import urllib.request
    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        with urllib.request.urlopen(oembed_url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("title", f"YouTube Video ({video_id})")
    except Exception:
        return f"YouTube Video ({video_id})"


def format_timestamp(seconds: float) -> str:
    """Convert seconds to [MM:SS] format."""
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"[{h}:{m:02d}:{s:02d}]"
    return f"[{m}:{s:02d}]"


def fetch_transcript(video_id: str) -> list:
    """Try to get transcript, preferring English."""
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        return [{"start": snippet.start, "text": snippet.text} for snippet in transcript]
    except TranscriptsDisabled:
        print("ERROR: TranscriptsDisabled — captions are turned off for this video.", file=sys.stderr)
        sys.exit(1)
    except NoTranscriptFound:
        print("ERROR: NoTranscriptFound — no captions available for this video.", file=sys.stderr)
        sys.exit(1)


def build_transcript_text(entries: list) -> str:
    """Merge transcript entries into readable text with timestamps every ~2 minutes."""
    lines = []
    last_stamped = -120  # force first timestamp

    for entry in entries:
        start = entry.get("start", 0)
        text = entry.get("text", "").strip().replace("\n", " ")
        if not text:
            continue
        if start - last_stamped >= 120:
            lines.append(f"\n{format_timestamp(start)} {text}")
            last_stamped = start
        else:
            lines.append(text)

    return " ".join(lines).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_transcript.py <youtube_url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    video_id = extract_video_id(url)
    title = fetch_title(video_id)
    entries = fetch_transcript(video_id)
    transcript_text = build_transcript_text(entries)

    result = {
        "video_id": video_id,
        "video_title": title,
        "transcript_text": transcript_text,
        "entry_count": len(entries),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
