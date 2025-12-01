from fastapi import APIRouter, HTTPException, Query
from ..config import settings
from ..services.opcua_service import OPCUAService
from ..services.opcua_ingestor import start_ingestor, stop_ingestor
from pydantic import BaseModel
from ..mqtt_client import mqtt_client


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


# Modelo de datos para la solicitud
class OPCUAWriteRequest(BaseModel):
    node_id: str
    valor: str # Siempre se manda como string para simplificar el transporte

@router.post("/write")
def opcua_write(payload: OPCUAWriteRequest):
    """Publica un comando de escritura en MQTT para su ejecución asíncrona."""
    topic = "tesis/cmd/opcua/write"
    
    success = mqtt_client.publish(
        topic=topic,
        payload=payload.dict(),
        qos=1 # Se recomienda QOS=1 para comandos para asegurar la entrega
    )
    
    if not success:
        raise HTTPException(503, "Broker MQTT no disponible. Comando no enviado.")
        
    return {
        "status": "Comando publicado en MQTT para ejecución asíncrona",
        "node_id": payload.node_id, 
        "valor": payload.valor
    }
