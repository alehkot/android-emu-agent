"""FastAPI server running over Unix Domain Socket."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
from hashlib import md5
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from android_emu_agent.actions.executor import ActionType, SwipeDirection
from android_emu_agent.actions.selector import (
    CoordsSelector,
    RefSelector,
    parse_selector,
)
from android_emu_agent.daemon.core import DaemonCore
from android_emu_agent.daemon.models import (
    ActionRequest,
    AppDeeplinkRequest,
    AppForceStopRequest,
    AppInstallRequest,
    AppIntentRequest,
    AppLaunchRequest,
    AppListRequest,
    AppResetRequest,
    AppResolveIntentRequest,
    ArtifactLogsRequest,
    DebugAttachRequest,
    DebugBreakpointRemoveRequest,
    DebugBreakpointSetRequest,
    DebugDetachRequest,
    DebugPingRequest,
    DeviceSettingRequest,
    DeviceTargetRequest,
    DozeRequest,
    EmulatorSnapshotRequest,
    FileAppPullRequest,
    FileAppPushRequest,
    FileFindRequest,
    FileListRequest,
    FilePullRequest,
    FilePushRequest,
    MobileRequest,
    ReliabilityBackgroundRequest,
    ReliabilityBugreportRequest,
    ReliabilityCompileRequest,
    ReliabilityDropboxListRequest,
    ReliabilityDropboxPrintRequest,
    ReliabilityDumpheapRequest,
    ReliabilityEventsRequest,
    ReliabilityExitInfoRequest,
    ReliabilityOomAdjRequest,
    ReliabilityPackageRequest,
    ReliabilityRunAsRequest,
    ReliabilitySigquitRequest,
    ReliabilityToggleRequest,
    ReliabilityTrimMemoryRequest,
    RotationRequest,
    SessionRequest,
    SessionStartRequest,
    SessionStopRequest,
    SetTextRequest,
    SnapshotRequest,
    SwipeRequest,
    WaitActivityRequest,
    WaitIdleRequest,
    WaitSelectorRequest,
    WaitTextRequest,
    WifiRequest,
)
from android_emu_agent.device.manager import Orientation
from android_emu_agent.errors import (
    AgentError,
    device_offline_error,
    not_found_error,
    session_expired_error,
    stale_ref_error,
)
from android_emu_agent.files.manager import FileMatch
from android_emu_agent.reliability.manager import DEFAULT_EVENTS_PATTERN, TRIM_LEVELS, require_root
from android_emu_agent.ui.ref_resolver import LocatorBundle
from android_emu_agent.validation import validate_package, validate_uri

logger = structlog.get_logger()

ResponsePayload = dict[str, Any]
EndpointResponse = Response | ResponsePayload


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage daemon lifecycle."""
    logger.info("daemon_starting")
    app.state.core = DaemonCore()
    await app.state.core.start()
    yield
    logger.info("daemon_stopping")
    await app.state.core.stop()


app = FastAPI(
    title="Android Emu Agent Daemon",
    version="0.1.0",
    lifespan=lifespan,
)


def _error_response(error: AgentError, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "error": error.to_dict()},
    )


def _bundle_from_dict(ref_dict: dict[str, Any], generation: int) -> LocatorBundle:
    key_parts = [
        ref_dict.get("resource_id", ""),
        ref_dict.get("class", ""),
        str(ref_dict.get("bounds", [])),
    ]
    ancestry_hash = md5("|".join(key_parts).encode()).hexdigest()[:8]
    return LocatorBundle(
        ref=ref_dict["ref"],
        generation=generation,
        resource_id=ref_dict.get("resource_id"),
        content_desc=ref_dict.get("content_desc"),
        text=ref_dict.get("text"),
        class_name=ref_dict.get("class", ""),
        bounds=ref_dict.get("bounds", [0, 0, 0, 0]),
        ancestry_hash=ancestry_hash,
        index=ref_dict.get("index", 0),
    )


def _format_file_matches(matches: list[FileMatch]) -> str:
    if not matches:
        return "No matches."
    header = "PATH\tTYPE\tSIZE\tMODE\tUID:GID\tMTIME_EPOCH"
    lines = [header]
    for match in matches:
        lines.append(
            f"{match['path']}\t{match['kind']}\t{match['size_bytes']}\t"
            f"{match['mode']}\t{match['uid']}:{match['gid']}\t{match['mtime_epoch']}"
        )
    return "\n".join(lines)


def _selector_from_locator(locator: LocatorBundle) -> dict[str, str] | None:
    if locator.resource_id:
        return {"resourceId": locator.resource_id}
    if locator.content_desc:
        return {"description": locator.content_desc}
    if locator.text:
        return {"text": locator.text}
    return None


async def _resolve_device_target(
    core: DaemonCore, session_id: str | None, serial: str | None
) -> tuple[str, Any, Any] | JSONResponse:
    if session_id:
        session = await core.session_manager.get_session(session_id)
        if not session:
            return _error_response(session_expired_error(session_id), status_code=404)
        serial = session.device_serial

    if not serial:
        return _error_response(
            AgentError(
                code="ERR_TARGET_REQUIRED",
                message="session_id or serial is required",
                context={},
                remediation="Provide --session or --device",
            ),
            status_code=400,
        )

    device = await core.device_manager.get_adb_device(serial)
    if not device:
        return _error_response(device_offline_error(serial), status_code=404)

    info = await core.device_manager.get_device(serial)
    return serial, device, info


async def _resolve_locator(
    core: DaemonCore,
    session_id: str,
    ref: str,
    current_generation: int,
) -> tuple[LocatorBundle | None, bool]:
    bundle, is_stale = core.ref_resolver.resolve_ref(session_id, ref, current_generation)
    if bundle:
        return bundle, is_stale

    stored = await core.database.get_ref_any_generation(session_id, ref)
    if stored:
        generation, ref_dict = stored
        return _bundle_from_dict(ref_dict, generation), generation < current_generation

    return None, False


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint with device status."""
    core: DaemonCore = app.state.core
    status = core.health_monitor.get_status()

    # Determine overall status
    devices = status.get("devices", {})
    all_healthy = all(d.get("adb_ok", False) and d.get("u2_ok", False) for d in devices.values())

    sessions = await core.session_manager.list_sessions()

    return {
        "status": "ok" if (all_healthy or not devices) else "degraded",
        "running": core.is_running,
        "active_sessions": len(sessions),
        "devices": devices,
    }


@app.get("/devices")
async def list_devices() -> dict[str, list[dict[str, str]]]:
    """List connected devices."""
    core: DaemonCore = app.state.core
    devices = await core.device_manager.list_devices()
    return {"devices": devices}


@app.post("/devices/animations", response_model=None)
async def set_animations(req: DeviceSettingRequest) -> EndpointResponse:
    """Enable or disable animations on a device."""
    core: DaemonCore = app.state.core
    enabled = req.state.lower() == "on"
    try:
        await core.device_manager.set_animations(req.serial, enabled)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)
    return {"status": "done", "serial": req.serial, "animations": "on" if enabled else "off"}


@app.post("/devices/stay_awake", response_model=None)
async def set_stay_awake(req: DeviceSettingRequest) -> EndpointResponse:
    """Enable or disable stay-awake on a device."""
    core: DaemonCore = app.state.core
    enabled = req.state.lower() == "on"
    try:
        await core.device_manager.set_stay_awake(req.serial, enabled)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)
    return {"status": "done", "serial": req.serial, "stay_awake": "on" if enabled else "off"}


@app.post("/devices/rotation", response_model=None)
async def set_rotation(req: RotationRequest) -> EndpointResponse:
    """Set device rotation."""
    core: DaemonCore = app.state.core

    orientation_map = {
        "portrait": Orientation.PORTRAIT,
        "landscape": Orientation.LANDSCAPE,
        "reverse-portrait": Orientation.REVERSE_PORTRAIT,
        "reverse-landscape": Orientation.REVERSE_LANDSCAPE,
        "auto": Orientation.AUTO,
    }

    orientation = orientation_map.get(req.orientation.lower())
    if not orientation:
        return _error_response(
            AgentError(
                code="ERR_INVALID_ORIENTATION",
                message=f"Invalid orientation: {req.orientation}",
                context={"orientation": req.orientation},
                remediation="Use: portrait, landscape, reverse-portrait, reverse-landscape, or auto",
            ),
            status_code=400,
        )

    try:
        await core.device_manager.set_rotation(req.serial, orientation)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)

    return {"status": "done", "serial": req.serial, "orientation": req.orientation}


@app.post("/devices/wifi", response_model=None)
async def set_wifi(req: WifiRequest) -> EndpointResponse:
    """Enable or disable WiFi."""
    core: DaemonCore = app.state.core
    try:
        await core.device_manager.set_wifi(req.serial, req.enabled)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)
    return {"status": "done", "serial": req.serial, "wifi": "on" if req.enabled else "off"}


@app.post("/devices/mobile", response_model=None)
async def set_mobile(req: MobileRequest) -> EndpointResponse:
    """Enable or disable mobile data."""
    core: DaemonCore = app.state.core
    try:
        await core.device_manager.set_mobile(req.serial, req.enabled)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)
    return {"status": "done", "serial": req.serial, "mobile": "on" if req.enabled else "off"}


@app.post("/devices/doze", response_model=None)
async def set_doze(req: DozeRequest) -> EndpointResponse:
    """Force device into or out of doze mode."""
    core: DaemonCore = app.state.core
    try:
        await core.device_manager.set_doze(req.serial, req.enabled)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)
    return {"status": "done", "serial": req.serial, "doze": "on" if req.enabled else "off"}


@app.post("/sessions/start", response_model=None)
async def session_start(req: SessionStartRequest) -> EndpointResponse:
    """Start a new session on a device."""
    core: DaemonCore = app.state.core
    await core.device_manager.refresh()
    device_info = await core.device_manager.get_device(req.device_serial)
    if not device_info:
        return _error_response(device_offline_error(req.device_serial), status_code=404)

    session = await core.session_manager.create_session(req.device_serial)
    return {
        "status": "done",
        "session_id": session.session_id,
        "device_serial": session.device_serial,
        "generation": session.generation,
    }


@app.post("/sessions/stop", response_model=None)
async def session_stop(req: SessionStopRequest) -> EndpointResponse:
    """Stop a session."""
    core: DaemonCore = app.state.core
    closed = await core.session_manager.close_session(req.session_id)
    if not closed:
        return _error_response(session_expired_error(req.session_id), status_code=404)
    core.ref_resolver.clear_session(req.session_id)
    return {"status": "done"}


@app.get("/sessions")
async def session_list() -> dict[str, Any]:
    """List active sessions."""
    core: DaemonCore = app.state.core
    sessions = await core.session_manager.list_sessions()
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "device_serial": s.device_serial,
                "generation": s.generation,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]
    }


@app.get("/sessions/{session_id}", response_model=None)
async def session_info(session_id: str) -> EndpointResponse:
    """Get session info."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(session_id)
    if not session:
        return _error_response(session_expired_error(session_id), status_code=404)
    return {
        "session_id": session.session_id,
        "device_serial": session.device_serial,
        "generation": session.generation,
        "created_at": session.created_at.isoformat(),
    }


@app.post("/ui/snapshot", response_model=None)
async def ui_snapshot(req: SnapshotRequest) -> EndpointResponse:
    """Take a UI snapshot.

    Modes:
    - compact (default): Interactive elements only, JSON format
    - full: All elements, JSON format
    - raw: Original XML hierarchy string
    """
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    adb_device = await core.device_manager.get_adb_device(session.device_serial)
    if not device or not adb_device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    # Determine if we need compressed hierarchy (compact mode only)
    use_compressed = req.mode == "compact"
    interactive_only = req.mode == "compact"

    try:
        generation = await core.session_manager.increment_generation(req.session_id)
        xml = await asyncio.to_thread(
            device.dump_hierarchy,
            compressed=use_compressed,
            pretty=False,
        )
        xml_str = xml if isinstance(xml, str) else xml.decode()
        xml_bytes = xml.encode() if isinstance(xml, str) else xml

        # For raw mode, return XML directly without parsing
        if req.mode == "raw":
            return Response(content=xml_str, media_type="application/xml")

        context = await core.context_resolver.resolve(adb_device)
        device_info = await core.device_manager.describe_device(session.device_serial)
        snapshot = core.snapshotter.parse_hierarchy(
            xml_bytes,
            session_id=req.session_id,
            generation=generation,
            device_info=device_info,
            context_info=asdict(context),
            interactive_only=interactive_only,
        )
    except Exception as exc:
        logger.exception("snapshot_failed", session_id=req.session_id)
        return _error_response(
            AgentError(
                code="ERR_SNAPSHOT_FAILED",
                message=str(exc),
                context={"session_id": req.session_id},
                remediation="Verify device is online and try again",
            ),
            status_code=500,
        )

    snapshot_dict = snapshot.to_dict()
    core.ref_resolver.store_refs(req.session_id, generation, snapshot_dict["elements"])
    await core.database.save_refs(req.session_id, generation, snapshot_dict["elements"])

    snapshot_json = json.dumps(snapshot_dict, ensure_ascii=True)
    await core.session_manager.update_snapshot(req.session_id, snapshot_dict, snapshot_json)

    return snapshot_dict


@app.post("/ui/screenshot", response_model=None)
async def ui_screenshot(req: DeviceTargetRequest) -> EndpointResponse:
    """Capture a screenshot."""
    core: DaemonCore = app.state.core
    serial = req.serial
    session_id = req.session_id
    if session_id:
        session = await core.session_manager.get_session(session_id)
        if not session:
            return _error_response(session_expired_error(session_id), status_code=404)
        serial = session.device_serial

    if not serial:
        return _error_response(
            AgentError(
                code="ERR_TARGET_REQUIRED",
                message="session_id or serial is required",
                context={},
                remediation="Provide --session or --device",
            ),
            status_code=400,
        )

    device = await core.device_manager.get_u2_device(serial)
    if not device:
        return _error_response(device_offline_error(serial), status_code=404)

    label = session_id or serial
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
    path = await core.artifact_manager.screenshot(device, safe_label)
    return {"status": "done", "serial": serial, "path": str(path)}


@app.post("/actions/tap", response_model=None)
async def action_tap(req: ActionRequest) -> EndpointResponse:
    """Tap an element.

    Supports multiple selector formats:
    - ^ref (e.g., ^a1): Use element ref from snapshot
    - text:"..." : Find by text content
    - id:resource_id : Find by resource ID
    - desc:"..." : Find by content description
    - coords:x,y : Tap at coordinates directly
    """
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    # Parse the selector
    try:
        selector = parse_selector(req.ref)
    except AgentError as e:
        return _error_response(e, status_code=400)

    # Handle different selector types
    if isinstance(selector, RefSelector):
        # Use existing ref resolution logic
        locator, is_stale = await _resolve_locator(
            core, req.session_id, selector.ref, session.generation
        )
        if not locator:
            return _error_response(not_found_error(selector.ref), status_code=404)

        if is_stale:
            # Try re-identification using resource_id (conservative approach)
            if locator.resource_id:
                element = device(resourceId=locator.resource_id)
                exists = await asyncio.to_thread(element.exists)
                if exists:
                    # Found via resource_id, proceed with warning
                    await asyncio.to_thread(element.click)
                    return {
                        "status": "done",
                        "selector": selector.ref,
                        "warning": f"Used stale ref {selector.ref}; take a new snapshot for reliable refs",
                    }
            # Could not re-identify, fail with stale ref error
            return _error_response(
                stale_ref_error(selector.ref, locator.generation, session.generation),
                status_code=409,
            )

        result = await core.action_executor.execute(device, ActionType.TAP, locator)
        return result.to_dict()

    elif isinstance(selector, CoordsSelector):
        # Direct coordinate tap without element lookup
        await asyncio.to_thread(device.click, selector.x, selector.y)
        return {"status": "done", "selector": f"coords:{selector.x},{selector.y}"}

    else:
        # TextSelector, ResourceIdSelector, DescSelector - use u2 kwargs
        kwargs = selector.to_u2_kwargs()
        element = device(**kwargs)
        exists = await asyncio.to_thread(element.exists)
        if not exists:
            return _error_response(not_found_error(req.ref), status_code=404)
        await asyncio.to_thread(element.click)
        return {"status": "done", "selector": req.ref}


@app.post("/actions/long_tap", response_model=None)
async def action_long_tap(req: ActionRequest) -> EndpointResponse:
    """Long tap an element."""
    return await _action_with_locator(req, ActionType.LONG_TAP)


@app.post("/actions/set_text", response_model=None)
async def action_set_text(req: SetTextRequest) -> EndpointResponse:
    """Set text on an element."""
    return await _action_with_locator(req, ActionType.SET_TEXT, text=req.text)


@app.post("/actions/clear", response_model=None)
async def action_clear(req: ActionRequest) -> EndpointResponse:
    """Clear text on an element."""
    return await _action_with_locator(req, ActionType.CLEAR)


@app.post("/actions/back", response_model=None)
async def action_back(req: SessionRequest) -> EndpointResponse:
    """Press back button."""
    return await _action_simple(req, ActionType.BACK)


@app.post("/actions/home", response_model=None)
async def action_home(req: SessionRequest) -> EndpointResponse:
    """Press home button."""
    return await _action_simple(req, ActionType.HOME)


@app.post("/actions/recents", response_model=None)
async def action_recents(req: SessionRequest) -> EndpointResponse:
    """Press recents button."""
    return await _action_simple(req, ActionType.RECENTS)


async def _action_simple(req: SessionRequest, action: ActionType) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    result = await core.action_executor.execute(device, action)
    return result.to_dict()


async def _action_with_locator(
    req: ActionRequest | SetTextRequest,
    action: ActionType,
    **kwargs: Any,
) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    locator, is_stale = await _resolve_locator(core, req.session_id, req.ref, session.generation)
    if not locator:
        return _error_response(not_found_error(req.ref), status_code=404)
    if is_stale:
        return _error_response(
            stale_ref_error(req.ref, locator.generation, session.generation),
            status_code=409,
        )

    result = await core.action_executor.execute(device, action, locator, **kwargs)
    return result.to_dict()


@app.post("/wait/idle", response_model=None)
async def wait_idle(req: WaitIdleRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    timeout = (req.timeout_ms or 0) / 1000 if req.timeout_ms else None
    result = await core.wait_engine.wait_idle(device, timeout=timeout)
    return result.to_dict()


@app.post("/wait/activity", response_model=None)
async def wait_activity(req: WaitActivityRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    timeout = (req.timeout_ms or 0) / 1000 if req.timeout_ms else None
    result = await core.wait_engine.wait_activity(device, req.activity, timeout=timeout)
    return result.to_dict()


@app.post("/wait/text", response_model=None)
async def wait_text(req: WaitTextRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    timeout = (req.timeout_ms or 0) / 1000 if req.timeout_ms else None
    result = await core.wait_engine.wait_text(device, req.text, timeout=timeout)
    return result.to_dict()


@app.post("/wait/exists", response_model=None)
async def wait_exists(req: WaitSelectorRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    selector = req.selector
    if req.ref:
        locator, is_stale = await _resolve_locator(
            core, req.session_id, req.ref, session.generation
        )
        if not locator:
            return _error_response(not_found_error(req.ref), status_code=404)
        if is_stale:
            return _error_response(
                stale_ref_error(req.ref, locator.generation, session.generation),
                status_code=409,
            )
        selector = _selector_from_locator(locator)

    if not selector:
        return _error_response(
            AgentError(
                code="ERR_SELECTOR_REQUIRED",
                message="wait exists requires a selector or ^ref",
                context={"session_id": req.session_id},
                remediation="Provide --ref or a selector dict",
            ),
            status_code=400,
        )

    timeout = (req.timeout_ms or 0) / 1000 if req.timeout_ms else None
    result = await core.wait_engine.wait_exists(device, selector, timeout=timeout)
    return result.to_dict()


@app.post("/wait/gone", response_model=None)
async def wait_gone(req: WaitSelectorRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    selector = req.selector
    if req.ref:
        locator, is_stale = await _resolve_locator(
            core, req.session_id, req.ref, session.generation
        )
        if not locator:
            return _error_response(not_found_error(req.ref), status_code=404)
        if is_stale:
            return _error_response(
                stale_ref_error(req.ref, locator.generation, session.generation),
                status_code=409,
            )
        selector = _selector_from_locator(locator)

    if not selector:
        return _error_response(
            AgentError(
                code="ERR_SELECTOR_REQUIRED",
                message="wait gone requires a selector or ^ref",
                context={"session_id": req.session_id},
                remediation="Provide --ref or a selector dict",
            ),
            status_code=400,
        )

    timeout = (req.timeout_ms or 0) / 1000 if req.timeout_ms else None
    result = await core.wait_engine.wait_gone(device, selector, timeout=timeout)
    return result.to_dict()


@app.post("/artifacts/save_snapshot", response_model=None)
async def save_snapshot(req: SessionRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    snapshot_json = await core.session_manager.get_last_snapshot_json(req.session_id)
    if not snapshot_json:
        return _error_response(
            AgentError(
                code="ERR_NO_SNAPSHOT",
                message="No snapshot available for this session",
                context={"session_id": req.session_id},
                remediation="Run 'ui snapshot' first",
            ),
            status_code=400,
        )

    path = await core.artifact_manager.save_snapshot(
        snapshot_json, req.session_id, session.generation
    )
    return {"status": "done", "path": str(path)}


@app.post("/artifacts/logs", response_model=None)
async def pull_logs(req: ArtifactLogsRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    if req.package:
        try:
            validate_package(req.package)
        except AgentError as exc:
            return _error_response(exc, status_code=400)

    if req.level and req.level.strip().lower() not in {
        "v",
        "verbose",
        "d",
        "debug",
        "i",
        "info",
        "w",
        "warn",
        "warning",
        "e",
        "error",
        "f",
        "fatal",
        "s",
        "silent",
    }:
        return _error_response(
            AgentError(
                code="ERR_INVALID_LOG_LEVEL",
                message=f"Invalid log level: {req.level}",
                context={"level": req.level},
                remediation="Use one of: v,d,i,w,e,f,s or verbose/debug/info/warn/error/fatal/silent",
            ),
            status_code=400,
        )

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    path = await core.artifact_manager.pull_logs(
        device,
        req.session_id,
        package=req.package,
        level=req.level,
        since=req.since,
        follow=req.follow,
    )
    return {"status": "done", "path": str(path)}


@app.post("/artifacts/debug_bundle", response_model=None)
async def debug_bundle(req: SessionRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    snapshot_json = await core.session_manager.get_last_snapshot_json(req.session_id)
    path = await core.artifact_manager.create_debug_bundle(device, req.session_id, snapshot_json)
    return {"status": "done", "path": str(path)}


# Reliability commands


@app.post("/reliability/exit_info", response_model=None)
async def reliability_exit_info(req: ReliabilityExitInfoRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.exit_info(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "output": output,
    }


@app.post("/reliability/bugreport", response_model=None)
async def reliability_bugreport(req: ReliabilityBugreportRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, _device, _info = resolved

    try:
        path = await core.reliability_manager.bugreport(serial, filename=req.filename)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "path": str(path)}


@app.post("/reliability/events", response_model=None)
async def reliability_events(req: ReliabilityEventsRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    pattern = req.pattern or DEFAULT_EVENTS_PATTERN
    try:
        result = await core.reliability_manager.logcat_events(device, pattern, req.since)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    output = result.output
    line_count = result.line_count
    if req.package:
        filtered = [line for line in output.splitlines() if req.package in line]
        output = "\n".join(filtered)
        line_count = len(filtered)

    return {
        "status": "done",
        "serial": serial,
        "pattern": pattern,
        "package": req.package,
        "line_count": line_count,
        "total_lines": result.total_lines,
        "output": output,
    }


@app.post("/reliability/dropbox_list", response_model=None)
async def reliability_dropbox_list(req: ReliabilityDropboxListRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.dropbox_list(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "output": output,
    }


@app.post("/reliability/dropbox_print", response_model=None)
async def reliability_dropbox_print(req: ReliabilityDropboxPrintRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.dropbox_print(device, req.tag)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "tag": req.tag, "output": output}


@app.post("/reliability/background", response_model=None)
async def reliability_background(req: ReliabilityBackgroundRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        data = await core.reliability_manager.background_restrictions(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    output = f"RUN_IN_BACKGROUND:\n{data['appops']}\n\nSTANDBY_BUCKET:\n{data['standby_bucket']}"
    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "appops": data["appops"],
        "standby_bucket": data["standby_bucket"],
        "output": output,
    }


@app.post("/reliability/last_anr", response_model=None)
async def reliability_last_anr(req: DeviceTargetRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.last_anr(device)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "output": output}


@app.post("/reliability/jobscheduler", response_model=None)
async def reliability_jobscheduler(req: ReliabilityPackageRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.jobscheduler(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "output": output,
    }


@app.post("/reliability/process", response_model=None)
async def reliability_process(req: ReliabilityPackageRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        data = await core.reliability_manager.process_info(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    output = (
        f"PID: {data['pid']}\n"
        f"OOM_SCORE_ADJ: {data['oom_score_adj']}\n\n"
        f"PS:\n{data['ps']}\n\n"
        f"PROCESS_STATE:\n{data['process_state']}"
    )
    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "pid": data["pid"],
        "oom_score_adj": data["oom_score_adj"],
        "ps": data["ps"],
        "process_state": data["process_state"],
        "output": output,
    }


@app.post("/reliability/meminfo", response_model=None)
async def reliability_meminfo(req: ReliabilityPackageRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.meminfo(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "package": req.package, "output": output}


@app.post("/reliability/gfxinfo", response_model=None)
async def reliability_gfxinfo(req: ReliabilityPackageRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.gfxinfo(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "package": req.package, "output": output}


@app.post("/reliability/compile", response_model=None)
async def reliability_compile(req: ReliabilityCompileRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.compile_package(device, req.package, req.mode)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "mode": req.mode,
        "output": output,
    }


@app.post("/reliability/always_finish", response_model=None)
async def reliability_always_finish(req: ReliabilityToggleRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    state = req.state.lower()
    if state not in {"on", "off"}:
        return _error_response(
            AgentError(
                code="ERR_INVALID_STATE",
                message=f"Invalid state: {req.state}",
                context={"state": req.state},
                remediation="Use 'on' or 'off'",
            ),
            status_code=400,
        )

    enabled = state == "on"
    try:
        await core.reliability_manager.always_finish_activities(device, enabled)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "enabled": enabled}


@app.post("/reliability/run_as_ls", response_model=None)
async def reliability_run_as_ls(req: ReliabilityRunAsRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.run_as_ls(device, req.package, req.path)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "path": req.path,
        "output": output,
    }


@app.post("/reliability/dumpheap", response_model=None)
async def reliability_dumpheap(req: ReliabilityDumpheapRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        path = await core.reliability_manager.dump_heap(
            device, serial, req.package, keep_remote=req.keep_remote
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "path": str(path),
    }


@app.post("/reliability/sigquit", response_model=None)
async def reliability_sigquit(req: ReliabilitySigquitRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        pid = await core.reliability_manager.sigquit(device, req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "package": req.package, "pid": pid}


@app.post("/reliability/oom_adj", response_model=None)
async def reliability_oom_adj(req: ReliabilityOomAdjRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "set oom_score_adj")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        pid = await core.reliability_manager.oom_score_adj(device, req.package, req.score)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "pid": pid,
        "score": req.score,
    }


@app.post("/reliability/trim_memory", response_model=None)
async def reliability_trim_memory(req: ReliabilityTrimMemoryRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    if req.level not in TRIM_LEVELS:
        return _error_response(
            AgentError(
                code="ERR_INVALID_LEVEL",
                message=f"Invalid trim level: {req.level}",
                context={"level": req.level},
                remediation=f"Choose one of: {', '.join(sorted(TRIM_LEVELS))}",
            ),
            status_code=400,
        )

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, _info = resolved

    try:
        output = await core.reliability_manager.trim_memory(device, req.package, req.level)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "level": req.level,
        "output": output,
    }


@app.post("/reliability/pull_anr", response_model=None)
async def reliability_pull_anr(req: DeviceTargetRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "pull /data/anr")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        path = await core.reliability_manager.pull_root_dir(device, serial, "/data/anr", "anr")
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "path": str(path)}


@app.post("/reliability/pull_tombstones", response_model=None)
async def reliability_pull_tombstones(req: DeviceTargetRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "pull /data/tombstones")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        path = await core.reliability_manager.pull_root_dir(
            device, serial, "/data/tombstones", "tombstones"
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "path": str(path)}


@app.post("/reliability/pull_dropbox", response_model=None)
async def reliability_pull_dropbox(req: DeviceTargetRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "pull /data/system/dropbox")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        path = await core.reliability_manager.pull_root_dir(
            device, serial, "/data/system/dropbox", "dropbox"
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "path": str(path)}


@app.post("/files/push", response_model=None)
async def files_push(req: FilePushRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, _device, _info = resolved

    try:
        remote = await core.file_manager.push(serial, req.local_path, req.remote_path)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "remote": remote, "path": remote}


@app.post("/files/pull", response_model=None)
async def files_pull(req: FilePullRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, _device, _info = resolved

    try:
        path = await core.file_manager.pull(serial, req.remote_path, req.local_path)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "serial": serial, "remote": req.remote_path, "path": str(path)}


@app.post("/files/app_push", response_model=None)
async def files_app_push(req: FileAppPushRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "push app data")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        remote = await core.file_manager.app_push(
            device, serial, req.package, req.local_path, req.remote_path
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "remote": remote,
        "path": remote,
    }


@app.post("/files/app_pull", response_model=None)
async def files_app_pull(req: FileAppPullRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "pull app data")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        path = await core.file_manager.app_pull(
            device, serial, req.package, req.remote_path, req.local_path
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "package": req.package,
        "remote": req.remote_path,
        "path": str(path),
    }


@app.post("/files/find", response_model=None)
async def files_find(req: FileFindRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "find files")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        matches = await core.file_manager.find_metadata(
            device, req.path, req.name, req.kind, req.max_depth
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "path": req.path,
        "name": req.name,
        "kind": req.kind,
        "max_depth": req.max_depth,
        "count": len(matches),
        "results": matches,
        "output": _format_file_matches(matches),
    }


@app.post("/files/list", response_model=None)
async def files_list(req: FileListRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, device, info = resolved

    try:
        require_root(bool(info and info.is_rooted), "list files")
    except AgentError as exc:
        return _error_response(exc, status_code=403)

    try:
        matches = await core.file_manager.list_metadata(device, req.path, req.kind)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {
        "status": "done",
        "serial": serial,
        "path": req.path,
        "kind": req.kind,
        "count": len(matches),
        "results": matches,
        "output": _format_file_matches(matches),
    }


@app.post("/app/current", response_model=None)
async def app_current(req: SessionRequest) -> EndpointResponse:
    """Get current foreground app/activity."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        data = await core.device_manager.app_current(session.device_serial)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    output = data.get("line") or "No foreground activity found."
    return {
        "status": "done",
        "session_id": req.session_id,
        "package": data.get("package"),
        "activity": data.get("activity"),
        "component": data.get("component"),
        "line": data.get("line"),
        "output": output,
    }


@app.post("/app/task_stack", response_model=None)
async def app_task_stack(req: SessionRequest) -> EndpointResponse:
    """Get activity task stack."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        output = await core.device_manager.app_task_stack(session.device_serial)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {"status": "done", "session_id": req.session_id, "output": output}


@app.post("/app/resolve_intent", response_model=None)
async def app_resolve_intent(req: AppResolveIntentRequest) -> EndpointResponse:
    """Resolve an intent target without launching it."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    if req.data_uri:
        try:
            validate_uri(req.data_uri)
        except AgentError as e:
            return _error_response(e, status_code=400)

    try:
        result = await core.device_manager.app_resolve_intent(
            session.device_serial,
            action=req.action,
            data_uri=req.data_uri,
            component=req.component,
            package=req.package,
        )
    except AgentError as e:
        return _error_response(e, status_code=400)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {
        "status": "done",
        "session_id": req.session_id,
        "action": req.action,
        "data_uri": req.data_uri,
        "component": req.component,
        "package": req.package,
        "resolved_component": result.component,
        "resolved": result.component is not None,
        "output": result.output,
    }


@app.post("/app/list", response_model=None)
async def app_list(req: AppListRequest) -> EndpointResponse:
    """List installed packages."""
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, _, _ = resolved

    scope_raw = req.scope.strip().lower()
    scope_map = {
        "all": "all",
        "system": "system",
        "third-party": "third-party",
        "third_party": "third-party",
        "thirdparty": "third-party",
        "user": "third-party",
    }
    scope = scope_map.get(scope_raw)
    if not scope:
        return _error_response(
            AgentError(
                code="ERR_INVALID_PACKAGE_SCOPE",
                message=f"Invalid package scope: {req.scope}",
                context={"scope": req.scope},
                remediation="Use: all, system, or third-party",
            ),
            status_code=400,
        )

    try:
        packages = await core.device_manager.list_packages(serial, scope=scope)
    except ValueError as exc:
        return _error_response(
            AgentError(
                code="ERR_INVALID_PACKAGE_SCOPE",
                message=str(exc),
                context={"scope": req.scope},
                remediation="Use: all, system, or third-party",
            ),
            status_code=400,
        )
    except Exception:
        return _error_response(device_offline_error(serial), status_code=404)

    output = "\n".join(packages) if packages else "No packages found."
    return {
        "status": "done",
        "serial": serial,
        "scope": scope,
        "count": len(packages),
        "packages": packages,
        "output": output,
    }


@app.post("/app/install", response_model=None)
async def app_install(req: AppInstallRequest) -> EndpointResponse:
    """Install an APK on a device."""
    core: DaemonCore = app.state.core
    resolved = await _resolve_device_target(core, req.session_id, req.serial)
    if isinstance(resolved, JSONResponse):
        return resolved
    serial, _, _ = resolved

    try:
        output = await core.device_manager.app_install(
            serial,
            req.apk_path,
            replace=req.replace,
            grant_permissions=req.grant_permissions,
            allow_downgrade=req.allow_downgrade,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)
    except Exception:
        return _error_response(device_offline_error(serial), status_code=404)

    return {
        "status": "done",
        "serial": serial,
        "apk_path": req.apk_path,
        "replace": req.replace,
        "grant_permissions": req.grant_permissions,
        "allow_downgrade": req.allow_downgrade,
        "output": output,
    }


@app.post("/app/reset", response_model=None)
async def app_reset(req: AppResetRequest) -> EndpointResponse:
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        await core.device_manager.app_reset(session.device_serial, req.package)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {"status": "done", "package": req.package}


@app.post("/app/launch", response_model=None)
async def app_launch(req: AppLaunchRequest) -> EndpointResponse:
    """Launch an app."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        validate_package(req.package)
    except AgentError as e:
        return _error_response(e, status_code=400)

    try:
        activity = await core.device_manager.app_launch(
            session.device_serial,
            req.package,
            req.activity,
            wait_for_debugger=req.wait_debugger,
        )
    except Exception as e:
        return _error_response(
            AgentError(
                code="ERR_LAUNCH_FAILED",
                message=str(e),
                context={"package": req.package},
                remediation="Verify package is installed and has a launchable activity",
            ),
            status_code=500,
        )

    return {
        "status": "done",
        "package": req.package,
        "activity": activity,
        "wait_debugger": req.wait_debugger,
    }


@app.post("/app/force_stop", response_model=None)
async def app_force_stop(req: AppForceStopRequest) -> EndpointResponse:
    """Force stop an app."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        validate_package(req.package)
    except AgentError as e:
        return _error_response(e, status_code=400)

    try:
        await core.device_manager.app_force_stop(session.device_serial, req.package)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {"status": "done", "package": req.package}


@app.post("/app/deeplink", response_model=None)
async def app_deeplink(req: AppDeeplinkRequest) -> EndpointResponse:
    """Open a deeplink URI."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        validate_uri(req.uri)
    except AgentError as e:
        return _error_response(e, status_code=400)

    try:
        await core.device_manager.app_deeplink(
            session.device_serial, req.uri, wait_for_debugger=req.wait_debugger
        )
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {"status": "done", "uri": req.uri, "wait_debugger": req.wait_debugger}


@app.post("/app/intent", response_model=None)
async def app_intent(req: AppIntentRequest) -> EndpointResponse:
    """Start an explicit or implicit intent."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    if req.data_uri:
        try:
            validate_uri(req.data_uri)
        except AgentError as e:
            return _error_response(e, status_code=400)

    try:
        await core.device_manager.app_start_intent(
            session.device_serial,
            action=req.action,
            data_uri=req.data_uri,
            component=req.component,
            package=req.package,
            wait_for_debugger=req.wait_debugger,
        )
    except AgentError as e:
        return _error_response(e, status_code=400)
    except Exception:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    return {
        "status": "done",
        "action": req.action,
        "data_uri": req.data_uri,
        "component": req.component,
        "package": req.package,
        "wait_debugger": req.wait_debugger,
    }


@app.post("/emulator/snapshot_save", response_model=None)
async def emulator_snapshot_save(req: EmulatorSnapshotRequest) -> EndpointResponse:
    """Save emulator snapshot."""
    core: DaemonCore = app.state.core
    try:
        await core.device_manager.emulator_snapshot_save(req.serial, req.name)
    except AgentError as e:
        return _error_response(e, status_code=400)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)

    return {"status": "done", "serial": req.serial, "snapshot": req.name}


@app.post("/emulator/snapshot_restore", response_model=None)
async def emulator_snapshot_restore(req: EmulatorSnapshotRequest) -> EndpointResponse:
    """Restore emulator snapshot."""
    core: DaemonCore = app.state.core
    try:
        await core.device_manager.emulator_snapshot_restore(req.serial, req.name)
    except AgentError as e:
        return _error_response(e, status_code=400)
    except Exception:
        return _error_response(device_offline_error(req.serial), status_code=404)

    return {"status": "done", "serial": req.serial, "snapshot": req.name}


# Debug commands


@app.post("/debug/ping", response_model=None)
async def debug_ping(req: DebugPingRequest) -> EndpointResponse:
    """Ping the JDI Bridge to verify it starts and responds."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        result = await core.debug_manager.ping(req.session_id)
    except AgentError as exc:
        return _error_response(exc, status_code=500)

    return {"status": "done", "session_id": req.session_id, "bridge": result}


@app.post("/debug/attach", response_model=None)
async def debug_attach(req: DebugAttachRequest) -> EndpointResponse:
    """Attach the debugger to a running app's JVM via JDWP."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    try:
        validate_package(req.package)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    adb_device = await core.device_manager.get_adb_device(session.device_serial)
    if not adb_device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    try:
        result = await core.debug_manager.attach(
            session_id=req.session_id,
            device_serial=session.device_serial,
            package=req.package,
            adb_device=adb_device,
            process_name=req.process,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", **result}


@app.post("/debug/detach", response_model=None)
async def debug_detach(req: DebugDetachRequest) -> EndpointResponse:
    """Detach the debugger from a session."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    adb_device = await core.device_manager.get_adb_device(session.device_serial)
    if not adb_device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    try:
        result = await core.debug_manager.detach(
            session_id=req.session_id,
            adb_device=adb_device,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", **result}


@app.get("/debug/status/{session_id}", response_model=None)
async def debug_status(session_id: str) -> EndpointResponse:
    """Get the debug session status."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(session_id)
    if not session:
        return _error_response(session_expired_error(session_id), status_code=404)

    result = await core.debug_manager.status(session_id)
    return {"status": "done", **result}


@app.get("/debug/status", response_model=None)
async def debug_status_query(session_id: str) -> EndpointResponse:
    """Get debug status using query string style: /debug/status?session_id=..."""
    return await debug_status(session_id)


@app.post("/debug/breakpoint/set", response_model=None)
async def debug_breakpoint_set(req: DebugBreakpointSetRequest) -> EndpointResponse:
    """Set a debugger breakpoint by class pattern and source line."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    if req.line <= 0:
        return _error_response(
            AgentError(
                code="ERR_INVALID_LINE",
                message=f"Invalid line number: {req.line}",
                context={"line": req.line},
                remediation="Use a positive 1-based source line.",
            ),
            status_code=400,
        )

    try:
        result = await core.debug_manager.set_breakpoint(
            session_id=req.session_id,
            class_pattern=req.class_pattern,
            line=req.line,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", **result}


@app.post("/debug/breakpoint/remove", response_model=None)
async def debug_breakpoint_remove(req: DebugBreakpointRemoveRequest) -> EndpointResponse:
    """Remove a debugger breakpoint by ID."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    if req.breakpoint_id <= 0:
        return _error_response(
            AgentError(
                code="ERR_INVALID_BREAKPOINT_ID",
                message=f"Invalid breakpoint id: {req.breakpoint_id}",
                context={"breakpoint_id": req.breakpoint_id},
                remediation="Use a positive breakpoint id from 'debug break list'.",
            ),
            status_code=400,
        )

    try:
        result = await core.debug_manager.remove_breakpoint(
            session_id=req.session_id,
            breakpoint_id=req.breakpoint_id,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", **result}


@app.get("/debug/breakpoints", response_model=None)
async def debug_breakpoint_list(session_id: str) -> EndpointResponse:
    """List active debugger breakpoints for a session."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(session_id)
    if not session:
        return _error_response(session_expired_error(session_id), status_code=404)

    try:
        result = await core.debug_manager.list_breakpoints(session_id)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "session_id": session_id, **result}


@app.get("/debug/threads", response_model=None)
async def debug_threads(
    session_id: str,
    include_daemon: bool = False,
    max_threads: int | None = None,
) -> EndpointResponse:
    """List debugger-visible VM threads with bounded output."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(session_id)
    if not session:
        return _error_response(session_expired_error(session_id), status_code=404)

    resolved_max_threads = (
        max_threads if max_threads is not None else (100 if include_daemon else 20)
    )
    if resolved_max_threads <= 0:
        return _error_response(
            AgentError(
                code="ERR_INVALID_MAX_THREADS",
                message=f"Invalid max_threads: {resolved_max_threads}",
                context={"max_threads": resolved_max_threads},
                remediation="Use a positive max_threads value.",
            ),
            status_code=400,
        )

    try:
        result = await core.debug_manager.list_threads(
            session_id,
            include_daemon=include_daemon,
            max_threads=resolved_max_threads,
        )
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", "session_id": session_id, **result}


@app.get("/debug/events", response_model=None)
async def debug_events(session_id: str) -> EndpointResponse:
    """Drain and return queued debugger events for a session."""
    core: DaemonCore = app.state.core
    session = await core.session_manager.get_session(session_id)
    if not session:
        return _error_response(session_expired_error(session_id), status_code=404)

    try:
        result = await core.debug_manager.drain_events(session_id)
    except AgentError as exc:
        return _error_response(exc, status_code=400)

    return {"status": "done", **result}


@app.post("/actions/swipe", response_model=None)
async def action_swipe(req: SwipeRequest) -> EndpointResponse:
    """Perform swipe action."""
    core: DaemonCore = app.state.core

    try:
        direction = SwipeDirection(req.direction)
    except ValueError:
        return {
            "status": "error",
            "error": {
                "code": "ERR_INVALID_DIRECTION",
                "message": f"Invalid direction: {req.direction}",
                "remediation": "Use up, down, left, or right",
            },
        }

    session = await core.session_manager.get_session(req.session_id)
    if not session:
        return _error_response(session_expired_error(req.session_id), status_code=404)

    device = await core.device_manager.get_u2_device(session.device_serial)
    if not device:
        return _error_response(device_offline_error(session.device_serial), status_code=404)

    # Get bounds (full screen if no container)
    info = await asyncio.to_thread(lambda: device.info)
    bounds = [0, 0, info["displayWidth"], info["displayHeight"]]

    start, end = core.action_executor._calculate_swipe_coords(bounds, direction, req.distance)

    await asyncio.to_thread(
        device.swipe, start[0], start[1], end[0], end[1], req.duration_ms / 1000
    )

    return {"status": "done", "direction": req.direction}
