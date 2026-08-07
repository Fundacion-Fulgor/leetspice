"""Polling SQLAlchemy worker for queued LeetSpice judging jobs.

The application owns the database schema. This module deliberately discovers
common session, model, and field names at runtime so importing it does not
require application models to exist during early development.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select

from .judge import (
    CharacterizationJudge,
    JudgeResult,
    LayoutJudge,
    MockJudge,
    NgspiceJudge,
)

LOGGER = logging.getLogger("leetspice.worker")
SESSION_MODULES = ("leetspice.database", "leetspice.db")
MODEL_MODULES = ("leetspice.models", "leetspice.db.models")
MODEL_NAMES = ("JudgeJob", "Submission")


def _first_attr(value: Any, names: Sequence[str]) -> tuple[str, Any]:
    for name in names:
        if hasattr(value, name):
            return name, getattr(value, name)
    raise AttributeError(f"{type(value).__name__} has none of: {', '.join(names)}")


def _status_value(target: Any, candidates: Sequence[str]) -> Any:
    """Match a status enum where possible, otherwise preserve string storage."""

    current = getattr(target, "status", None)
    enum_type = type(current) if isinstance(current, Enum) else None
    if enum_type is None:
        column = getattr(type(target), "status", None)
        enum_type = getattr(getattr(column, "type", None), "enum_class", None)
    if enum_type is not None:
        for candidate in candidates:
            for member in enum_type:
                if member.name.casefold() == candidate or str(member.value).casefold() == candidate:
                    return member
        raise RuntimeError(f"status enum {enum_type.__name__} lacks {candidates!r}")
    return candidates[0]


def _queued_value(model: type[Any]) -> Any:
    column = getattr(model, "status", None)
    enum_type = getattr(getattr(column, "type", None), "enum_class", None)
    if enum_type is not None:
        for member in enum_type:
            if member.name.casefold() == "queued" or str(member.value).casefold() == "queued":
                return member
        raise RuntimeError(f"status enum {enum_type.__name__} has no queued value")
    return "queued"


def _set_status(target: Any, candidates: Sequence[str]) -> None:
    if not hasattr(target, "status"):
        raise AttributeError(f"{type(target).__name__} has no status field")
    target.status = _status_value(target, candidates)


def _payload(job: Any) -> tuple[str, str, list[str]]:
    source = getattr(job, "submission", job)
    _, netlist = _first_attr(source, ("netlist", "netlist_text", "source", "code"))
    challenge = getattr(source, "challenge", None) or getattr(job, "challenge", None)
    metadata_sources = (job, source, challenge)

    subckt = None
    pins = None
    for item in metadata_sources:
        if item is None:
            continue
        if subckt is None:
            for name in ("expected_subckt", "subckt_name", "subcircuit_name"):
                subckt = getattr(item, name, None)
                if subckt is not None:
                    break
        if pins is None:
            for name in ("expected_pins", "pins", "pin_order"):
                pins = getattr(item, name, None)
                if pins is not None:
                    break

    if not isinstance(netlist, str) or not isinstance(subckt, str):
        raise ValueError("job must provide netlist text and an expected subcircuit name")
    if isinstance(pins, str):
        try:
            decoded = json.loads(pins)
            pins = decoded if isinstance(decoded, list) else pins.split()
        except json.JSONDecodeError:
            pins = pins.replace(",", " ").split()
    if not isinstance(pins, (list, tuple)) or not all(isinstance(pin, str) for pin in pins):
        raise ValueError("job must provide an ordered pin list")
    return netlist, subckt, list(pins)


def _judge(job: Any, backend: Any) -> tuple[JudgeResult, str]:
    source = getattr(job, "submission", job)
    challenge = getattr(source, "challenge", None) or getattr(job, "challenge", None)
    if getattr(source, "submission_kind", "netlist") == "gds":
        if challenge is None or getattr(challenge, "judge_backend", None) != "klayout":
            raise ValueError("GDS submission requires a KLayout challenge")
        payload = getattr(source, "payload_binary", None)
        if not isinstance(payload, bytes):
            raise ValueError("GDS submission payload is missing")
        layout_backend = LayoutJudge(timeout=float(os.getenv("LEETSPICE_LAYOUT_TIMEOUT", "300")))
        result = layout_backend.judge(
            payload,
            challenge.expected_subckt,
            list(challenge.expected_pins),
            challenge.fixture_path,
            dict(challenge.judge_config),
        )
        return result, type(layout_backend).__name__
    if challenge is not None and getattr(challenge, "judge_backend", None) == "characterization":
        characterization_backend = CharacterizationJudge()
        netlist, subckt, pins = _payload(job)
        result = characterization_backend.judge(
            netlist,
            subckt,
            pins,
            challenge.fixture_path,
            dict(challenge.judge_config),
        )
        return result, type(characterization_backend).__name__
    return backend.judge(*_payload(job)), type(backend).__name__


def _store_related_run(job: Any, result: JudgeResult, backend_name: str) -> None:
    relationship = getattr(type(job), "judge_runs", None)
    try:
        run_type = relationship.property.mapper.class_
    except AttributeError:
        return

    now = datetime.now(UTC)
    run = run_type(
        status="completed" if result.accepted else "rejected",
        backend=backend_name,
        error_message=None if result.accepted else result.message,
        finished_at=now,
    )
    measurement_relationship = getattr(run_type, "measurements", None)
    try:
        measurement_type = measurement_relationship.property.mapper.class_
    except AttributeError:
        measurement_type = None
    if measurement_type is not None:
        run.measurements.extend(
            measurement_type(
                name=measurement.name,
                value=measurement.value,
                unit=measurement.unit,
                passed=measurement.passed,
                details={"conditions": measurement.conditions} if measurement.conditions else None,
            )
            for measurement in result.measurements
        )
    job.judge_runs.append(run)


def _store_result(job: Any, result: JudgeResult, backend_name: str) -> None:
    target = getattr(job, "submission", job)
    items = (job,) if target is job else (job, target)
    for item in items:
        if hasattr(item, "score"):
            item.score = result.score
        for name in ("result_json", "judge_result", "result"):
            if hasattr(item, name):
                column = getattr(type(item), name, None)
                python_type = None
                try:
                    python_type = column.type.python_type
                except (AttributeError, NotImplementedError):
                    pass
                value = json.dumps(result.to_dict()) if python_type is str else result.to_dict()
                setattr(item, name, value)
                break
        if hasattr(item, "error_message"):
            item.error_message = None if result.accepted else result.message
        if result.accepted and hasattr(item, "accepted_at"):
            item.accepted_at = datetime.now(UTC)
    statuses = ("accepted", "completed") if result.accepted else ("rejected", "failed")
    _set_status(job, statuses)
    if target is not job and hasattr(target, "status"):
        _set_status(target, statuses)
    _store_related_run(target, result, backend_name)


def claim_one(session: Any, model: type[Any]) -> Any | None:
    """Claim one queued row; callers commit before doing expensive work."""

    statement = select(model).where(model.status == _queued_value(model))
    if hasattr(model, "id"):
        statement = statement.order_by(model.id)
    statement = statement.limit(1).with_for_update(skip_locked=True)
    job = session.execute(statement).scalars().first()
    if job is None:
        return None
    _set_status(job, ("running", "processing"))
    session.commit()
    return job


def process_one(session_factory: Callable[[], Any], model: type[Any], backend: Any) -> bool:
    """Claim and process one job, returning whether a job was found."""

    with session_factory() as session:
        job = claim_one(session, model)
        if job is None:
            return False
        job_id = getattr(job, "id", None)

    with session_factory() as session:
        job = session.get(model, job_id) if job_id is not None else session.merge(job)
        backend_name = type(backend).__name__
        try:
            result, backend_name = _judge(job, backend)
            if not isinstance(result, JudgeResult):
                raise TypeError("judge backend must return JudgeResult")
            _store_result(job, result, backend_name)
        except Exception as error:  # Persist backend failures rather than losing the job.
            LOGGER.exception("judge job %s failed", job_id)
            result = JudgeResult(False, 0.0, message=f"worker error: {error}")
            try:
                _store_result(job, result, backend_name)
                _set_status(job, ("failed", "rejected"))
                target = getattr(job, "submission", job)
                if target is not job and hasattr(target, "status"):
                    _set_status(target, ("failed", "rejected"))
                judge_runs = getattr(target, "judge_runs", ())
                if judge_runs:
                    judge_runs[-1].status = "failed"
            except Exception:
                _set_status(job, ("failed", "rejected"))
        session.commit()
    return True


def discover_contract() -> tuple[Callable[[], Any], type[Any]]:
    session_factory = None
    for module_name in SESSION_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for name in ("SessionLocal", "session_factory", "Session"):
            candidate = getattr(module, name, None)
            if callable(candidate):
                session_factory = candidate
                break
        if session_factory is not None:
            break

    model = None
    configured_model = os.getenv("LEETSPICE_JOB_MODEL")
    model_names = (configured_model,) if configured_model else MODEL_NAMES
    for module_name in MODEL_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for name in model_names:
            candidate = getattr(module, name, None)
            if candidate is not None and hasattr(candidate, "status"):
                model = candidate
                break
        if model is not None:
            break

    if session_factory is None or model is None:
        raise RuntimeError(
            "could not discover SQLAlchemy contract; define SessionLocal in leetspice.database "
            "or leetspice.db and JudgeJob/Submission in leetspice.models or leetspice.db.models"
        )
    return session_factory, model


def configured_backend(name: str | None = None) -> MockJudge | NgspiceJudge:
    selected = (
        name or os.getenv("LEETSPICE_JUDGE_BACKEND") or os.getenv("RUNNER_BACKEND", "mock")
    ).casefold()
    if selected == "mock":
        return MockJudge()
    if selected == "ngspice":
        return NgspiceJudge(
            executable=os.getenv("LEETSPICE_NGSPICE", "ngspice"),
            timeout=float(os.getenv("LEETSPICE_JUDGE_TIMEOUT", "10")),
        )
    raise ValueError(f"unknown judge backend: {selected}")


def run_worker(
    session_factory: Callable[[], Any],
    model: type[Any],
    backend: Any,
    *,
    once: bool = False,
    poll_interval: float = 1.0,
) -> None:
    while True:
        processed = process_one(session_factory, model, backend)
        if once:
            return
        if not processed:
            time.sleep(poll_interval)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process queued LeetSpice judge jobs")
    parser.add_argument("--once", action="store_true", help="process at most one queued job")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="idle poll delay in seconds",
    )
    parser.add_argument(
        "--backend",
        choices=("mock", "ngspice"),
        help="override configured backend",
    )
    args = parser.parse_args(argv)
    if args.poll_interval < 0:
        parser.error("--poll-interval must be non-negative")
    logging.basicConfig(level=os.getenv("LEETSPICE_LOG_LEVEL", "INFO"))
    try:
        session_factory, model = discover_contract()
        run_worker(
            session_factory,
            model,
            configured_backend(args.backend),
            once=args.once,
            poll_interval=args.poll_interval,
        )
    except (RuntimeError, ValueError) as error:
        LOGGER.error("%s", error)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
