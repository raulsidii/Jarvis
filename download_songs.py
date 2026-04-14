#!/usr/bin/env python3
"""Download all AC/DC songs for Jarvis and trim as needed."""

import os
import subprocess
import sys

FFMPEG_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1-full_build\bin"
)

SONGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")

# (search query, output filename, start_seconds or None)
SONGS = [
    ("AC/DC Back in Black official audio", "back_in_black.mp3", 4),
    ("AC/DC Thunderstruck official audio", "thunderstruck.mp3", None),
    ("AC/DC Shoot to Thrill official audio", "shoot_to_thrill.mp3", None),
    ("AC/DC TNT official audio", "tnt.mp3", None),
    ("AC/DC Highway to Hell official audio", "highway_to_hell.mp3", None),
    ("AC/DC The Razors Edge official audio", "razors_edge.mp3", 30),
]


def download_song(query, filename, start_sec):
    import yt_dlp

    output_path = os.path.join(SONGS_DIR, filename)
    temp_path = os.path.join(SONGS_DIR, f"temp_{filename}")

    if os.path.exists(output_path):
        print(f"  [SKIP] {filename} already exists")
        return

    print(f"  [DOWNLOADING] {query} -> {filename}")

    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": temp_path.replace(".mp3", ".%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "ffmpeg_location": FFMPEG_PATH,
        "default_search": "ytsearch",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch1:{query}"])

    temp_mp3 = temp_path.replace(".mp3", ".mp3")

    # Trim if needed
    if start_sec and os.path.exists(temp_mp3):
        print(f"  [TRIMMING] {filename} starting at {start_sec}s")
        ffmpeg_exe = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", temp_mp3, "-ss", str(start_sec),
             "-acodec", "copy", output_path],
            capture_output=True,
        )
        os.remove(temp_mp3)
    elif os.path.exists(temp_mp3):
        os.rename(temp_mp3, output_path)

    if os.path.exists(output_path):
        print(f"  [DONE] {filename}")
    else:
        print(f"  [FAILED] {filename}")


def main():
    os.makedirs(SONGS_DIR, exist_ok=True)
    print(f"Downloading {len(SONGS)} songs to {SONGS_DIR}\n")
    for query, filename, start_sec in SONGS:
        try:
            download_song(query, filename, start_sec)
        except Exception as e:
            print(f"  [ERROR] {filename}: {e}")
    print("\nAll done!")


if __name__ == "__main__":
    main()
