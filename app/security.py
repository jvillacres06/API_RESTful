
from fastapi import Header, HTTPException
from .config import settings

async def api_key_guard(x_api_key: str | None = Header(None)):
    if not getattr(settings, "API_KEY", None):
        return
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
