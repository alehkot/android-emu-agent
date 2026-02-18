"""Pydantic request models for debugger endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DebugPingRequest(BaseModel):
    session_id: str


class DebugAttachRequest(BaseModel):
    session_id: str
    package: str
    process: str | None = None


class DebugDetachRequest(BaseModel):
    session_id: str


class DebugStatusRequest(BaseModel):
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


class DebugExceptionBreakpointSetRequest(BaseModel):
    session_id: str
    class_pattern: str = "*"
    caught: bool = True
    uncaught: bool = True


class DebugExceptionBreakpointRemoveRequest(BaseModel):
    session_id: str
    breakpoint_id: int
