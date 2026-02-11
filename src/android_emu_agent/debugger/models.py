"""Pydantic request models for debugger endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DebugPingRequest(BaseModel):
    session_id: str
