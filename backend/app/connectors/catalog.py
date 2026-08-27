from backend.app.connectors.schemas import ConnectorKindResponse

CONNECTOR_KINDS = (
    ConnectorKindResponse(
        id="teslamate.mqtt",
        name="TeslaMate (MQTT)",
        description="Receive TeslaMate telemetry from an MQTT broker.",
        docs_url="https://docs.teslamate.org/docs/integrations/mqtt/",
    ),
)
