#!/usr/bin/env python3
"""
Download your music for Jarvis.

Usage:
    python download_music.py <youtube_url>

Example:
    python download_music.py "https://www.youtube.com/watch?v=BN1WwnEDWAM"

Requires: pip install yt-dlp
Requires: ffmpeg installed (winget install Gyan.FFmpeg)
"""

import sys
import os

def main():
    import yt_dlp

    if len(sys.argv) < 2:
        print("Usage: python download_music.py <youtube_url>")
        print('Example: python download_music.py "https://www.youtube.com/watch?v=BN1WwnEDWAM"')
        sys.exit(1)

    url = sys.argv[1]
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "music.%(ext)s")

    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
    }

    print(f"Downloading audio from: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    print(f"\nDone! music.mp3 saved to {output_dir}")


if __name__ == "__main__":
    main()
