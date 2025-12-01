# app/services/opcua_service.py
import logging
from typing import Optional
from opcua import Client, ua

logger = logging.getLogger("opcua_service")

class OPCUAService:
    def __init__(self, endpoint: str, timeout: float = 5.0):
        self.endpoint = endpoint
        self.timeout = timeout
        self._client: Optional[Client] = None
        self._connected: bool = False

    # --- Conexión ---
    def connect(self):
        if self._connected and self._client:
            return
        try:
            c = Client(self.endpoint, timeout=self.timeout)
            # Opcional: identidades/seguridad si su servidor lo exige
            # c.set_user("user"); c.set_password("pass")
            # c.set_security_string("Basic256Sha256,SignAndEncrypt,cert.der,key.pem")
            c.application_uri = "urn:tesis:api"
            c.connect()
            self._client = c
            self._connected = True
            logger.info(f"OPCUA conectado a {self.endpoint}")
        except Exception as e:
            self._client = None
            self._connected = False
            logger.exception(f"Error conectando OPCUA: {e}")
            raise

    def disconnect(self):
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass
        finally:
            self._client = None
            self._connected = False
            logger.info("OPCUA desconectado")

    # --- Estado / salud ---
    def is_connected(self) -> bool:
        """
        Con python-opcua, la sesión existe cuando hay conexión.
        """
        try:
            return (
                self._connected
                and self._client is not None
                and getattr(self._client.uaclient, "session", None) is not None
            )
        except Exception:
            return False

    def ping(self) -> bool:
        """
        Lectura barata para validar la sesión.
        ServerStatus.CurrentTime es estándar.
        """
        if not self._client:
            raise RuntimeError("OPCUA no inicializado")
        node = self._client.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_CurrentTime))
        _ = node.get_value()  # lanza excepción si la sesión cayó
        return True

    # --- Lecturas ---
    def read_node_value(self, node_id: str):
        if not self._client:
            raise RuntimeError("OPCUA no inicializado")
        node = self._client.get_node(node_id)
        return node.get_value()

    # --- Escritura (Write-Back) ---
    def write_node_value(self, node_id: str, valor: str):
        """Escribe un valor en un nodo OPC UA."""
        if not self._client:
            raise RuntimeError("OPCUA no inicializado o desconectado.")

        try:
            node = self._client.get_node(node_id)
            
            try:
                numeric_valor = float(valor)
                node.set_value(numeric_valor)
            except ValueError:
                # Si no es numérico, intentamos escribirlo como string
                node.set_value(valor)

            logger.info(f"Escritura exitosa: Node {node_id} = {valor}")

        except Exception as e:
            logger.error(f"Fallo al escribir en OPC UA (Node {node_id}): {e}")
            raise
