from app.datetime_utils import OptionalUTCDateTime
from app.response_model import ResponseModel


class BackupStatusRead(ResponseModel):
    last_backup_at: OptionalUTCDateTime = None
    last_backup_size_bytes: int | None = None
    backup_count: int
    total_size_bytes: int
    # No dump in the last day and a bit, so last night's run didn't happen.
    overdue: bool
    scheduled: bool
    # False while every copy is on the same drive as the live data.
    on_separate_disk: bool
    last_restore_check_at: OptionalUTCDateTime = None
    # Row counts differ when data changed after the dump, so this can be False
    # on a perfectly good restore.
    last_restore_check_matched: bool | None = None
    uploads_last_copied_at: OptionalUTCDateTime = None
