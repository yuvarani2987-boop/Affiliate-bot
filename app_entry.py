from fastapi.responses import FileResponse

from app_v2 import ROOT, app

VERIFICATION_FILENAME = "tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt"


@app.get(f"/{VERIFICATION_FILENAME}", include_in_schema=False)
def tiktok_site_verification():
    return FileResponse(
        ROOT / VERIFICATION_FILENAME,
        media_type="text/plain; charset=utf-8",
        filename=VERIFICATION_FILENAME,
    )
