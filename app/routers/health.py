from fastapi import APIRouter
from sqlalchemy import text
from ..database import SessionLocal
from ..mqtt_client import mqtt_client
from ..services import opcua_ingestor

router = APIRouter()

@router.get("/health")
def health():
    db_ok = False
    try:
        db = SessionLocal(); db.execute(text("SELECT 1")); db_ok = True
    except Exception: db_ok = False
    finally:
        try: db.close()
        except: pass
    return {
        "db": "ok" if db_ok else "down",
        "mqtt_connected": getattr(mqtt_client, "_connected", False),
        "opcua_ingestor_running": getattr(opcua_ingestor, "_timer_ref", None) is not None
    }
