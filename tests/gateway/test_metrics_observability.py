"""Regression tests for structured gateway observability metrics."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
from tools.mcp_tool import MCPServerTask


def metric_payloads(caplog, event: str):
    payloads = []
    for record in caplog.records:
        msg = record.getMessage()
        marker = "gateway_metric "
        if marker not in msg:
            continue
        payload = json.loads(msg.split(marker, 1)[1])
        if payload.get("event") == event:
            payloads.append(payload)
    return payloads


class _DummyRequest:
    method = "POST"
    path = "/v1/chat/completions"
    path_qs = "/v1/chat/completions"
    remote = "203.0.113.9"
    transport = None

    def __init__(self, headers):
        self.headers = headers


def test_api_invalid_key_emits_structured_metric_without_token(caplog):
    caplog.set_level("INFO", logger="gateway.metrics")
    adapter = APIServerAdapter(
        PlatformConfig(enabled=True, extra={"key": "expected-secret"}),
    )
    request = _DummyRequest(
        {
            "Authorization": "Bearer wrong-secret-token",
            "User-Agent": "pytest",
            "X-Forwarded-For": "198.51.100.7",
        }
    )

    response = adapter._check_auth(request)

    assert response is not None
    payloads = metric_payloads(caplog, "api-invalid-key")
    assert payloads
    payload = payloads[-1]
    assert payload["platform"] == "api_server"
    assert payload["auth_state"] == "bearer_invalid"
    assert payload["path"] == "/v1/chat/completions"
    serialized = json.dumps(payload)
    assert "wrong-secret-token" not in serialized
    assert "expected-secret" not in serialized


@pytest.mark.asyncio
async def test_mcp_refresh_failure_metric_includes_exception_group_details(caplog, monkeypatch):
    caplog.set_level("INFO", logger="gateway.metrics")
    server = MCPServerTask("aicoven")
    server._config = {"command": "python"}
    exc = ExceptionGroup(
        "refresh failed",
        [RuntimeError("inner boom"), ValueError("bad response")],
    )
    monkeypatch.setattr(MCPServerTask, "_refresh_tools", AsyncMock(side_effect=exc))

    await server._refresh_tools_task()

    payloads = metric_payloads(caplog, "mcp-refresh-failure")
    assert payloads
    payload = payloads[-1]
    assert payload["server"] == "aicoven"
    assert payload["transport"] == "stdio"
    assert payload["exception"]["type"] == "ExceptionGroup"
    assert payload["exception"]["sub_exception_count"] == 2
    assert {sub["type"] for sub in payload["exception"]["sub_exceptions"]} == {
        "RuntimeError",
        "ValueError",
    }
