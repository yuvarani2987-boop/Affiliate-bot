import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app_v2 import app

ROOT = Path(__file__).parent
CHATGPT_EMAIL = "yuvarani2987@gmail.com"
VERIFICATION_FILENAME = "tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt"
VERIFICATION_VALUE = "tiktok-developers-site-verification=ltZD3Glempkz2AdpF1grLyTP7WHZ2gz5"


@app.middleware("http")
async def recreated_angelovea_home(request: Request, call_next):
    if request.method == "GET" and request.url.path == "/":
        html = (ROOT / "index_v2.html").read_text(encoding="utf-8")
        html = html.replace("Angelovea Affiliate Bot", "Angelovea AI")

        chatgpt_section = f'''<section class="step"><div class="num">3</div><div class="card">
<div class="eyebrow">CHATGPT ACCOUNT</div>
<h2>Log in to ChatGPT</h2>
<p>Use your ChatGPT account for manual image creation. Automatic image generation below uses the OpenAI API configured on this bot.</p>
<label>Your ChatGPT email</label>
<div class="row"><input value="{CHATGPT_EMAIL}" readonly aria-label="ChatGPT email"><button class="btn ghost" onclick="navigator.clipboard.writeText('{CHATGPT_EMAIL}')">Copy email</button></div>
<button class="btn gradient" style="margin-top:12px;width:100%" onclick="window.open('https://chatgpt.com/auth/login/','_blank','noopener')">Continue to ChatGPT login ↗</button>
<div class="row" style="margin-top:11px"><div id="openaiState" class="status">OpenAI: checking…</div><div id="geminiState" class="status">Gemini: checking…</div></div>
<div class="row" style="margin-top:11px"><button class="btn secondary" onclick="openManualAI('chatgpt')">Open ChatGPT ↗</button><button class="btn secondary" onclick="openManualAI('gemini')">Open Gemini ↗</button></div>
<div class="note">Your ChatGPT email is shown here for convenience. Sign-in happens only on OpenAI's official site; Angelovea AI does not collect or store your ChatGPT password. Your ChatGPT subscription is separate from OpenAI API access used for automatic generation.</div>
</div></section>'''

        html = re.sub(
            r'<section class="step"><div class="num">3</div>.*?</section>',
            chatgpt_section,
            html,
            count=1,
            flags=re.S,
        )
        return HTMLResponse(html)
    return await call_next(request)


@app.get(f"/{VERIFICATION_FILENAME}", include_in_schema=False)
def tiktok_site_verification():
    return PlainTextResponse(VERIFICATION_VALUE, media_type="text/plain")
