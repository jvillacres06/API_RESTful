from fastapi import FastAPI, Depends
from .routers import assets, motores, variables, unidades, despliegues, mediciones, ingestas, opcua, health, analytics, debug_config
from .mqtt_client import mqtt_client
from .security import api_key_guard
from .config import settings
from .services import opcua_ingestor
import logging

logger = logging.getLogger("uvicorn")
# (Opcional) silenciar SQL ruidoso:
# logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

app = FastAPI(title="Tesis - API Mantenimiento Predictivo")

app.include_router(unidades.router,    prefix="/api/unidades",    tags=["unidades"])
app.include_router(variables.router,   prefix="/api/variables",   tags=["variables"])
app.include_router(assets.router,      prefix="/api/assets",      tags=["assets"])
app.include_router(motores.router,     prefix="/api/motores",     tags=["motores"])
app.include_router(despliegues.router, prefix="/api/despliegues", tags=["despliegues"])
app.include_router(health.router,                              tags=["infra"])
app.include_router(ingestas.router,   prefix="/api/ingestas",   tags=["ingestas"],   dependencies=[Depends(api_key_guard)])
app.include_router(mediciones.router, prefix="/api/mediciones", tags=["mediciones"], dependencies=[Depends(api_key_guard)])
app.include_router(opcua.router,      prefix="/api/opcua",      tags=["opcua"],      dependencies=[Depends(api_key_guard)])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["analytics"])
app.include_router(debug_config.router, prefix="/api/debug",    tags=["debug"])

@app.on_event("startup")
def startup():
    logger.info("Iniciando servicio: conectando MQTT")
    mqtt_client.connect()
    # Iniciar ingestor SOLO si está habilitado
    if getattr(settings, "OPCUA_INGEST_ENABLED", False):
        opcua_ingestor.start_ingestor()

@app.on_event("shutdown")
def shutdown():
    logger.info("Deteniendo servicio: desconectando MQTT")
    mqtt_client.disconnect()
    opcua_ingestor.stop_ingestor()

@app.get("/")
def root():
    return {"status": "ok"}
