import os, json, re, subprocess, textwrap, shutil, base64
from pathlib import Path
from datetime import datetime, timezone
import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

ROOT = Path(".")
OUT = ROOT / "output"
ASSETS = OUT / "assets"
OUT.mkdir(exist_ok=True)
ASSETS.mkdir(exist_ok=True)

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
UPLOAD = os.environ.get("YOUTUBE_UPLOAD", "false").lower() == "true"

def call_gemini():
    if not API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY GitHub secret.")
    prompt = """
Create one original YouTube Short for this channel:
Niche: fresher careers, office life, discipline, failures, and personal growth.
Audience: Indian students and early-career professionals.
Language: natural spoken English, simple and specific, not generic motivational fluff.
Length: about 40–55 seconds. No invented statistics, no fake personal stories, no copied creator material.
Choose one useful, relatable idea. Make the first line a strong hook. Give actionable advice.
Return ONLY valid JSON with this exact schema:
{
 "topic":"short topic",
 "title":"clear curiosity-driven title, no misleading claim",
 "description":"2-3 sentence description and a few relevant hashtags",
 "scenes":[
   {"voice":"spoken narration for this scene","screen":"short on-screen text, max 9 words"}
 ],
 "hashtags":["#Shorts","#Career"]
}
Use 4 to 6 scenes. Each voice segment should sound natural when read aloud. No markdown fences.
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}],
                                 "generationConfig":{"temperature":0.8,"responseMimeType":"application/json"}}, timeout=90)
    if not r.ok:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:1000]}")
    data = r.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    content = json.loads(raw)
    if not isinstance(content.get("scenes"), list) or len(content["scenes"]) < 3:
        raise RuntimeError("Gemini returned an incomplete script.")
    content["scenes"] = content["scenes"][:6]
    content["created_utc"] = datetime.now(timezone.utc).isoformat()
    return content

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"
    ]
    for f in candidates:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()

def wrap_text(draw, text, fnt, max_width):
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0,0), candidate, font=fnt)[2] <= max_width:
            current = candidate
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def make_card(text, idx, total, path):
    W, H = 1080, 1920
    im = Image.new("RGB", (W,H), (13, 22, 42))
    d = ImageDraw.Draw(im)
    # Free, locally drawn abstract background
    for y in range(H):
        t = y/H
        col = (int(12+18*t), int(25+12*t), int(48+28*t))
        d.line((0,y,W,y), fill=col)
    d.ellipse((700,-160,1260,400), fill=(27,62,96))
    d.ellipse((-220,1450,380,2050), fill=(24,53,83))
    d.rounded_rectangle((72,140,1008,1780), radius=42, outline=(86,151,200), width=4)
    d.text((105,205), "ONE THING TO REMEMBER", font=font(30, True), fill=(127,210,255))
    d.text((105,1630), f"{idx:02d} / {total:02d}   •   CAREER GROWTH", font=font(27, True), fill=(170,190,215))
    lines = wrap_text(d, text, font(68, True), 820)
    block_h = len(lines)*92
    y = (H-block_h)//2
    for line in lines:
        d.text((W//2,y), line, font=font(68,True), fill=(255,255,255), anchor="mt", stroke_width=0)
        y += 92
    im.save(path, quality=92)

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr[-2000:]}")

def render(content):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required. GitHub's ubuntu-latest runner usually provides it.")
    segments = []
    scenes = content["scenes"]
    for i, scene in enumerate(scenes, start=1):
        card = ASSETS / f"scene_{i:02d}.jpg"
        audio = ASSETS / f"scene_{i:02d}.mp3"
        clip = ASSETS / f"scene_{i:02d}.mp4"
        make_card(scene.get("screen") or scene["voice"], i, len(scenes), card)
        gTTS(text=scene["voice"], lang="en", slow=False).save(str(audio))
        run(["ffmpeg","-y","-loop","1","-i",str(card),"-i",str(audio),
             "-vf","scale=1080:1920,format=yuv420p","-c:v","libx264","-preset","ultrafast",
             "-tune","stillimage","-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(clip)])
        segments.append(clip)
    listfile = ASSETS / "concat.txt"
    listfile.write_text("\n".join("file '"+str(p.resolve()).replace("'","'\\''")+"'" for p in segments), encoding="utf-8")
    final = OUT / "daily_short.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listfile),"-c","copy","-movflags","+faststart",str(final)])
    return final

def save_metadata(content):
    (OUT/"content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    script = "\n\n".join(s["voice"] for s in content["scenes"])
    (OUT/"script.txt").write_text(script, encoding="utf-8")
    (OUT/"youtube_metadata.txt").write_text(
        f"TITLE:\n{content['title']}\n\nDESCRIPTION:\n{content['description']}\n\nTOPIC:\n{content['topic']}\n", encoding="utf-8")

def upload_to_youtube(video, content):
    # OAuth secrets are decoded in the workflow; token.json must contain a refresh token.
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    token_path = Path("token.json")
    if not token_path.exists():
        raise RuntimeError("YOUTUBE_UPLOAD=true but token.json was not restored from GitHub secrets.")
    token = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(token, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": content["title"][:100],
            "description": (content.get("description","") + "\n\n" + " ".join(content.get("hashtags", [])))[:5000],
            "categoryId": "27",
            "tags": [h.lstrip("#") for h in content.get("hashtags", [])][:15]
        },
        "status": {
            "privacyStatus": os.environ.get("YOUTUBE_PRIVACY_STATUS", "private"),
            "selfDeclaredMadeForKids": False
        }
    }
    request = youtube.videos().insert(part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True))
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress()*100)}%")
    print("Uploaded video ID:", response.get("id"))

def main():
    content = call_gemini()
    save_metadata(content)
    video = render(content)
    if UPLOAD:
        upload_to_youtube(video, content)
    else:
        print("Upload disabled. Review output/daily_short.mp4 before enabling YouTube upload.")
    print("Finished. Files are in output/")

if __name__ == "__main__":
    main()
