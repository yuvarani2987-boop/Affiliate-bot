import mimetypes
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import requests
from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

import app_legacy as legacy

app = legacy.app

VERIFICATION_FILENAME = "tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt"
VERIFICATION_VALUE = "tiktok-developers-site-verification=ltZD3Glempkz2AdpF1grLyTP7WHZ2gz5"


@app.get(f"/{VERIFICATION_FILENAME}", include_in_schema=False)
def tiktok_site_verification():
    return PlainTextResponse(VERIFICATION_VALUE, media_type="text/plain")


def _token(account_id: int) -> str:
    con = legacy.db()
    row = con.execute(
        "SELECT access_token FROM accounts WHERE id=? AND platform='TikTok' AND connected=1",
        (account_id,),
    ).fetchone()
    con.close()
    if not row or not row["access_token"]:
        raise HTTPException(400, "Connect TikTok first.")
    return row["access_token"]


def _video_bytes(file: UploadFile):
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".webm"}:
        raise HTTPException(400, "Use MP4, MOV or WEBM.")
    return ext


def _put_tiktok(upload_url: str, raw: bytes, mime: str):
    size = len(raw)
    if not size:
        raise HTTPException(400, "Video file is empty.")
    up = requests.put(
        upload_url,
        headers={
            "Content-Range": f"bytes 0-{size-1}/{size}",
            "Content-Length": str(size),
            "Content-Type": mime,
        },
        data=raw,
        timeout=180,
    )
    if not up.ok:
        raise HTTPException(up.status_code, f"TikTok upload failed: {up.text[:500]}")


@app.get("/api/tiktok/review-login/{account_id}")
def review_login(account_id: int):
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")
    if not client_key or not redirect_uri or not os.getenv("TIKTOK_CLIENT_SECRET"):
        raise HTTPException(400, "TikTok developer credentials are not configured.")
    con = legacy.db()
    row = con.execute(
        "SELECT id FROM accounts WHERE id=? AND platform='TikTok'", (account_id,)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "TikTok account slot not found.")
    state = f"{account_id}." + secrets.token_urlsafe(24)
    (legacy.ROOT / "data" / "oauth_state.txt").write_text(state, encoding="utf-8")
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": "user.info.basic,video.publish,video.upload",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return RedirectResponse("https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params))


@app.get("/review-demo", response_class=HTMLResponse)
def review_demo():
    return HTMLResponse("""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Affiliate AI Bot - TikTok Review Demo</title>
<style>
body{font-family:Arial,sans-serif;background:#f6f7fb;color:#172033;margin:0}.wrap{max-width:760px;margin:30px auto;padding:18px}.card{background:white;border:1px solid #e1e5ec;border-radius:18px;padding:22px;margin:16px 0;box-shadow:0 8px 25px #0000000d}h1{margin-bottom:8px}.muted{color:#667085}.btn{display:inline-block;background:#6f3cf2;color:white;text-decoration:none;border:0;border-radius:12px;padding:12px 16px;font-weight:700;cursor:pointer}.pink{background:#e83e77}.dark{background:#172033}input,select,textarea{width:100%;box-sizing:border-box;padding:11px;margin:8px 0 14px;border:1px solid #ccd3dd;border-radius:10px}label{font-weight:700}.ok{background:#edf9f3;padding:12px;border-radius:10px;color:#08734d}.note{background:#fff8e8;padding:12px;border-radius:10px;color:#7d5a00}
</style></head><body><div class="wrap">
<h1>Affiliate AI Bot — TikTok Review Demo</h1><p class="muted">This page demonstrates Login Kit, <b>user.info.basic</b>, <b>video.publish</b>, and <b>video.upload</b> for TikTok review.</p>
<div class="card"><h2>1. Connect TikTok with review scopes</h2><p>Use TikTok's official authorization screen. The bot never asks for your TikTok password.</p><a class="btn" href="/api/tiktok/review-login/1">Connect / re-authorize TikTok Account 1</a><p class="note">After TikTok sends you back to the bot homepage, reopen <b>/review-demo</b> in this tab.</p></div>
<div class="card"><h2>2. Direct Post — video.publish</h2><p>Upload a short test video, choose the privacy option TikTok returns for this creator, and explicitly confirm the post.</p><button class="btn dark" type="button" onclick="loadInfo()">Load TikTok posting options</button><form action="/api/tiktok/review-direct/1" method="post" enctype="multipart/form-data"><label>Video</label><input name="file" type="file" accept="video/mp4,video/quicktime,video/webm" required><label>Caption</label><textarea name="caption">Affiliate AI Bot review test</textarea><label>Privacy</label><select name="privacy_level" id="privacy"><option value="SELF_ONLY">SELF ONLY</option></select><label><input style="width:auto" name="consent" type="checkbox" value="true" required> I reviewed this video and want to publish it now.</label><br><button class="btn pink" type="submit">Post test video to TikTok</button></form></div>
<div class="card"><h2>3. Upload Draft — video.upload</h2><p>Upload a video as a TikTok draft. TikTok will send an inbox notification so the creator can continue editing and post inside TikTok.</p><form action="/api/tiktok/review-draft/1" method="post" enctype="multipart/form-data"><label>Video</label><input name="file" type="file" accept="video/mp4,video/quicktime,video/webm" required><button class="btn" type="submit">Send video to TikTok as draft</button></form></div>
</div><script>
async function loadInfo(){try{const r=await fetch('/api/tiktok/creator-info/1',{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.detail||JSON.stringify(d));const info=d.data||{};const s=document.getElementById('privacy');s.innerHTML='';(info.privacy_level_options||['SELF_ONLY']).forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x.replaceAll('_',' ');s.appendChild(o)});alert('Posting options loaded for '+(info.creator_nickname||info.creator_username||'connected TikTok account'));}catch(e){alert(e.message)}}
</script></body></html>
""")


@app.post("/api/tiktok/review-direct/{account_id}", response_class=HTMLResponse)
async def review_direct(
    account_id: int,
    file: UploadFile = File(...),
    caption: str = Form("Affiliate AI Bot review test"),
    privacy_level: str = Form("SELF_ONLY"),
    consent: bool = Form(False),
):
    if not consent:
        raise HTTPException(400, "Explicit confirmation is required.")
    ext = _video_bytes(file)
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(400, "Use a video smaller than 100 MB for this review demo.")
    token = _token(account_id)
    size = len(raw)
    body = {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": privacy_level,
            "disable_comment": False,
            "disable_duet": False,
            "disable_stitch": False,
            "brand_content_toggle": True,
            "brand_organic_toggle": False,
            "is_aigc": True,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        },
    }
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=body,
        timeout=40,
    )
    data = r.json() if r.content else {}
    err = data.get("error", {})
    if not r.ok or err.get("code") not in (None, "ok"):
        raise HTTPException(r.status_code if not r.ok else 400, str(data))
    upload_url = data.get("data", {}).get("upload_url")
    publish_id = data.get("data", {}).get("publish_id")
    if not upload_url:
        raise HTTPException(500, "TikTok did not return an upload URL.")
    mime = {".mp4":"video/mp4", ".mov":"video/quicktime", ".webm":"video/webm"}[ext]
    _put_tiktok(upload_url, raw, mime)
    return HTMLResponse(f"<html><body style='font-family:Arial;padding:40px'><h2>Direct Post sent to TikTok ✅</h2><p>Publish ID: <b>{publish_id}</b></p><p><a href='/review-demo'>Return to review demo</a></p></body></html>")


@app.post("/api/tiktok/review-draft/{account_id}", response_class=HTMLResponse)
async def review_draft(account_id: int, file: UploadFile = File(...)):
    ext = _video_bytes(file)
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(400, "Use a video smaller than 100 MB for this review demo.")
    token = _token(account_id)
    size = len(raw)
    body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        }
    }
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=body,
        timeout=40,
    )
    data = r.json() if r.content else {}
    err = data.get("error", {})
    if not r.ok or err.get("code") not in (None, "ok"):
        raise HTTPException(r.status_code if not r.ok else 400, str(data))
    upload_url = data.get("data", {}).get("upload_url")
    publish_id = data.get("data", {}).get("publish_id")
    if not upload_url:
        raise HTTPException(500, "TikTok did not return an upload URL.")
    mime = {".mp4":"video/mp4", ".mov":"video/quicktime", ".webm":"video/webm"}[ext]
    _put_tiktok(upload_url, raw, mime)
    return HTMLResponse(f"<html><body style='font-family:Arial;padding:40px'><h2>TikTok draft uploaded ✅</h2><p>Publish ID: <b>{publish_id}</b></p><p>Open the TikTok app inbox to continue editing and post the draft.</p><p><a href='/review-demo'>Return to review demo</a></p></body></html>")
