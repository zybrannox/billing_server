from datetime import datetime, timezone
from typing import Annotated, Optional
from pydantic import PlainSerializer


def _as_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    # Every DateTime column in this app is naive (no timezone=True), but
    # every value written to one is a UTC wall-clock reading -
    # datetime.utcnow() on the backend, or a frontend .toISOString() value
    # that loses its "Z" the moment SQLAlchemy stores it in a naive column.
    # Serializing that naive value as-is produces an ISO string with no UTC
    # marker, which browsers interpret as *local* time - stamping UTC back
    # on here is what makes the API's JSON unambiguous again.
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


UTCDateTime = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]
OptionalUTCDateTime = Annotated[
    Optional[datetime], PlainSerializer(_as_utc_iso, return_type=Optional[str])
]
