from fastapi.responses import PlainTextResponse

from app_v2 import app


@app.get("/tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt", include_in_schema=False)
def tiktok_site_verification():
    return PlainTextResponse(
        "tiktok-developers-site-verification=ltZD3Glempkz2AdpF1grLyTP7WHZ2gz5\n"
    )
