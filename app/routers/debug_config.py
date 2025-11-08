# app/routers/debug_config.py
from fastapi import APIRouter
from ..config import settings
import os
router = APIRouter()
@router.get("/debug/opcua-nodes")
def debug_nodes():
    return {"cwd": os.getcwd(),
            "raw_env": os.getenv("OPCUA_NODES_JSON"),
            "parsed": settings.opcua_nodes,
            "count": len(settings.opcua_nodes)}
