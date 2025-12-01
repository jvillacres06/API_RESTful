import json
import ssl
import logging
import paho.mqtt.client as mqtt
from .config import settings

logger = logging.getLogger("mqtt")

class MQTTClient:
    def __init__(self):
        self.client = mqtt.Client(settings.MQTT_CLIENT_ID)
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        # TLS 
        if settings.MQTT_TLS_ENABLED:
            self.client.tls_set(
                ca_certs=settings.MQTT_TLS_CA or None,
                certfile=settings.MQTT_TLS_CERT or None,
                keyfile=settings.MQTT_TLS_KEY or None,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
            self.client.tls_insecure_set(False)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._connected = False

        # LWT (Last Will and Testament)
        self.client.will_set("tesis/api/status", payload="offline", qos=1, retain=False)

    def connect(self):
        try:
            # connect_async
            self.client.connect_async(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            self.client.loop_start() 
        except Exception as e:
            logger.exception("MQTT connect error: %s", e)

    def _on_connect(self, client, userdata, flags, rc):
        logger.info(f"MQTT connected (rc={rc})")
        self._connected = True
        try:
            self.publish("tesis/api/status", "online", qos=1)
        except Exception:
            pass

    def _on_disconnect(self, client, userdata, rc):
        logger.info("MQTT disconnected")
        self._connected = False

    def disconnect(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            logger.exception("MQTT disconnect error: %s", e)

    def publish(self, topic: str, payload, qos: int | None = None, retain=False) -> bool:
        if not isinstance(payload, str):
            payload = json.dumps(payload, default=str)
        try:
            _qos = settings.MQTT_QOS if qos is None else qos
            rc, mid = self.client.publish(topic, payload, qos=_qos, retain=retain)
            return rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.exception("MQTT publish error: %s", e)
            return False

# instancia compartida
mqtt_client = MQTTClient()