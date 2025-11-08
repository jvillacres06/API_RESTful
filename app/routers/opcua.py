from fastapi import APIRouter, HTTPException, Query
from ..config import settings
from ..services.opcua_service import OPCUAService
from ..services.opcua_ingestor import start_ingestor, stop_ingestor

router = APIRouter()

@router.get("/read")
def opcua_read(node_id: str = Query(...), endpoint: str | None = None):
    ep = endpoint or settings.OPCUA_ENDPOINT
    client = OPCUAService(ep)
    try:
        client.connect()
        val = client.read_node_value(node_id)
        return {"node_id": node_id, "value": val}
    except Exception as e:
        raise HTTPException(500, f"OPC UA read error: {e}")
    finally:
        client.disconnect()

@router.post("/ingestor/start")
def opcua_ingestor_start():
    start_ingestor()
    return {"status": "started", "mode": "mqtt-only"}

@router.post("/ingestor/stop")
def opcua_ingestor_stop():
    stop_ingestor()
    return {"status": "stopped"}
