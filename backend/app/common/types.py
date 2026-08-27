from typing import Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONValue = dict[str, Any]
JSONType = JSON().with_variant(JSONB(), "postgresql")
