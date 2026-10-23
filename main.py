
import os
import json
import re
import time
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# --------------------------------------------------
# Configuration
# --------------------------------------------------

ROOT = Path(".")
OUT = ROOT / "output"
ASSETS = OUT / "assets"

OUT.mkdir(exist_ok=True)
ASSETS.mkdir(exist_ok=True)

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
UPLOAD = os.environ.get("YOUTUBE_UPLOAD", "false").lower() == "true"


# --------------------------------------------------
# Gemini: generate script with retry handling
# --------------------------------------------------

def call_gemini():
    if not API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY GitHub secret.")

    prompt = """
Create one original YouTube Short for this channel.

Niche: fresher careers, office life, discipline, failures,
and personal growth.

Audience: Indian students and early-career professionals.
Language: natural spoken English, simple and specific.
Length: about 40-55 seconds.
Do not invent statistics or fake personal stories.
Choose one useful, relatable idea.
Start with a strong hook and give actionable advice.

Return ONLY valid JSON with this schema:
{
  "topic": "short topic",
  "title": "curiosity-driven accurate title",
  "description": "2-3 sentence description with relevant hashtags",
  "scenes": [
    {
      "voice": "natural spoken narration",
      "screen": "short on-screen text, maximum 9 words"
    }
  ],
  "hashtags": ["#Shorts", "#Career"]
}

Use 4 to 6 scenes.
Each voice segment should sound natural when read aloud.
No markdown fences.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.8,
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "x-goog-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    response = None

    for attempt in range(5):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90
            )

            if response.ok:
                break

            retryable = response.status_code in (
                408, 429, 500, 502, 503, 504
            )

            if not retryable:
                raise RuntimeError(
                    f"Gemini API error {response.status_code}: "
                    f"{response.text[:1500]}"
                )

            if attempt == 4:
                raise RuntimeError(
                    f"Gemini failed after 5 attempts: "
                    f"{response.status_code}: {response.text[:1500]}"
                )

            delay = min(2 ** (attempt + 1), 30)
            print(
                f"Gemini returned HTTP {response.status_code}. "
                f"Retrying in {delay} seconds..."
            )
            time.sleep(delay)

        except requests.exceptions.RequestException as exc:
            if attempt == 4:
                raise RuntimeError(
                    f"Gemini network request failed after 5 attempts: {exc}"
                ) from exc

            delay = min(2 ** (attempt + 1), 30)
            print(f"Network error. Retrying in {delay} seconds...")
            time.sleep(delay)

    if response is None or not response.ok:
        raise RuntimeError("Gemini did not return a successful response.")

    data = response.json()

    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "Gemini returned no usable script. Response: "
            + json.dumps(data)[:1500]
        ) from exc

    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Gemini returned invalid JSON: {raw[:1000]}"
        ) from exc

    if not isinstance(content, dict):
        raise RuntimeError("Gemini response must be a JSON object.")

    scenes = content.get("scenes")

    if not isinstance(scenes, list) or len(scenes) < 4:
        raise RuntimeError(
            "Gemini must return at least 4 scenes. Please retry."
        )

    content["scenes"] = scenes[:6]

    for scene in content["scenes"]:
        if not isinstance(scene, dict) or not scene.get("voice"):
            raise RuntimeError("A scene is missing its voice narration.")

        scene["voice"] = str(scene["voice"]).strip()
        scene["screen"] = str(
            scene.get("screen") or scene["voice"]
        ).strip()

    content["topic"] = str(content.get("topic", "Career growth"))
    content["title"] = str(
        content.get("title", content["topic"])
    )[:100]
    content["description"] = str(
        content.get("description", "")
    )
    content["hashtags"] = content.get(
        "hashtags", ["#Shorts", "#Career"]
    )
    content["created_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    return content


# --------------------------------------------------
# Fonts and text layout
# --------------------------------------------------

def font(size, bold=False):
    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
            if bold else
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        (
            "C:/Windows/Fonts/arialbd.ttf"
            if bold else
            "C:/Windows/Fonts/arial.ttf"
        )
    ]

    for filename in candidates:
        if Path(filename).exists():
            return ImageFont.truetype(filename, size)

    return ImageFont.load_default()


def wrap_text(draw, text, fnt, max_width):
    words = str(text).split()
    lines = []
    current = ""

    for word in words:
        candidate = (current + " " + word).strip()

        if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


# --------------------------------------------------
# Create a vertical text card for each scene
# --------------------------------------------------

def make_card(text, idx, total, path):
    width, height = 1080, 1920

    image = Image.new("RGB", (width, height), (13, 22, 42))
    draw = ImageDraw.Draw(image)

    for y in range(height):
        t = y / height
        color = (
            int(12 + 18 * t),
            int(25 + 12 * t),
            int(48 + 28 * t)
        )
        draw.line((0, y, width, y), fill=color)

    draw.ellipse((700, -160, 1260, 400), fill=(27, 62, 96))
    draw.ellipse((-220, 1450, 380, 2050), fill=(24, 53, 83))

    draw.rounded_rectangle(
        (72, 140, 1008, 1780),
        radius=42,
        outline=(86, 151, 200),
        width=4
    )

    draw.text(
        (105, 205),
        "ONE THING TO REMEMBER",
        font=font(30, True),
        fill=(127, 210, 255)
    )

    draw.text(
        (105, 1630),
        f"{idx:02d} / {total:02d}  |  CAREER GROWTH",
        font=font(27, True),
        fill=(170, 190, 215)
    )

    lines = wrap_text(draw, text, font(68, True), 820)
    line_height = 92
    block_height = len(lines) * line_height
    y = (height - block_height) // 2

    for line in lines:
        draw.text(
            (width // 2, y),
            line,
            font=font(68, True),
            fill=(255, 255, 255),
            anchor="mt"
        )
        y += line_height

    image.save(path, quality=92)


# --------------------------------------------------
# Run FFmpeg safely
# --------------------------------------------------

def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(map(str, command))}\n"
            f"{result.stderr[-3000:]}"
        )


# --------------------------------------------------
# Render video and narration
# --------------------------------------------------

def render(content):
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg on the runner."
        )

    segments = []
    scenes = content["scenes"]

    for index, scene in enumerate(scenes, start=1):
        print(f"Creating scene {index}/{len(scenes)}...")

        card = ASSETS / f"scene_{index:02d}.jpg"
        audio = ASSETS / f"scene_{index:02d}.mp3"
        clip = ASSETS / f"scene_{index:02d}.mp4"

        make_card(
            scene["screen"],
            index,
            len(scenes),
            card
        )

        # gTTS requires internet access and may occasionally fail.
        gTTS(
            text=scene["voice"],
            lang="en",
            slow=False
        ).save(str(audio))

        run_command([
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(card),
            "-i", str(audio),
            "-vf", "scale=1080:1920,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(clip)
        ])

        segments.append(clip)

    list_file = ASSETS / "concat.txt"

    list_file.write_text(
        "".join(
            f"file '{clip.resolve()}'\n"
            for clip in segments
        ),
        encoding="utf-8"
    )

    final_video = OUT / "daily_short.mp4"

    run_command([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(final_video)
    ])

    print(f"Video created: {final_video}")
    return final_video


# --------------------------------------------------
# Save script and YouTube metadata
# --------------------------------------------------

def save_metadata(content):
    (OUT / "content.json").write_text(
        json.dumps(content, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    script = "\n\n".join(
        scene["voice"] for scene in content["scenes"]
    )

    (OUT / "script.txt").write_text(
        script,
        encoding="utf-8"
    )

    metadata = (
        f"TITLE:\n{content['title']}\n\n"
        f"DESCRIPTION:\n{content['description']}\n\n"
        f"TOPIC:\n{content['topic']}\n\n"
        f"HASHTAGS:\n{' '.join(content['hashtags'])}\n"
    )

    (OUT / "youtube_metadata.txt").write_text(
        metadata,
        encoding="utf-8"
    )


# --------------------------------------------------
# Optional YouTube upload
# --------------------------------------------------

def upload_to_youtube(video, content):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_path = Path("token.json")

    if not token_path.exists():
        raise RuntimeError(
            "YouTube upload is enabled but token.json is missing."
        )

    token = json.loads(
        token_path.read_text(encoding="utf-8")
    )

    credentials = Credentials.from_authorized_user_info(
        token,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload"
        ]
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

        token_path.write_text(
            credentials.to_json(),
            encoding="utf-8"
        )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )

    body = {
        "snippet": {
            "title": content["title"][:100],
            "description": (
                content.get("description", "")
                + "\n\n"
                + " ".join(content.get("hashtags", []))
            )[:5000],
            "categoryId": "27",
            "tags": [
                str(tag).lstrip("#")
                for tag in content.get("hashtags", [])
            ][:15]
        },
        "status": {
            "privacyStatus": os.environ.get(
                "YOUTUBE_PRIVACY_STATUS", "private"
            ),
            "selfDeclaredMadeForKids": False
        }
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            resumable=True
        )
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            print(
                f"Upload progress: {int(status.progress() * 100)}%"
            )

    print("YouTube video ID:", response.get("id"))


# --------------------------------------------------
# Main entry point
# --------------------------------------------------

def main():
    print(f"Using Gemini model: {MODEL}")

    content = call_gemini()
    save_metadata(content)

    video = render(content)

    if UPLOAD:
        upload_to_youtube(video, content)
    else:
        print(
            "YouTube upload is disabled. "
            "The video will be saved as an artifact."
        )

    print("Finished. Generated files are in output/")


if __name__ == "__main__":
    main()
