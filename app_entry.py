from fastapi.responses import PlainTextResponse

from app_v2 import app

VERIFICATION_FILENAME = "tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt"
VERIFICATION_VALUE = "tiktok-developers-site-verification=ltZD3Glempkz2AdpF1grLyTP7WHZ2gz5"


@app.get(f"/{VERIFICATION_FILENAME}", include_in_schema=False)
def tiktok_site_verification():
    return PlainTextResponse(VERIFICATION_VALUE, media_type="text/plain")
