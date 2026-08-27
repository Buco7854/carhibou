from dataclasses import dataclass


@dataclass(frozen=True)
class CadenceDefaults:
    sampling_seconds: int
    upload_seconds: int
    parked_sampling_seconds: int
    parked_upload_seconds: int


STANDARD_CADENCE = CadenceDefaults(
    sampling_seconds=5,
    upload_seconds=5,
    parked_sampling_seconds=300,
    parked_upload_seconds=300,
)
MINIMUM_CADENCE_SECONDS = 1
MAXIMUM_CADENCE_SECONDS = 86400
