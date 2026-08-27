from agent.vehicle_agent.profile_decoder import VehicleProfileDecoder
from agent.vehicle_agent.providers.obdlink import AdapterError, OBDLinkSXAdapter


class RawCANProfileProvider:
    """Read-only raw CAN monitor backed by a declarative vehicle profile."""

    def __init__(
        self,
        adapter: OBDLinkSXAdapter,
        decoder: VehicleProfileDecoder,
        window_seconds: float = 1.0,
    ):
        self.adapter = adapter
        self.decoder = decoder
        self.window_seconds = window_seconds
        self.connected = False
        self.metrics: dict[str, object] = {}

    def read_metrics(self) -> dict[str, object]:
        if not self.connected:
            try:
                self.adapter.connect()
                self.adapter.select_protocol("6")
                self.connected = True
            except (AdapterError, OSError):
                return dict(self.metrics)
        try:
            for frame in self.adapter.monitor(self.window_seconds):
                decoded = self.decoder.decode(frame, self.metrics)
                self.metrics.update({signal.name: signal.value for signal in decoded})
        except (AdapterError, OSError):
            self.adapter.close()
            self.connected = False
        return dict(self.metrics)
