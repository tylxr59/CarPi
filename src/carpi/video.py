"""Local generated test pattern. No CarPlay transport is implied."""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from pathlib import Path

# Public-domain-style hand-defined 5x7 glyphs, independently authored for this demo.
FONT = {
    " ": [0, 0, 0, 0, 0, 0, 0],
    ":": [0, 4, 4, 0, 4, 4, 0],
    "-": [0, 0, 0, 31, 0, 0, 0],
    "/": [1, 2, 4, 8, 16, 0, 0],
    "@": [14, 17, 23, 21, 23, 16, 14],
    "0": [14, 17, 19, 21, 25, 17, 14],
    "1": [4, 12, 4, 4, 4, 4, 14],
    "2": [14, 17, 1, 2, 4, 8, 31],
    "3": [30, 1, 1, 14, 1, 1, 30],
    "4": [2, 6, 10, 18, 31, 2, 2],
    "5": [31, 16, 16, 30, 1, 1, 30],
    "6": [14, 16, 16, 30, 17, 17, 14],
    "7": [31, 1, 2, 4, 8, 8, 8],
    "8": [14, 17, 17, 14, 17, 17, 14],
    "9": [14, 17, 17, 15, 1, 1, 14],
    "A": [14, 17, 17, 31, 17, 17, 17],
    "B": [30, 17, 17, 30, 17, 17, 30],
    "C": [14, 17, 16, 16, 16, 17, 14],
    "D": [30, 17, 17, 17, 17, 17, 30],
    "E": [31, 16, 16, 30, 16, 16, 31],
    "F": [31, 16, 16, 30, 16, 16, 16],
    "G": [14, 17, 16, 23, 17, 17, 14],
    "H": [17, 17, 17, 31, 17, 17, 17],
    "I": [14, 4, 4, 4, 4, 4, 14],
    "L": [16, 16, 16, 16, 16, 16, 31],
    "M": [17, 27, 21, 21, 17, 17, 17],
    "N": [17, 25, 21, 19, 17, 17, 17],
    "O": [14, 17, 17, 17, 17, 17, 14],
    "P": [30, 17, 17, 30, 16, 16, 16],
    "R": [30, 17, 17, 30, 20, 18, 17],
    "S": [15, 16, 16, 14, 1, 1, 30],
    "T": [31, 4, 4, 4, 4, 4, 4],
    "U": [17, 17, 17, 17, 17, 17, 14],
    "W": [17, 17, 17, 21, 21, 21, 10],
    "X": [17, 17, 10, 4, 10, 17, 17],
    "a": [0, 0, 14, 1, 15, 17, 15],
    "c": [0, 0, 14, 16, 16, 16, 14],
    "d": [1, 1, 15, 17, 17, 17, 15],
    "e": [0, 0, 14, 17, 31, 16, 14],
    "i": [4, 0, 12, 4, 4, 4, 14],
    "l": [12, 4, 4, 4, 4, 4, 14],
    "o": [0, 0, 14, 17, 17, 17, 14],
    "p": [0, 0, 30, 17, 30, 16, 16],
    "r": [0, 0, 22, 25, 16, 16, 16],
    "t": [4, 4, 31, 4, 4, 5, 2],
    "u": [0, 0, 17, 17, 17, 19, 13],
}


def frame(
    width: int, height: int, count: int, now: dt.datetime | None = None, fps: int = 30
) -> bytes:
    if not 160 <= width <= 1920 or not 120 <= height <= 1080:
        raise ValueError("demo dimensions must be 160..1920 by 120..1080")
    now = now or dt.datetime.now(dt.UTC)
    data = bytearray(bytes((12, 28, 48)) * (width * height))
    detail_line = f"LOCAL {width} X {height} @ {fps}"
    scale = max(1, min(width // (6 * len(detail_line) + 16), height // 55, 5))

    def write(line: str, y: int, color: bytes) -> None:
        x = max(8, (width - len(line) * 6 * scale) // 2)
        for letter in line:
            glyph = FONT.get(letter, FONT[" "])
            for row, bits in enumerate(glyph):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        for dy in range(scale):
                            yy = y + row * scale + dy
                            if yy >= height:
                                continue
                            for dx in range(scale):
                                xx = x + col * scale + dx
                                if 0 <= xx < width:
                                    offset = (yy * width + xx) * 3
                                    data[offset : offset + 3] = color
            x += 6 * scale

    write("Hello World", height // 5, bytes((255, 255, 255)))
    write("carpi", height // 5 + 10 * scale, bytes((66, 220, 220)))
    write(detail_line, height // 5 + 20 * scale, bytes((255, 220, 100)))
    write(f"FRAME {count}", height // 5 + 29 * scale, bytes((255, 220, 100)))
    write(now.strftime("%H:%M:%S UTC"), height // 5 + 38 * scale, bytes((255, 220, 100)))
    return bytes(data)


def write_ppm(path: Path, width: int, height: int) -> None:
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode() + frame(width, height, 0))


def encode_demo(path: Path, width: int, height: int, fps: int, seconds: int, encoder: str) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required")
    if encoder not in {"libx264", "h264_v4l2m2m"}:
        raise ValueError("unsupported encoder")
    if not 1 <= fps <= 60 or not 1 <= seconds <= 30:
        raise ValueError("demo FPS/seconds out of range")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        encoder,
    ]
    if encoder == "libx264":
        command += ["-preset", "ultrafast", "-tune", "zerolatency"]
    command += ["-g", str(fps), "-f", "h264", str(path)]
    start_time = dt.datetime.now(dt.UTC)
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        assert process.stdin is not None
        try:
            for count in range(fps * seconds):
                presentation_time = start_time + dt.timedelta(seconds=count / fps)
                process.stdin.write(frame(width, height, count, presentation_time, fps))
        except BrokenPipeError as error:
            raise RuntimeError(
                "FFmpeg encoder exited early; check device/encoder availability"
            ) from error
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError(f"FFmpeg encoder failed with status {process.returncode}")
    # No pacing is needed: this writes a finite test stream, not a live transport.
