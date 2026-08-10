"""Database models shared by the web application and judge worker."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="user")


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    expected_subckt: Mapped[str] = mapped_column(String(100))
    expected_pins: Mapped[list[str]] = mapped_column(JSON, default=list)
    starter_netlist: Mapped[str] = mapped_column(Text, default="")
    submission_kind: Mapped[str] = mapped_column(String(30), default="netlist")
    judge_backend: Mapped[str] = mapped_column(String(80), default="ngspice")
    submission_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    judge_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fixture_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="General", server_default="General")
    track: Mapped[str] = mapped_column(String(80), default="General", server_default="General")
    difficulty: Mapped[str] = mapped_column(String(50), default="medium", server_default="medium")
    verification_version: Mapped[int] = mapped_column(default=1, server_default="1")
    is_ranked: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    curriculum_order: Mapped[int] = mapped_column(default=0, server_default="0")
    prerequisites: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    retired_slugs: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    score_unit: Mapped[str] = mapped_column(String(30), default="points")
    lower_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="challenge")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_challenge_status_score", "challenge_id", "status", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id"), index=True)
    verification_version: Mapped[int] = mapped_column(default=1, server_default="1")
    submission_kind: Mapped[str] = mapped_column(String(30), default="netlist")
    netlist: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_binary: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_size: Mapped[int] = mapped_column(default=0)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="submissions")
    challenge: Mapped[Challenge] = relationship(back_populates="submissions")
    judge_runs: Mapped[list["JudgeRun"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class JudgeRun(Base):
    __tablename__ = "judge_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    backend: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="judge_runs")
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="judge_run", cascade="all, delete-orphan"
    )


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    judge_run_id: Mapped[int] = mapped_column(ForeignKey("judge_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    judge_run: Mapped[JudgeRun] = relationship(back_populates="measurements")
