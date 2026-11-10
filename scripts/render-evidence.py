"""Render the captured real HPA snapshots as a clearly labelled video replay."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument("--input", default="artifacts/recorded-hpa.json")
parser.add_argument("--output", default="artifacts/hpa-evidence.mp4")
args = parser.parse_args()

root = Path("artifacts")
samples = json.loads(Path(args.input).read_text())
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    raise RuntimeError("ffmpeg required")
fontpath = (
    "C:/Windows/Fonts/consola.ttf"
    if os.name == "nt"
    else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
)
font = ImageFont.truetype(fontpath, 16)
segments = []
for i, sample in enumerate(samples):
    text = "MICROSERV STORE | REPLAY OF REAL LOCAL COMMAND OUTPUT\n"
    text += "Context: " + sample.get("context", "kind-microserv-store") + "; captured timestamps below.\n"
    scenario = sample.get("scenario", "login")
    text += (
        sample["utc"]
        + f" | Scenario: {scenario} ({sample.get('load_users', 4)} users) | "
        + sample["load_status"]
        + "\n\n"
    )
    for key in ("HPA", "DEPLOYMENTS", "CPU AND MEMORY"):
        text += key + "\n" + sample[key].strip() + "\n\n"
    frame = Image.new("RGB", (1600, 1200), "#101824")
    draw = ImageDraw.Draw(frame)
    for row, line in enumerate(text.splitlines()[:48]):
        draw.text((24, 20 + row * 23), line, font=font, fill="white")
    textpath = root / f"frame-{i:03}.png"
    frame.save(textpath)
    duration = 3
    if i + 1 < len(samples):
        start = datetime.datetime.strptime(sample["utc"], "UTC %Y-%m-%d %H:%M:%S")
        end = datetime.datetime.strptime(samples[i + 1]["utc"], "UTC %Y-%m-%d %H:%M:%S")
        duration = max(1, (end - start).total_seconds())
    segment = root / f"segment-{i:03}.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            "2",
            "-i",
            str(textpath),
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            str(segment),
        ],
        check=True,
    )
    segments.append(segment)
concat = root / "segments.txt"
concat.write_text("".join(f"file '{p.name}'\n" for p in segments))
subprocess.run(
    [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(Path(args.output)),
    ],
    check=True,
)
print(f"Rendered {args.output} from actual captured snapshots")
