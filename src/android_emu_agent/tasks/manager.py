"""Task harness with verifier execution."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from android_emu_agent.errors import AgentError

TaskDispatcher = Callable[["TaskCall"], Awaitable[dict[str, Any]]]

ACTION_OPERATIONS = {"tap", "long_tap", "set_text", "clear", "back", "home", "recents", "swipe"}
WAIT_OPERATIONS = {"idle", "activity", "text", "exists", "gone"}
APP_OPERATIONS = {"launch", "force_stop", "deeplink"}
UI_OPERATIONS = {"snapshot"}
STEP_KINDS = {"action", "wait", "app", "ui"}


@dataclass(frozen=True)
class TaskCall:
    """A normalized daemon operation requested by a task step or verifier."""

    kind: str
    operation: str
    payload: dict[str, Any]
    label: str


class TaskManager:
    """Validates and runs JSON task specs through a daemon dispatcher."""

    def validate(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a task spec and return a normalized execution plan."""
        normalized = self._normalize_spec(spec)
        steps = normalized["steps"]
        verifiers = normalized["verifiers"]
        return {
            "status": "done",
            "task": self._task_metadata(normalized),
            "step_count": len(steps),
            "verifier_count": len(verifiers)
            + sum(len(step["verifiers"]) for step in steps),
            "steps": [
                {
                    "index": step["index"],
                    "name": step["name"],
                    "kind": step["kind"],
                    "operation": step["operation"],
                    "verifier_count": len(step["verifiers"]),
                }
                for step in steps
            ],
            "verifiers": [
                {
                    "index": verifier["index"],
                    "name": verifier["name"],
                    "operation": verifier["operation"],
                }
                for verifier in verifiers
            ],
        }

    async def run(
        self,
        spec: Mapping[str, Any],
        *,
        session_id: str,
        dispatcher: TaskDispatcher,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Run a task spec and verifier set through a dispatcher."""
        normalized = self._normalize_spec(spec)
        started = time.perf_counter()
        step_results: list[dict[str, Any]] = []
        task_verifier_results: list[dict[str, Any]] = []
        failure: dict[str, Any] | None = None

        for step in normalized["steps"]:
            result = await self._run_step(step, session_id=session_id, dispatcher=dispatcher)
            step_results.append(result)
            if not result["passed"] and failure is None:
                failure = self._failure_payload("step", result)
                if stop_on_failure:
                    break

        if failure is None or not stop_on_failure:
            for verifier in normalized["verifiers"]:
                result = await self._run_verifier(
                    verifier,
                    session_id=session_id,
                    dispatcher=dispatcher,
                    scope="task",
                )
                task_verifier_results.append(result)
                if not result["passed"] and failure is None:
                    failure = self._failure_payload("verifier", result)
                    if stop_on_failure:
                        break

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        passed = failure is None
        return {
            "status": "done" if passed else "failed",
            "passed": passed,
            "task": self._task_metadata(normalized),
            "session_id": session_id,
            "elapsed_ms": elapsed_ms,
            "stop_on_failure": stop_on_failure,
            "step_count": len(step_results),
            "steps": step_results,
            "verifiers": task_verifier_results,
            "failure": failure,
        }

    async def _run_step(
        self,
        step: dict[str, Any],
        *,
        session_id: str,
        dispatcher: TaskDispatcher,
    ) -> dict[str, Any]:
        call = self._call_for_step(step, session_id=session_id)
        started = time.perf_counter()
        response = await dispatcher(call)
        verifier_results: list[dict[str, Any]] = []
        passed = self._response_passed(response)
        failed_verifier: dict[str, Any] | None = None

        if passed:
            for verifier in step["verifiers"]:
                verifier_result = await self._run_verifier(
                    verifier,
                    session_id=session_id,
                    dispatcher=dispatcher,
                    scope="step",
                )
                verifier_results.append(verifier_result)
                if not verifier_result["passed"]:
                    passed = False
                    failed_verifier = verifier_result
                    break

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "index": step["index"],
            "name": step["name"],
            "kind": step["kind"],
            "operation": step["operation"],
            "passed": passed,
            "elapsed_ms": elapsed_ms,
            "response": response,
            "verifiers": verifier_results,
            "failed_verifier": failed_verifier,
        }

    async def _run_verifier(
        self,
        verifier: dict[str, Any],
        *,
        session_id: str,
        dispatcher: TaskDispatcher,
        scope: str,
    ) -> dict[str, Any]:
        call = self._call_for_verifier(verifier, session_id=session_id)
        started = time.perf_counter()
        response = await dispatcher(call)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "index": verifier["index"],
            "name": verifier["name"],
            "scope": scope,
            "operation": verifier["operation"],
            "passed": self._response_passed(response),
            "elapsed_ms": elapsed_ms,
            "response": response,
        }

    def _normalize_spec(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(spec, Mapping):
            raise self._invalid("Task spec must be a JSON object")

        steps_value = spec.get("steps", [])
        verifiers_value = spec.get("verifiers", [])
        if not isinstance(steps_value, Sequence) or isinstance(steps_value, (str, bytes)):
            raise self._invalid("'steps' must be a list")
        if not isinstance(verifiers_value, Sequence) or isinstance(verifiers_value, (str, bytes)):
            raise self._invalid("'verifiers' must be a list")
        if not steps_value and not verifiers_value:
            raise self._invalid("Task spec must include at least one step or verifier")

        steps = [
            self._normalize_step(self._as_mapping(step, f"steps[{index}]"), index=index)
            for index, step in enumerate(steps_value, start=1)
        ]
        verifiers = [
            self._normalize_verifier(
                self._as_mapping(verifier, f"verifiers[{index}]"),
                index=index,
            )
            for index, verifier in enumerate(verifiers_value, start=1)
        ]
        return {
            "name": self._optional_string(spec, "name") or "unnamed task",
            "description": self._optional_string(spec, "description"),
            "steps": steps,
            "verifiers": verifiers,
        }

    def _normalize_step(self, step: Mapping[str, Any], *, index: int) -> dict[str, Any]:
        kind, operation = self._step_kind_operation(step)
        verifiers_value = step.get("verify", step.get("verifiers", []))
        if not isinstance(verifiers_value, Sequence) or isinstance(verifiers_value, (str, bytes)):
            raise self._invalid(f"steps[{index}].verify must be a list")

        normalized = {
            "index": index,
            "name": self._optional_string(step, "name") or f"{kind}:{operation}",
            "kind": kind,
            "operation": operation,
            "source": dict(step),
            "verifiers": [
                self._normalize_verifier(
                    self._as_mapping(verifier, f"steps[{index}].verify[{verifier_index}]"),
                    index=verifier_index,
                )
                for verifier_index, verifier in enumerate(verifiers_value, start=1)
            ],
        }
        self._validate_call_source(normalized, source_label=f"steps[{index}]")
        return normalized

    def _normalize_verifier(self, verifier: Mapping[str, Any], *, index: int) -> dict[str, Any]:
        operation = self._required_string(verifier, "type", source_label=f"verifiers[{index}]")
        if operation not in WAIT_OPERATIONS:
            raise self._unsupported(f"Unsupported verifier type: {operation}")
        normalized = {
            "index": index,
            "name": self._optional_string(verifier, "name") or f"verify:{operation}",
            "operation": operation,
            "source": dict(verifier),
        }
        self._validate_wait_source(normalized, source_label=f"verifiers[{index}]")
        return normalized

    def _step_kind_operation(self, step: Mapping[str, Any]) -> tuple[str, str]:
        explicit_kind = self._optional_string(step, "kind")
        explicit_operation = self._optional_string(step, "operation") or self._optional_string(
            step, "op"
        )
        shorthand = [(kind, step[kind]) for kind in STEP_KINDS if kind in step]

        if explicit_kind or explicit_operation:
            if not explicit_kind or not explicit_operation:
                raise self._invalid("Both 'kind' and 'operation' are required together")
            if shorthand:
                raise self._invalid("Use either kind/operation or shorthand step syntax")
            kind = explicit_kind
            operation = explicit_operation
        else:
            if len(shorthand) != 1:
                raise self._invalid("Step must specify exactly one of action, wait, app, or ui")
            kind, raw_operation = shorthand[0]
            if not isinstance(raw_operation, str) or not raw_operation:
                raise self._invalid(f"Step field '{kind}' must be a non-empty string")
            operation = raw_operation

        self._validate_operation(kind, operation)
        return kind, operation

    def _validate_operation(self, kind: str, operation: str) -> None:
        allowed = {
            "action": ACTION_OPERATIONS,
            "wait": WAIT_OPERATIONS,
            "app": APP_OPERATIONS,
            "ui": UI_OPERATIONS,
        }.get(kind)
        if allowed is None:
            raise self._unsupported(f"Unsupported task step kind: {kind}")
        if operation not in allowed:
            raise self._unsupported(f"Unsupported {kind} operation: {operation}")

    def _validate_call_source(self, step: dict[str, Any], *, source_label: str) -> None:
        kind = cast(str, step["kind"])
        if kind == "wait":
            self._validate_wait_source(step, source_label=source_label)
        elif kind == "action":
            self._validate_action_source(step, source_label=source_label)
        elif kind == "app":
            self._validate_app_source(step, source_label=source_label)

    def _validate_action_source(self, step: dict[str, Any], *, source_label: str) -> None:
        source = cast(dict[str, Any], step["source"])
        operation = cast(str, step["operation"])
        if operation in {"tap", "long_tap", "clear"}:
            self._required_string(source, "ref", source_label=source_label)
        elif operation == "set_text":
            self._required_string(source, "ref", source_label=source_label)
            self._required_string(source, "text", source_label=source_label)
        elif operation == "swipe":
            self._required_string(source, "direction", source_label=source_label)

    def _validate_wait_source(self, step: dict[str, Any], *, source_label: str) -> None:
        source = cast(dict[str, Any], step["source"])
        operation = cast(str, step["operation"])
        if operation == "activity":
            self._required_string(source, "activity", source_label=source_label)
        elif operation == "text":
            self._required_string(source, "text", source_label=source_label)
        elif operation in {"exists", "gone"} and not self._selector_payload(source):
            raise self._invalid(f"{source_label} requires ref, selector, text, id, or desc")

    def _validate_app_source(self, step: dict[str, Any], *, source_label: str) -> None:
        source = cast(dict[str, Any], step["source"])
        operation = cast(str, step["operation"])
        if operation in {"launch", "force_stop"}:
            self._required_string(source, "package", source_label=source_label)
        elif operation == "deeplink":
            self._required_string(source, "uri", source_label=source_label)

    def _call_for_step(self, step: dict[str, Any], *, session_id: str) -> TaskCall:
        kind = cast(str, step["kind"])
        operation = cast(str, step["operation"])
        source = cast(dict[str, Any], step["source"])
        payload = self._payload_for(kind, operation, source, session_id=session_id)
        return TaskCall(kind=kind, operation=operation, payload=payload, label=cast(str, step["name"]))

    def _call_for_verifier(self, verifier: dict[str, Any], *, session_id: str) -> TaskCall:
        operation = cast(str, verifier["operation"])
        source = cast(dict[str, Any], verifier["source"])
        payload = self._payload_for("wait", operation, source, session_id=session_id)
        return TaskCall(
            kind="wait",
            operation=operation,
            payload=payload,
            label=cast(str, verifier["name"]),
        )

    def _payload_for(
        self,
        kind: str,
        operation: str,
        source: dict[str, Any],
        *,
        session_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"session_id": session_id}
        if kind == "action":
            if operation in {"tap", "long_tap", "clear"}:
                payload["ref"] = source["ref"]
            elif operation == "set_text":
                payload["ref"] = source["ref"]
                payload["text"] = source["text"]
            elif operation == "swipe":
                payload["direction"] = source["direction"]
                payload["container"] = source.get("container")
                payload["distance"] = source.get("distance", 0.8)
                payload["duration_ms"] = source.get("duration_ms", source.get("duration", 300))
        elif kind == "wait":
            if operation == "activity":
                payload["activity"] = source["activity"]
            elif operation == "text":
                payload["text"] = source["text"]
            elif operation in {"exists", "gone"}:
                payload.update(self._selector_payload(source))
            if "timeout_ms" in source:
                payload["timeout_ms"] = source["timeout_ms"]
        elif kind == "app":
            if operation == "launch":
                payload["package"] = source["package"]
                payload["activity"] = source.get("activity")
                payload["wait_debugger"] = source.get("wait_debugger", False)
            elif operation == "force_stop":
                payload["package"] = source["package"]
            elif operation == "deeplink":
                payload["uri"] = source["uri"]
                payload["wait_debugger"] = source.get("wait_debugger", False)
        elif kind == "ui":
            payload["mode"] = source.get("mode", "compact")
            payload["full"] = source.get("full", False)
        return payload

    def _selector_payload(self, source: Mapping[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        ref = source.get("ref")
        if isinstance(ref, str) and ref:
            payload["ref"] = ref
        selector = source.get("selector")
        if isinstance(selector, Mapping):
            payload["selector"] = dict(selector)

        inline_selector: dict[str, str] = {}
        text = source.get("text")
        text_contains = source.get("text_contains") or source.get("textContains")
        resource_id = source.get("id") or source.get("resource_id") or source.get("resourceId")
        resource_id_matches = source.get("id_matches") or source.get("resourceIdMatches")
        desc = source.get("desc") or source.get("description")
        desc_contains = source.get("desc_contains") or source.get("descriptionContains")
        class_name = source.get("class") or source.get("class_name") or source.get("className")
        if isinstance(text, str) and text:
            inline_selector["text"] = text
        if isinstance(text_contains, str) and text_contains:
            inline_selector["textContains"] = text_contains
        if isinstance(resource_id, str) and resource_id:
            inline_selector["resourceId"] = resource_id
        if isinstance(resource_id_matches, str) and resource_id_matches:
            inline_selector["resourceIdMatches"] = resource_id_matches
        if isinstance(desc, str) and desc:
            inline_selector["description"] = desc
        if isinstance(desc_contains, str) and desc_contains:
            inline_selector["descriptionContains"] = desc_contains
        if isinstance(class_name, str) and class_name:
            inline_selector["className"] = class_name
        if inline_selector and "selector" not in payload:
            payload["selector"] = inline_selector
        return payload

    @staticmethod
    def _response_passed(response: Mapping[str, Any]) -> bool:
        return response.get("status") == "done"

    @staticmethod
    def _failure_payload(kind: str, result: Mapping[str, Any]) -> dict[str, Any]:
        failure = {
            "kind": kind,
            "index": result.get("index"),
            "name": result.get("name"),
            "operation": result.get("operation"),
            "response": result.get("response"),
        }
        if result.get("failed_verifier"):
            failure["verifier"] = result["failed_verifier"]
        return failure

    @staticmethod
    def _task_metadata(spec: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "name": spec.get("name"),
            "description": spec.get("description"),
        }

    def _required_string(
        self,
        source: Mapping[str, Any],
        key: str,
        *,
        source_label: str,
    ) -> str:
        value = source.get(key)
        if not isinstance(value, str) or not value:
            raise self._invalid(f"{source_label}.{key} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(source: Mapping[str, Any], key: str) -> str | None:
        value = source.get(key)
        return value if isinstance(value, str) and value else None

    def _as_mapping(self, value: Any, source_label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise self._invalid(f"{source_label} must be a JSON object")
        return value

    @staticmethod
    def _invalid(message: str) -> AgentError:
        return AgentError(
            code="ERR_TASK_INVALID",
            message=message,
            context={},
            remediation="Fix the task JSON and run 'task validate' before running it.",
        )

    @staticmethod
    def _unsupported(message: str) -> AgentError:
        return AgentError(
            code="ERR_TASK_UNSUPPORTED_STEP",
            message=message,
            context={},
            remediation="Use supported action, wait, app, or ui task operations.",
        )
