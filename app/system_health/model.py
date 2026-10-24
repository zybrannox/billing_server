from typing import Optional

from app.datetime_utils import OptionalUTCDateTime, UTCDateTime
from app.response_model import ResponseModel


class MachineRead(ResponseModel):
    memory_total_mb: float
    memory_available_mb: float
    memory_available_pct: float
    swap_used_mb: float
    cpu_cores: int
    load_per_core: float
    disk_total_gb: float
    disk_free_gb: float
    disk_free_pct: float
    uptime_hours: float


class ComponentRead(ResponseModel):
    role: str
    processes: int
    memory_mb: float
    memory_pct: float
    approximate: bool
    memory_known: bool


class OtherProcessRead(ResponseModel):
    name: str
    memory_mb: float
    memory_pct: float


class ProcessesRead(ResponseModel):
    components: list[ComponentRead]
    other_top: list[OtherProcessRead]


class PoolRead(ResponseModel):
    size: int
    in_use: int


class StorageFolderRead(ResponseModel):
    label: str
    size_mb: float
    files: int


class TableSizeRead(ResponseModel):
    name: str
    size_mb: float


class DatabaseSizeRead(ResponseModel):
    total_mb: float
    largest_tables: list[TableSizeRead]


class StorageRead(ResponseModel):
    computed_at: OptionalUTCDateTime
    refreshing: bool
    complete: bool
    folders: list[StorageFolderRead]
    database: Optional[DatabaseSizeRead]


class RouteStatRead(ResponseModel):
    route: str
    count: int
    errors: int
    avg_ms: Optional[float]
    p50_ms: Optional[float]
    p95_ms: Optional[float]


class PerformanceRead(ResponseModel):
    window_minutes: int
    requests: int
    errors: int
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    in_flight: int
    slowest_routes: list[RouteStatRead]


class SlowQueryRead(ResponseModel):
    at: UTCDateTime
    ms: int
    statement: str


class FindingRead(ResponseModel):
    severity: str
    title: str
    detail: str
    action: str


class DiagnosisRead(ResponseModel):
    verdict: str
    findings: list[FindingRead]


class SystemHealthRead(ResponseModel):
    generated_at: UTCDateTime
    machine: MachineRead
    processes: ProcessesRead
    pool: Optional[PoolRead]
    storage: StorageRead
    performance: PerformanceRead
    slow_queries: list[SlowQueryRead]
    active_uploads: int
    diagnosis: DiagnosisRead


class HealthPointRead(ResponseModel):
    at: UTCDateTime
    memory_available_pct: float
    swap_used_mb: float
    load_per_core: float
    disk_free_pct: float
    app_memory_mb: float
    requests: int
    errors: int
    p95_ms: Optional[float]
