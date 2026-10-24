"""Pydantic request models for daemon endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, StrictBool, model_validator


class RequestModel(PydanticBaseModel):
    """Base model that rejects misspelled or unsupported request fields."""

    model_config = ConfigDict(extra="forbid")


class SessionStartRequest(RequestModel):
    device_serial: str


class SessionStopRequest(RequestModel):
    session_id: str


class SnapshotRequest(RequestModel):
    session_id: str
    mode: Literal["compact", "full", "raw"] = "compact"
    full: bool = False  # Deprecated: kept for backward compatibility

    @model_validator(mode="after")
    def migrate_full_to_mode(self) -> SnapshotRequest:
        """Migrate legacy 'full' field to 'mode' field.

        If 'full=True' is set and mode is still the default 'compact',
        upgrade mode to 'full' for backward compatibility.
        """
        if self.full and self.mode == "compact":
            object.__setattr__(self, "mode", "full")
        return self


class SessionRequest(RequestModel):
    session_id: str


class VisualGroundingRequest(RequestModel):
    session_id: str
    refs: list[str] | None = None
    screenshot: bool = True


class TraceStartRequest(RequestModel):
    session_id: str
    label: str | None = None


class TraceStopRequest(RequestModel):
    session_id: str
    output_path: str | None = None


class TraceReplayRequest(RequestModel):
    path: str
    until_failure: bool = False


class TraceExportRequest(RequestModel):
    path: str
    output_path: str | None = None
    format: str = "markdown"


class TaskValidateRequest(RequestModel):
    task: dict[str, Any]


class TaskScriptValidateRequest(RequestModel):
    script: str
    source_name: str = "<script>"


class TaskRunRequest(RequestModel):
    session_id: str
    task: dict[str, Any]
    stop_on_failure: bool = True


class TaskScriptRunRequest(RequestModel):
    session_id: str
    script: str
    source_name: str = "<script>"
    stop_on_failure: bool = True


class ExpectIdleRequest(RequestModel):
    session_id: str
    timeout_ms: int | None = None


class ExpectTextRequest(RequestModel):
    session_id: str
    text: str
    timeout_ms: int | None = None


class ExpectActivityRequest(RequestModel):
    session_id: str
    activity: str
    timeout_ms: int | None = None


class ExpectSelectorRequest(RequestModel):
    session_id: str
    ref: str | None = None
    selector: dict[str, str | StrictBool] | None = None
    timeout_ms: int | None = None


class ExpectCurrentAppRequest(RequestModel):
    session_id: str
    package: str | None = None
    activity: str | None = None


class ActionRequest(RequestModel):
    session_id: str
    ref: str  # Can be ^ref, text:"...", id:..., desc:"...", or coords:x,y


class SetTextRequest(RequestModel):
    session_id: str
    ref: str
    text: str


class WaitIdleRequest(RequestModel):
    session_id: str
    timeout_ms: int | None = None


class WaitActivityRequest(RequestModel):
    session_id: str
    activity: str
    timeout_ms: int | None = None


class WaitTextRequest(RequestModel):
    session_id: str
    text: str
    timeout_ms: int | None = None


class WaitSelectorRequest(RequestModel):
    session_id: str
    ref: str | None = None
    selector: dict[str, str | StrictBool] | None = None
    timeout_ms: int | None = None


class DeviceSettingRequest(RequestModel):
    serial: str
    state: str


class AppResetRequest(RequestModel):
    session_id: str
    package: str


class RotationRequest(RequestModel):
    serial: str
    orientation: str  # portrait, landscape, reverse-portrait, reverse-landscape, auto


class WifiRequest(RequestModel):
    serial: str
    enabled: bool


class MobileRequest(RequestModel):
    serial: str
    enabled: bool


class DozeRequest(RequestModel):
    serial: str
    enabled: bool


class AppLaunchRequest(RequestModel):
    session_id: str
    package: str
    activity: str | None = None
    wait_debugger: bool = False


class AppForceStopRequest(RequestModel):
    session_id: str
    package: str


class AppDeeplinkRequest(RequestModel):
    session_id: str
    uri: str
    wait_debugger: bool = False


class AppIntentRequest(RequestModel):
    session_id: str
    action: str | None = None
    data_uri: str | None = None
    component: str | None = None
    package: str | None = None
    wait_debugger: bool = False

    @model_validator(mode="after")
    def validate_intent_target(self) -> AppIntentRequest:
        if not any((self.action, self.data_uri, self.component, self.package)):
            raise ValueError("Provide at least one of action, data_uri, component, or package")
        return self


class AppResolveIntentRequest(RequestModel):
    session_id: str
    action: str | None = None
    data_uri: str | None = None
    component: str | None = None
    package: str | None = None

    @model_validator(mode="after")
    def validate_intent_target(self) -> AppResolveIntentRequest:
        if not any((self.action, self.data_uri, self.component, self.package)):
            raise ValueError("Provide at least one of action, data_uri, component, or package")
        return self


class EmulatorSnapshotRequest(RequestModel):
    serial: str
    name: str


class EmulatorSnapshotRestoreRequest(EmulatorSnapshotRequest):
    restart: bool = True


class EmulatorStartRequest(RequestModel):
    avd_name: str
    snapshot: str | None = None
    wipe_data: bool = False
    cold_boot: bool = False
    no_snapshot_save: bool = False
    read_only: bool = False
    no_window: bool = False
    port: int | None = None
    wait_boot: bool = True

    @model_validator(mode="after")
    def validate_snapshot_options(self) -> EmulatorStartRequest:
        if self.snapshot and self.cold_boot:
            raise ValueError("Cannot combine snapshot and cold_boot")
        return self


class EmulatorStopRequest(RequestModel):
    serial: str


class ArtifactLogsRequest(RequestModel):
    session_id: str
    package: str | None = None
    level: str | None = None
    log_type: str | None = None
    since: str | int | None = None
    follow: bool = False


class SwipeRequest(RequestModel):
    """Request for swipe action."""

    session_id: str
    direction: str  # up, down, left, right
    container: str | None = None  # Optional ^ref or selector
    distance: float = 0.8
    duration_ms: int = 300


class DeviceTargetRequest(RequestModel):
    session_id: str | None = None
    serial: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> DeviceTargetRequest:
        if bool(self.session_id) == bool(self.serial):
            raise ValueError("Provide exactly one of session_id or serial")
        return self


class AppListRequest(DeviceTargetRequest):
    scope: str = "all"


class AppInstallRequest(DeviceTargetRequest):
    apk_path: str
    replace: bool = True
    grant_permissions: bool = False
    allow_downgrade: bool = False


class AppUninstallRequest(DeviceTargetRequest):
    package: str
    keep_data: bool = False


class SystemPermissionListRequest(DeviceTargetRequest):
    package: str


class SystemPermissionRequest(DeviceTargetRequest):
    package: str
    permission: str


class ReliabilityPackageRequest(DeviceTargetRequest):
    package: str


class ReliabilityExitInfoRequest(ReliabilityPackageRequest):
    pass


class ReliabilityEventsRequest(DeviceTargetRequest):
    pattern: str | None = None
    since: str | None = None
    package: str | None = None


class ReliabilityProfileRequest(DeviceTargetRequest):
    package: str
    since: str | None = None
    include_raw: bool = False


class ReliabilityPerfettoRequest(DeviceTargetRequest):
    duration_seconds: int = 10
    categories: str | None = None
    filename: str | None = None


class ReliabilitySimpleperfRequest(ReliabilityPackageRequest):
    duration_seconds: int = 10
    filename: str | None = None


class ReliabilityScreenrecordRequest(DeviceTargetRequest):
    duration_seconds: int = 10
    bit_rate: int | None = None
    filename: str | None = None


class ReliabilityDropboxListRequest(DeviceTargetRequest):
    package: str | None = None


class ReliabilityDropboxPrintRequest(DeviceTargetRequest):
    tag: str


class ReliabilityBugreportRequest(DeviceTargetRequest):
    filename: str | None = None


class ReliabilityBackgroundRequest(ReliabilityPackageRequest):
    pass


class ReliabilityTrimMemoryRequest(ReliabilityPackageRequest):
    level: str = "RUNNING_CRITICAL"


class ReliabilityOomAdjRequest(ReliabilityPackageRequest):
    score: int = 1000


class ReliabilityCompileRequest(ReliabilityPackageRequest):
    mode: Literal["reset", "speed"]


class ReliabilityToggleRequest(DeviceTargetRequest):
    state: str  # on|off


class ReliabilityRunAsRequest(ReliabilityPackageRequest):
    path: str = "files/"


class ReliabilityDumpheapRequest(ReliabilityPackageRequest):
    keep_remote: bool = False


class ReliabilitySigquitRequest(ReliabilityPackageRequest):
    pass


class FilePushRequest(DeviceTargetRequest):
    local_path: str
    remote_path: str | None = None


class FilePullRequest(DeviceTargetRequest):
    remote_path: str
    local_path: str | None = None


class FileAppPushRequest(DeviceTargetRequest):
    package: str
    local_path: str
    remote_path: str | None = None


class FileAppPullRequest(DeviceTargetRequest):
    package: str
    remote_path: str
    local_path: str | None = None


class FileFindRequest(DeviceTargetRequest):
    path: str
    name: str
    kind: Literal["file", "dir", "any"] = "any"
    max_depth: int = 4


class FileListRequest(DeviceTargetRequest):
    path: str
    kind: Literal["file", "dir", "any"] = "any"


class DebugPingRequest(RequestModel):
    session_id: str


class DebugAttachRequest(RequestModel):
    session_id: str
    package: str
    process: str | None = None
    keep_suspended: bool = False


class DebugDetachRequest(RequestModel):
    session_id: str


class DebugObserveRequest(RequestModel):
    session_id: str
    thread: str = "main"
    max_frames: int = 8
    include_stack: bool = True
    include_events: bool = True
    drain_events: bool = False
    event_limit: int = 20
    include_logpoints: bool = True
    logpoint_limit: int = 20
    ref_limit: int = 20


class DebugBreakpointSetRequest(RequestModel):
    session_id: str
    class_pattern: str
    line: int
    condition: str | None = None
    log_message: str | None = None
    capture_stack: bool = False
    stack_max_frames: int = 8


class DebugBreakpointRemoveRequest(RequestModel):
    session_id: str
    breakpoint_id: int


class DebugStepRequest(RequestModel):
    session_id: str
    thread: str = "main"
    timeout_seconds: float = 10.0


class DebugResumeRequest(RequestModel):
    session_id: str
    thread: str | None = None


class DebugStackRequest(RequestModel):
    session_id: str
    thread: str = "main"
    max_frames: int = 10


class DebugInspectRequest(RequestModel):
    session_id: str
    variable_path: str
    thread: str = "main"
    frame: int = 0
    depth: int = 1


class DebugEvalRequest(RequestModel):
    session_id: str
    expression: str
    thread: str = "main"
    frame: int = 0


class DebugMappingLoadRequest(RequestModel):
    session_id: str
    path: str


class DebugMappingClearRequest(RequestModel):
    session_id: str


class DebugExceptionBreakpointSetRequest(RequestModel):
    session_id: str
    class_pattern: str = "*"
    caught: bool = True
    uncaught: bool = True


class DebugExceptionBreakpointRemoveRequest(RequestModel):
    session_id: str
    breakpoint_id: int
