"""Pydantic request models for daemon endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class SessionStartRequest(BaseModel):
    device_serial: str


class SessionStopRequest(BaseModel):
    session_id: str


class SnapshotRequest(BaseModel):
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


class SessionRequest(BaseModel):
    session_id: str


class ActionRequest(BaseModel):
    session_id: str
    ref: str  # Can be ^ref, text:"...", id:..., desc:"...", or coords:x,y


class SetTextRequest(BaseModel):
    session_id: str
    ref: str
    text: str


class WaitIdleRequest(BaseModel):
    session_id: str
    timeout_ms: int | None = None


class WaitActivityRequest(BaseModel):
    session_id: str
    activity: str
    timeout_ms: int | None = None


class WaitTextRequest(BaseModel):
    session_id: str
    text: str
    timeout_ms: int | None = None


class WaitSelectorRequest(BaseModel):
    session_id: str
    ref: str | None = None
    selector: dict[str, str] | None = None
    timeout_ms: int | None = None


class DeviceSettingRequest(BaseModel):
    serial: str
    state: str


class AppResetRequest(BaseModel):
    session_id: str
    package: str


class RotationRequest(BaseModel):
    serial: str
    orientation: str  # portrait, landscape, reverse-portrait, reverse-landscape, auto


class WifiRequest(BaseModel):
    serial: str
    enabled: bool


class MobileRequest(BaseModel):
    serial: str
    enabled: bool


class DozeRequest(BaseModel):
    serial: str
    enabled: bool


class AppLaunchRequest(BaseModel):
    session_id: str
    package: str
    activity: str | None = None
    wait_debugger: bool = False


class AppForceStopRequest(BaseModel):
    session_id: str
    package: str


class AppDeeplinkRequest(BaseModel):
    session_id: str
    uri: str
    wait_debugger: bool = False


class AppIntentRequest(BaseModel):
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


class AppResolveIntentRequest(BaseModel):
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


class EmulatorSnapshotRequest(BaseModel):
    serial: str
    name: str


class ArtifactLogsRequest(BaseModel):
    session_id: str
    package: str | None = None
    level: str | None = None
    since: str | None = None
    follow: bool = False


class SwipeRequest(BaseModel):
    """Request for swipe action."""

    session_id: str
    direction: str  # up, down, left, right
    container: str | None = None  # Optional ^ref or selector
    distance: float = 0.8
    duration_ms: int = 300


class DeviceTargetRequest(BaseModel):
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


class ReliabilityPackageRequest(DeviceTargetRequest):
    package: str


class ReliabilityExitInfoRequest(ReliabilityPackageRequest):
    pass


class ReliabilityEventsRequest(DeviceTargetRequest):
    pattern: str | None = None
    since: str | None = None
    package: str | None = None


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


class DebugPingRequest(BaseModel):
    session_id: str


class DebugAttachRequest(BaseModel):
    session_id: str
    package: str
    process: str | None = None


class DebugDetachRequest(BaseModel):
    session_id: str


class DebugBreakpointSetRequest(BaseModel):
    session_id: str
    class_pattern: str
    line: int


class DebugBreakpointRemoveRequest(BaseModel):
    session_id: str
    breakpoint_id: int


class DebugStepRequest(BaseModel):
    session_id: str
    thread: str = "main"
    timeout_seconds: float = 10.0


class DebugResumeRequest(BaseModel):
    session_id: str
    thread: str | None = None


class DebugStackRequest(BaseModel):
    session_id: str
    thread: str = "main"
    max_frames: int = 10


class DebugInspectRequest(BaseModel):
    session_id: str
    variable_path: str
    thread: str = "main"
    frame: int = 0
    depth: int = 1


class DebugEvalRequest(BaseModel):
    session_id: str
    expression: str
    thread: str = "main"
    frame: int = 0
