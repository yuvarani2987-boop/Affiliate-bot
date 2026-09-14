import base64
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
ROOT = Path(__file__).parent
DB = ROOT / "data" / "bot.db"
GEN = ROOT / "generated"
GEN.mkdir(exist_ok=True)

app = FastAPI(title="TikTok Affiliate Creator Bot")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
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
    """)

    # Lightweight migration for users upgrading from v1.
    cols = {r["name"] for r in con.execute("PRAGMA table_info(accounts)")}
    for name in ("access_token","refresh_token","open_id","scope"):
        if name not in cols:
            con.execute(f"ALTER TABLE accounts ADD COLUMN {name} TEXT")

    count = con.execute("SELECT COUNT(*) n FROM prompts").fetchone()["n"]
    if count == 0:
        defaults = [
            ("Fashion model", "Create a premium vertical 9:16 TikTok product photo using the selected product. Keep the product design, color and details accurate. Put it on a stylish model in a clean studio, realistic lighting, high-end ecommerce quality."),
            ("Lifestyle", "Create a realistic vertical 9:16 lifestyle image featuring the selected product naturally in use. Keep the exact product appearance accurate. Bright social-commerce aesthetic, clean background, attention-grabbing composition."),
            ("Luxury studio", "Create a luxury commercial product advertisement in vertical 9:16. Preserve the exact product. Elegant studio lighting, premium backdrop, realistic shadows, crisp details, no extra text."),
            ("Close-up details", "Create a vertical 9:16 product close-up emphasizing fabric, texture, stitching and premium details. Preserve exact colors and product design. Photorealistic ecommerce lighting."),
            ("UGC creator", "Create a natural UGC-style vertical 9:16 image of a friendly creator presenting the selected product to camera. Preserve the product exactly. Authentic home setting, realistic smartphone-photo look."),
            ("Festive", "Create an elegant vertical 9:16 festive social-commerce image using the selected product. Preserve exact product design and color. Warm premium lighting, tasteful celebration setting, photorealistic.")
        ]
        con.executemany("INSERT INTO prompts(name,body) VALUES(?,?)", defaults)
    count2 = con.execute("SELECT COUNT(*) n FROM accounts").fetchone()["n"]
    if count2 == 0:
        rows = [("TikTok", f"TikTok Account {i}", 0) for i in range(1,6)]
        rows += [("Google Flow","Google Flow",0), ("ChatGPT","OpenAI API",0), ("Gemini","Gemini",0)]
        con.executemany("INSERT INTO accounts(platform,label,connected) VALUES(?,?,?)", rows)
    con.commit()
    con.close()

init_db()


@app.get("/")
def home():
     return FileResponse(ROOT / "index.html")


                        


                        


@app.get("/api/state")
def state():
    con = db()
    prompts = [dict(r) for r in con.execute("SELECT * FROM prompts ORDER BY id")]
    accounts = [dict(r) for r in con.execute("SELECT * FROM accounts ORDER BY id")]
    con.close()
    return {
        "prompts": prompts,
        "accounts": accounts,
        "openai_ready": bool(os.getenv("OPENAI_API_KEY")),
        "flow_url": os.getenv("GOOGLE_FLOW_URL", "https://labs.google/fx/tools/flow")
    }


class PromptIn(BaseModel):
    name: str
    body: str


@app.put("/api/prompts/{prompt_id}")
def update_prompt(prompt_id: int, p: PromptIn):
    con = db()
    con.execute("UPDATE prompts SET name=?, body=? WHERE id=?", (p.name, p.body, prompt_id))
    con.commit()
    con.close()
    return {"ok": True}



@app.get("/api/tiktok/login/{account_id}")
def tiktok_login(account_id: int):
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")
    if not client_key or not redirect_uri:
        raise HTTPException(400, "Set TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI in .env first.")

    con = db()
    row = con.execute("SELECT * FROM accounts WHERE id=? AND platform='TikTok'", (account_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "TikTok account slot not found.")

    import secrets
    state = f"{account_id}." + secrets.token_urlsafe(24)
    # Persist state server-side in a tiny file for this local single-user starter.
    (ROOT / "data" / "oauth_state.txt").write_text(state, encoding="utf-8")
    scopes = os.getenv("TIKTOK_SCOPES", "user.info.basic,video.publish")
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": scopes,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return RedirectResponse("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params))


@app.get("/api/tiktok/callback")
def tiktok_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        raise HTTPException(400, f"TikTok authorization failed: {error_description or error}")
    state_file = ROOT / "data" / "oauth_state.txt"
    expected = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    if not expected or state != expected:
        raise HTTPException(400, "OAuth state mismatch. Please start login again.")
    try:
        account_id = int(state.split(".", 1)[0])
    except Exception:
        raise HTTPException(400, "Invalid OAuth state.")

    data = {
        "client_key": os.getenv("TIKTOK_CLIENT_KEY", ""),
        "client_secret": os.getenv("TIKTOK_CLIENT_SECRET", ""),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": os.getenv("TIKTOK_REDIRECT_URI", ""),
    }
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    try:
        payload = r.json()
    except Exception:
        payload = {"error_description": r.text[:500]}
    if not r.ok or payload.get("error"):
        raise HTTPException(r.status_code if r.status_code >= 400 else 400,
                            payload.get("error_description") or str(payload))

    con = db()
    con.execute(
        "UPDATE accounts SET connected=1,access_token=?,refresh_token=?,open_id=?,scope=? WHERE id=?",
        (payload.get("access_token"), payload.get("refresh_token"), payload.get("open_id"), payload.get("scope"), account_id)
    )
    con.commit()
    con.close()
    try:
        state_file.unlink()
    except Exception:
        pass
    return RedirectResponse("/?tiktok=connected")


@app.post("/api/tiktok/creator-info/{account_id}")
def creator_info(account_id: int):
    con = db()
    row = con.execute("SELECT access_token FROM accounts WHERE id=? AND platform='TikTok'", (account_id,)).fetchone()
    con.close()
    if not row or not row["access_token"]:
        raise HTTPException(400, "This TikTok account is not connected.")
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        headers={
            "Authorization": f"Bearer {row['access_token']}",
            "Content-Type": "application/json; charset=UTF-8"
        },
        json={},
        timeout=20
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:1000]}
    if not r.ok:
        raise HTTPException(r.status_code, str(data))
    return data


class TikTokPostIn(BaseModel):
    account_id: int
    video_url: str
    title: str = ""
    privacy_level: str
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    is_aigc: bool = True
    consent: bool = False


@app.post("/api/tiktok/direct-post")
def direct_post(p: TikTokPostIn):
    if not p.consent:
        raise HTTPException(400, "Explicit confirmation is required before posting.")
    if not p.video_url.startswith("https://"):
        raise HTTPException(400, "TikTok PULL_FROM_URL requires an HTTPS video URL from a domain/prefix you have verified with TikTok.")

    con = db()
    row = con.execute("SELECT access_token FROM accounts WHERE id=? AND platform='TikTok'", (p.account_id,)).fetchone()
    con.close()
    if not row or not row["access_token"]:
        raise HTTPException(400, "This TikTok account is not connected.")

    body = {
        "post_info": {
            "title": p.title[:2200],
            "privacy_level": p.privacy_level,
            "disable_comment": p.disable_comment,
            "disable_duet": p.disable_duet,
            "disable_stitch": p.disable_stitch,
            "is_aigc": p.is_aigc,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": p.video_url
        }
    }
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {row['access_token']}",
            "Content-Type": "application/json; charset=UTF-8"
        },
        json=body,
        timeout=30
    )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:1000]}
    if not r.ok:
        raise HTTPException(r.status_code, str(data))
    return data


class ProductIn(BaseModel):
    url: str


@app.post("/api/product")
def product(p: ProductIn):
    """Best-effort public metadata retrieval. Does not bypass login or anti-bot controls."""
    if not p.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Please enter a valid http/https product link.")
    try:
        r = requests.get(
            p.url,
            timeout=15,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AffiliateCreator/1.0)"}
        )
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(400, f"Could not open this public page: {e}")

    soup = BeautifulSoup(r.text, "html.parser")
    def meta(prop=None, name=None):
        tag = soup.find("meta", property=prop) if prop else soup.find("meta", attrs={"name": name})
        return tag.get("content", "").strip() if tag else ""

    title = meta(prop="og:title") or (soup.title.text.strip() if soup.title else "Product")
    desc = meta(prop="og:description") or meta(name="description")
    imgs = []
    for prop in ["og:image", "twitter:image"]:
        val = meta(prop=prop) if prop == "og:image" else meta(name=prop)
        if val and val not in imgs:
            imgs.append(val)
    # Add a few public image URLs found in the HTML.
    for im in soup.find_all("img"):
        src = im.get("src") or im.get("data-src")
        if src and src.startswith("http") and src not in imgs:
            imgs.append(src)
        if len(imgs) >= 8:
            break

    return {"title": title[:300], "description": desc[:1000], "images": imgs[:8], "resolved_url": r.url}


class GenerateIn(BaseModel):
    image_url: Optional[str] = None
    prompt: str
    engine: str = "openai"


@app.post("/api/generate-image")
def generate_image(g: GenerateIn):
    if g.engine != "openai":
        raise HTTPException(501, "Gemini adapter is a placeholder in this starter. Use OpenAI or add your Gemini API integration.")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(400, "OPENAI_API_KEY is not configured. Copy .env.example to .env and add your API key.")

    prompt = g.prompt.strip()
    if g.image_url:
        prompt += f"\nReference product image: {g.image_url}\nKeep the product visually accurate."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        result = client.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            prompt=prompt,
            size="1024x1536",
            n=1,
        )
        item = result.data[0]
        if getattr(item, "b64_json", None):
            raw = base64.b64decode(item.b64_json)
            name = f"image_{len(list(GEN.glob('image_*.png'))) + 1}.png"
            path = GEN / name
            path.write_bytes(raw)
            return {"url": f"/generated/{name}"}
        if getattr(item, "url", None):
            return {"url": item.url}
        raise RuntimeError("Image API returned no image data.")
    except Exception as e:
        raise HTTPException(500, f"Image generation failed: {e}")


class CaptionIn(BaseModel):
    title: str = ""
    description: str = ""
    product_url: str = ""


@app.post("/api/caption")
def caption(c: CaptionIn):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        # Useful demo fallback
        title = c.title or "this product"
        return {
            "caption": f"✨ Found {title}! Check the product link for details. #TikTokShop #TikTokFinds #Affiliate"
        }
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        res = client.responses.create(
            model="gpt-5.6-luna",
            input=(
                "Write one short TikTok Shop affiliate caption. Be persuasive but do not make "
                "unsupported claims. Include 3-5 relevant hashtags.\n"
                f"Product: {c.title}\nDescription: {c.description}\nLink: {c.product_url}"
            )
        )
        return {"caption": res.output_text.strip()}
    except Exception as e:
        raise HTTPException(500, f"Caption generation failed: {e}")


class ConnectIn(BaseModel):
    account_id: int
    connected: bool


@app.post("/api/account/demo-connect")
def demo_connect(x: ConnectIn):
    """UI-state only. Real TikTok/Google OAuth must be wired with the official provider."""
    con = db()
    con.execute("UPDATE accounts SET connected=? WHERE id=?", (1 if x.connected else 0, x.account_id))
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/tiktok/status")
def tiktok_status():
    return {
        "configured": bool(os.getenv("TIKTOK_CLIENT_KEY") and os.getenv("TIKTOK_CLIENT_SECRET")),
        "message": "Official OAuth / Content Posting API adapter must be completed with your approved TikTok developer app."
    }


