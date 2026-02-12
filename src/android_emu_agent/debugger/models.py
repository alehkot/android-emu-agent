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
