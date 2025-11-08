# app/config.py
import os, json, ast
from typing import List, Dict, Any, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

import os, json, ast, pathlib
from pydantic_settings import BaseSettings, SettingsConfigDict


from dotenv import load_dotenv
BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env", override=False)


class Settings(BaseSettings):
    # --- DB ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "tproyecto1"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "12345678"

    # --- API ---
    API_PREFIX: str = "/api"
    API_KEY: Optional[str] = None

    # --- MQTT ---
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_CLIENT_ID: str = "tesis-api-client"
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_TLS_ENABLED: bool = False
    MQTT_TLS_CA: Optional[str] = None
    MQTT_TLS_CERT: Optional[str] = None
    MQTT_TLS_KEY: Optional[str] = None
    MQTT_QOS: int = 0

    # --- OPC UA ---
    OPCUA_ENDPOINT: str = "opc.tcp://localhost:4840"
    OPCUA_INGEST_INTERVAL_SEC: int = 5
    OPCUA_INGEST_PUBLISH_MQTT: bool = True

    # --- Flags ---
    OPCUA_INGEST_WRITE_RAW: bool = False
    OPCUA_INGEST_ENABLED: bool = False
    MQTT_INGEST_ENABLED: bool = False
    ALLOW_WRITE_MEDICIONES: bool = False

    # Pydantic v2
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # --- Nodos OPC UA desde .env ---
    @property
    def opcua_nodes(self) -> List[Dict[str, Any]]:
        raw = os.getenv("OPCUA_NODES_JSON", "")
        if not raw:
            return []
        # JSON válido
        try:
            return json.loads(raw)
        except Exception:
            pass
        # tolerar comillas simples -> dobles
        try:
            return json.loads(raw.replace("'", '"'))
        except Exception:
            pass
        # tolerar literal estilo Python
        try:
            v = ast.literal_eval(raw)
            return v if isinstance(v, list) else []
        except Exception:
            return []

settings = Settings()
