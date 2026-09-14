import base64
import json
import mimetypes
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
ROOT = Path(__file__).parent
DATA = ROOT / "data"
GEN = ROOT / "generated"
DATA.mkdir(exist_ok=True)
GEN.mkdir(exist_ok=True)
DB = DATA / "bot.db"

app = FastAPI(title="Angelovea TikTok Affiliate Bot v2")
app.mount("/generated", StaticFiles(directory=GEN), name="generated")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS prompts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      body TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS accounts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      platform TEXT NOT NULL,
      label TEXT NOT NULL,
      connected INTEGER DEFAULT 0,
      access_token TEXT,
      refresh_token TEXT,
      open_id TEXT,
      scope TEXT
    );
    CREATE TABLE IF NOT EXISTS oauth_states(
      state TEXT PRIMARY KEY,
      account_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(accounts)")}
    for name in ("access_token", "refresh_token", "open_id", "scope"):
        if name not in cols:
            con.execute(f"ALTER TABLE accounts ADD COLUMN {name} TEXT")
    if con.execute("SELECT COUNT(*) n FROM prompts").fetchone()["n"] == 0:
        defaults = [
            ("Fashion model", "Create a premium vertical 9:16 TikTok product photo using the selected product. Keep the exact product design, color, print and details. Put it on a stylish model in a clean studio with realistic lighting and high-end ecommerce quality."),
            ("Lifestyle", "Create a realistic vertical 9:16 lifestyle image featuring the selected product naturally in use. Keep the exact product appearance accurate. Bright social-commerce aesthetic, clean setting and attention-grabbing composition."),
            ("Luxury studio", "Create a luxury commercial product advertisement in vertical 9:16. Preserve the exact product. Elegant studio lighting, premium backdrop, realistic shadows, crisp details and no extra text."),
            ("Close-up details", "Create a vertical 9:16 product close-up emphasizing fabric, texture, stitching and premium details. Preserve the exact colors and product design. Photorealistic ecommerce lighting."),
            ("UGC creator", "Create a natural UGC-style vertical 9:16 image of a friendly creator presenting the selected product to camera. Preserve the product exactly. Authentic home setting and realistic smartphone-photo look."),
            ("Festive", "Create an elegant vertical 9:16 festive social-commerce image using the selected product. Preserve the exact product design and color. Warm premium lighting, tasteful celebration setting and photorealistic quality."),
        ]
        con.executemany("INSERT INTO prompts(name,body) VALUES(?,?)", defaults)
    if con.execute("SELECT COUNT(*) n FROM accounts WHERE platform='TikTok'").fetchone()["n"] == 0:
        con.executemany(
            "INSERT INTO accounts(platform,label,connected) VALUES(?,?,0)",
            [("TikTok", f"TikTok Account {i}") for i in range(1, 6)],
        )
    con.commit()
    con.close()


init_db()


def safe_local_path(public_path: str, allowed_exts=None) -> Path:
    if not public_path.startswith("/generated/"):
        raise HTTPException(400, "Use a file created or uploaded in this bot.")
    name = Path(public_path).name
    path = GEN / name
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Generated file not found.")
    if allowed_exts and path.suffix.lower() not in allowed_exts:
        raise HTTPException(400, "Unsupported file type.")
    return path


def get_image_bytes(ref: str):
    if ref.startswith("/generated/"):
        p = safe_local_path(ref, {".png", ".jpg", ".jpeg", ".webp"})
        return p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png"
    if not ref.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid image reference.")
    r = requests.get(ref, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
    if not mime.startswith("image/"):
        raise HTTPException(400, "Selected URL is not an image.")
    return r.content, mime


def save_bytes(data: bytes, prefix: str, ext: str):
    name = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    (GEN / name).write_bytes(data)
    return f"/generated/{name}"


@app.get("/")
def home():
    return FileResponse(ROOT / "index_v2.html")


@app.get("/health")
def health():
    return {"ok": True, "version": 2}


@app.get("/api/state")
def state():
    con = db()
    prompts = [dict(r) for r in con.execute("SELECT * FROM prompts ORDER BY id LIMIT 6")]
    accounts = [dict(r) for r in con.execute("SELECT id,platform,label,connected,open_id,scope FROM accounts WHERE platform='TikTok' ORDER BY id LIMIT 5")]
    con.close()
    return {
        "prompts": prompts,
        "accounts": accounts,
        "openai_ready": bool(os.getenv("OPENAI_API_KEY")),
        "gemini_ready": bool(os.getenv("GEMINI_API_KEY")),
        "tiktok_ready": bool(os.getenv("TIKTOK_CLIENT_KEY") and os.getenv("TIKTOK_CLIENT_SECRET") and os.getenv("TIKTOK_REDIRECT_URI")),
        "flow_url": os.getenv("GOOGLE_FLOW_URL", "https://labs.google/fx/tools/flow"),
        "manual_chatgpt_url": "https://chatgpt.com/",
        "manual_gemini_url": "https://gemini.google.com/",
    }


class PromptIn(BaseModel):
    name: str
    body: str


@app.put("/api/prompts/{prompt_id}")
def update_prompt(prompt_id: int, p: PromptIn):
    con = db()
    cur = con.execute("UPDATE prompts SET name=?,body=? WHERE id=?", (p.name.strip()[:60], p.body.strip()[:5000], prompt_id))
    con.commit()
    con.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Prompt not found.")
    return {"ok": True}


class LabelIn(BaseModel):
    label: str


@app.put("/api/accounts/{account_id}/label")
def rename_account(account_id: int, p: LabelIn):
    con = db()
    con.execute("UPDATE accounts SET label=? WHERE id=? AND platform='TikTok'", (p.label.strip()[:80] or "TikTok Account", account_id))
    con.commit()
    con.close()
    return {"ok": True}


@app.post("/api/accounts/{account_id}/disconnect")
def disconnect_account(account_id: int):
    con = db()
    con.execute("UPDATE accounts SET connected=0,access_token=NULL,refresh_token=NULL,open_id=NULL,scope=NULL WHERE id=? AND platform='TikTok'", (account_id,))
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/tiktok/login/{account_id}")
def tiktok_login(account_id: int):
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")
    if not client_key or not redirect_uri or not os.getenv("TIKTOK_CLIENT_SECRET"):
        raise HTTPException(400, "TikTok developer app keys are not configured on the server yet.")
    con = db()
    row = con.execute("SELECT id FROM accounts WHERE id=? AND platform='TikTok'", (account_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "TikTok account slot not found.")
    state_token = secrets.token_urlsafe(32)
    con.execute("DELETE FROM oauth_states WHERE created_at < ?", (int(time.time()) - 900,))
    con.execute("INSERT OR REPLACE INTO oauth_states(state,account_id,created_at) VALUES(?,?,?)", (state_token, account_id, int(time.time())))
    con.commit()
    con.close()
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": os.getenv("TIKTOK_SCOPES", "user.info.basic,video.publish"),
        "redirect_uri": redirect_uri,
        "state": state_token,
    }
    return RedirectResponse("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params))


@app.get("/api/tiktok/callback")
def tiktok_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        raise HTTPException(400, error_description or error)
    con = db()
    row = con.execute("SELECT account_id,created_at FROM oauth_states WHERE state=?", (state,)).fetchone()
    if not row or int(time.time()) - row["created_at"] > 900:
        con.close()
        raise HTTPException(400, "TikTok login expired. Start login again.")
    account_id = row["account_id"]
    payload = {
        "client_key": os.getenv("TIKTOK_CLIENT_KEY", ""),
        "client_secret": os.getenv("TIKTOK_CLIENT_SECRET", ""),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": os.getenv("TIKTOK_REDIRECT_URI", ""),
    }
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    try:
        data = r.json()
    except Exception:
        data = {"error_description": r.text[:600]}
    if not r.ok or data.get("error"):
        con.close()
        raise HTTPException(400, data.get("error_description") or str(data))
    con.execute(
        "UPDATE accounts SET connected=1,access_token=?,refresh_token=?,open_id=?,scope=? WHERE id=?",
        (data.get("access_token"), data.get("refresh_token"), data.get("open_id"), data.get("scope"), account_id),
    )
    con.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    con.commit()
    con.close()
    return RedirectResponse("/?tiktok=connected")


def tiktok_token(account_id: int):
    con = db()
    row = con.execute("SELECT access_token FROM accounts WHERE id=? AND platform='TikTok' AND connected=1", (account_id,)).fetchone()
    con.close()
    if not row or not row["access_token"]:
        raise HTTPException(400, "That TikTok account is not connected.")
    return row["access_token"]


@app.post("/api/tiktok/creator-info/{account_id}")
def creator_info(account_id: int):
    token = tiktok_token(account_id)
    r = requests.post("https://open.tiktokapis.com/v2/post/publish/creator_info/query/", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}, json={}, timeout=30)
    data = r.json() if r.content else {}
    if not r.ok or data.get("error", {}).get("code") not in (None, "ok"):
        raise HTTPException(r.status_code if not r.ok else 400, str(data))
    return data


class ProductIn(BaseModel):
    url: str


@app.post("/api/product")
def product(p: ProductIn):
    if not p.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Paste a valid product link.")
    try:
        r = requests.get(p.url, timeout=20, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36"})
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(400, f"This shop page blocked automatic loading. You can still upload the product image manually. ({e})")
    soup = BeautifulSoup(r.text, "html.parser")
    def meta(prop=None, name=None):
        tag = soup.find("meta", property=prop) if prop else soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""
    title = meta(prop="og:title") or (soup.title.text.strip() if soup.title else "Product")
    desc = meta(prop="og:description") or meta(name="description")
    imgs = []
    for val in (meta(prop="og:image"), meta(name="twitter:image")):
        if val:
            imgs.append(urljoin(r.url, val))
    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
        if src:
            src = urljoin(r.url, src)
            if src.startswith("http") and src not in imgs:
                imgs.append(src)
        if len(imgs) >= 12:
            break
    return {"title": title[:300], "description": desc[:1500], "images": imgs[:12], "resolved_url": r.url}


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename or "image.jpg").suffix.lower() or ".jpg"
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Upload PNG, JPG, JPEG or WEBP.")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "Image is too large. Maximum 20 MB.")
    return {"url": save_bytes(data, "upload", ext)}


class GenerateImageIn(BaseModel):
    image_ref: Optional[str] = None
    prompt: str
    engine: str = "openai"


@app.post("/api/generate-image")
def generate_image(g: GenerateImageIn):
    prompt = g.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Add a prompt first.")
    if g.engine == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise HTTPException(400, "Gemini API key is not configured.")
        parts = [{"text": prompt}]
        if g.image_ref:
            raw, mime = get_image_bytes(g.image_ref)
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}})
        model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
        url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
        payload = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "responseFormat": {"image": {"aspectRatio": "9:16", "imageSize": "1K"}}}}
        r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload, timeout=180)
        data = r.json() if r.content else {}
        if not r.ok:
            raise HTTPException(500, data.get("error", {}).get("message", str(data)))
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                blob = part.get("inlineData") or part.get("inline_data")
                if blob and blob.get("data"):
                    mime = blob.get("mimeType") or blob.get("mime_type") or "image/png"
                    ext = ".jpg" if "jpeg" in mime else ".png"
                    return {"url": save_bytes(base64.b64decode(blob["data"]), "gemini", ext), "engine": "gemini"}
        raise HTTPException(500, "Gemini returned no image.")

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(400, "OpenAI API key is not configured.")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
        if g.image_ref:
            raw, mime = get_image_bytes(g.image_ref)
            ext = ".jpg" if "jpeg" in mime else ".png"
            tmp = GEN / f"_reference_{uuid.uuid4().hex}{ext}"
            tmp.write_bytes(raw)
            try:
                with open(tmp, "rb") as fh:
                    res = client.images.edit(model=model, image=fh, prompt=prompt, size="1024x1536")
            finally:
                tmp.unlink(missing_ok=True)
        else:
            res = client.images.generate(model=model, prompt=prompt, size="1024x1536", n=1)
        item = res.data[0]
        if getattr(item, "b64_json", None):
            return {"url": save_bytes(base64.b64decode(item.b64_json), "openai", ".png"), "engine": "openai"}
        if getattr(item, "url", None):
            rr = requests.get(item.url, timeout=60)
            rr.raise_for_status()
            return {"url": save_bytes(rr.content, "openai", ".png"), "engine": "openai"}
        raise RuntimeError("No image data returned.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"OpenAI image generation failed: {e}")


class CaptionIn(BaseModel):
    title: str = ""
    description: str = ""
    product_url: str = ""


@app.post("/api/caption")
def caption(c: CaptionIn):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        title = c.title or "this product"
        return {"caption": f"✨ {title} — check it out in my TikTok Shop showcase. #TikTokShop #TikTokFinds #Affiliate"}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        res = client.responses.create(
            model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini"),
            input=("Write one short TikTok Shop affiliate caption for this product. Be persuasive but do not invent claims. Mention that it is an affiliate recommendation naturally. Include 3-5 relevant hashtags.\n"
                   f"Product: {c.title}\nDescription: {c.description}\nProduct link context: {c.product_url}")
        )
        return {"caption": res.output_text.strip()}
    except Exception as e:
        raise HTTPException(500, f"Caption generation failed: {e}")


class VideoStartIn(BaseModel):
    image_ref: str
    prompt: str


@app.post("/api/gemini-video/start")
def gemini_video_start(v: VideoStartIn):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(400, "Gemini API key is not configured. Use Google Flow manual mode instead.")
    raw, mime = get_image_bytes(v.image_ref)
    model = os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview")
    payload = {
        "instances": [{"prompt": v.prompt.strip(), "image": {"inlineData": {"mimeType": mime, "data": base64.b64encode(raw).decode()}}}],
        "parameters": {"aspectRatio": "9:16"},
    }
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predictLongRunning", headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload, timeout=60)
    data = r.json() if r.content else {}
    if not r.ok or not data.get("name"):
        raise HTTPException(500, data.get("error", {}).get("message", str(data)))
    return {"operation": data["name"]}


@app.get("/api/gemini-video/status")
def gemini_video_status(operation: str):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(400, "Gemini API key is not configured.")
    if not operation.startswith("operations/"):
        raise HTTPException(400, "Invalid operation id.")
    r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{operation}", headers={"x-goog-api-key": key}, timeout=40)
    data = r.json() if r.content else {}
    if not r.ok:
        raise HTTPException(500, data.get("error", {}).get("message", str(data)))
    if not data.get("done"):
        return {"done": False}
    if data.get("error"):
        raise HTTPException(500, data["error"].get("message", str(data["error"])))
    samples = data.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
    if not samples:
        raise HTTPException(500, "Video finished but no video file was returned.")
    uri = samples[0].get("video", {}).get("uri")
    if not uri:
        raise HTTPException(500, "Video download URL missing.")
    rr = requests.get(uri, headers={"x-goog-api-key": key}, timeout=120, allow_redirects=True)
    rr.raise_for_status()
    return {"done": True, "url": save_bytes(rr.content, "veo", ".mp4")}


@app.post("/api/upload-video")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if ext not in {".mp4", ".mov", ".webm", ".mkv"}:
        raise HTTPException(400, "Upload MP4, MOV, WEBM or MKV.")
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(400, "Video is too large. Maximum 100 MB.")
    return {"url": save_bytes(data, "video", ext)}


class TikTokFilePostIn(BaseModel):
    account_id: int
    video_path: str
    title: str = ""
    privacy_level: str
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    consent: bool = False


@app.post("/api/tiktok/post-file")
def tiktok_post_file(p: TikTokFilePostIn):
    if not p.consent:
        raise HTTPException(400, "Confirm the post before publishing.")
    token = tiktok_token(p.account_id)
    path = safe_local_path(p.video_path, {".mp4", ".mov", ".webm", ".mkv"})
    raw = path.read_bytes()
    size = len(raw)
    if size == 0:
        raise HTTPException(400, "Video file is empty.")
    body = {
        "post_info": {
            "title": p.title[:2200],
            "privacy_level": p.privacy_level,
            "disable_comment": p.disable_comment,
            "disable_duet": p.disable_duet,
            "disable_stitch": p.disable_stitch,
            "brand_content_toggle": True,
            "brand_organic_toggle": False,
            "is_aigc": True,
        },
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
    }
    init = requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}, json=body, timeout=40)
    data = init.json() if init.content else {}
    err = data.get("error", {})
    if not init.ok or err.get("code") not in (None, "ok"):
        raise HTTPException(init.status_code if not init.ok else 400, str(data))
    upload_url = data.get("data", {}).get("upload_url")
    publish_id = data.get("data", {}).get("publish_id")
    if not upload_url:
        raise HTTPException(500, "TikTok did not return an upload URL.")
    up = requests.put(upload_url, headers={"Content-Range": f"bytes 0-{size-1}/{size}", "Content-Type": "video/mp4"}, data=raw, timeout=180)
    if not up.ok:
        raise HTTPException(up.status_code, f"TikTok video upload failed: {up.text[:500]}")
    return {"ok": True, "publish_id": publish_id}


class PublishStatusIn(BaseModel):
    account_id: int
    publish_id: str


@app.post("/api/tiktok/publish-status")
def publish_status(p: PublishStatusIn):
    token = tiktok_token(p.account_id)
    r = requests.post("https://open.tiktokapis.com/v2/post/publish/status/fetch/", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}, json={"publish_id": p.publish_id}, timeout=30)
    data = r.json() if r.content else {}
    if not r.ok:
        raise HTTPException(r.status_code, str(data))
    return data
