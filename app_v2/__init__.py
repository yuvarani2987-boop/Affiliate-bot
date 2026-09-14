import importlib.util
from pathlib import Path

from fastapi.responses import PlainTextResponse

_legacy_path = Path(__file__).resolve().parent.parent / "app_v2.py"
_spec = importlib.util.spec_from_file_location("_affiliate_bot_app_v2_legacy", _legacy_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

app = _mod.app

VERIFICATION_FILENAME = "tiktokltZD3Glempkz2AdpF1grLyTP7WHZ2gz5.txt"
VERIFICATION_VALUE = "tiktok-developers-site-verification=ltZD3Glempkz2AdpF1grLyTP7WHZ2gz5"


@app.get(f"/{VERIFICATION_FILENAME}", include_in_schema=False)
def tiktok_site_verification():
    return PlainTextResponse(VERIFICATION_VALUE, media_type="text/plain")
