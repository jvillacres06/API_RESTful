import logging
from ..mqtt_client import mqtt_client

logger = logging.getLogger("mqtt_service")

def init_subscriptions():
    """Ejemplo: suscribirse a comandos MQTT."""
    def on_message(client, userdata, msg):
        logger.info(f"[MQTT] {msg.topic}: {msg.payload.decode(errors='ignore')}")
        # Aquí podrías parsear y actuar (p.ej., escribir a OPC UA o insertar en DB)

    mqtt_client.client.on_message = on_message
    mqtt_client.client.subscribe("tesis/cmd/#", qos=0)
    logger.info("Suscripción MQTT iniciada a: tesis/cmd/#")
