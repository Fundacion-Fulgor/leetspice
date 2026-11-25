"""Testing bench: testers try challenges and track their verification status."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from .auth import require_csrf
from .db import get_session
from .models import Challenge, Submission, User
from .web import _context, _current_user, templates

router = APIRouter()

CLAIM_DURATION = timedelta(days=10)
STATUS_LABELS = {
    "unverified": "Unverified",
    "testing": "Testing",
    "verified": "Verified",
    "problems": "Needs fix",
}
ACTIONS = {"claim", "release", "verify", "report", "reopen"}


class VerificationError(Exception):
    """An action is not allowed for the challenge's current state or this user."""


def _aware(value: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip; every stored timestamp is UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def claim_expires_at(challenge: Challenge) -> datetime | None:
    if challenge.verification_status != "testing" or challenge.claimed_at is None:
        return None
    return _aware(challenge.claimed_at) + CLAIM_DURATION


def _clear_claim(challenge: Challenge) -> None:
    challenge.claimed_by_id = None
    challenge.claimed_at = None


def effective_status(challenge: Challenge, now: datetime | None = None) -> str:
    """The verification status as it stands now, without writing anything.

    A claim lasts ``CLAIM_DURATION``; a verification only holds for the judge version it
    was made against, so bumping ``verification_version`` invalidates it. Both read as
    ``unverified`` here until ``expire_verifications`` persists them.
    """
    state = challenge.verification_status
    expires = claim_expires_at(challenge)
    if expires is not None and expires <= (now or datetime.now(UTC)):
        return "unverified"
    if state == "verified" and challenge.verified_version != challenge.verification_version:
        return "unverified"
    return state


def expire_verifications(db: Session, now: datetime | None = None) -> None:
    """Persist stale claims and outdated verifications as ``unverified``.

    Only the workflow actions call this; read-only pages use ``effective_status``.
    """
    now = now or datetime.now(UTC)
    changed = False
    for challenge in db.scalars(
        select(Challenge).where(Challenge.verification_status.in_(("testing", "verified")))
    ):
        if effective_status(challenge, now) == "unverified":
            challenge.verification_status = "unverified"
            _clear_claim(challenge)
            changed = True
    if changed:
        db.commit()


def can_tester_edit(user: User, challenge: Challenge) -> bool:
    """Testers edit only their own challenges, while drafts or after a reported problem."""
    return challenge.created_by_id == user.id and (
        not challenge.is_active or challenge.verification_status == "problems"
    )


def is_own_challenge(user: User, challenge: Challenge) -> bool:
    """True when a tester authored *challenge*: someone else must verify it. Admins are exempt."""
    return not user.is_admin and challenge.created_by_id == user.id


def invalidate_verification(challenge: Challenge) -> None:
    """Send a verified challenge back to ``unverified``, e.g. after its author edited it."""
    if challenge.verification_status == "verified":
        challenge.verification_status = "unverified"
        challenge.verified_by_id = None
        challenge.verified_at = None
        challenge.verified_version = None
        challenge.verification_notes = None


def _has_accepted_run(db: Session, user: User, challenge: Challenge) -> bool:
    return (
        db.scalar(
            select(Submission.id)
            .where(
                Submission.user_id == user.id,
                Submission.challenge_id == challenge.id,
                Submission.verification_version == challenge.verification_version,
                Submission.status == "accepted",
                Submission.score.is_not(None),
            )
            .limit(1)
        )
        is not None
    )


def apply_action(
    db: Session,
    user: User,
    challenge: Challenge,
    action: str,
    *,
    notes: str = "",
    score_confirmed: bool = False,
    now: datetime | None = None,
) -> None:
    """Move *challenge* through the verification workflow, or raise ``VerificationError``."""
    now = now or datetime.now(UTC)
    state = challenge.verification_status
    is_claimer = challenge.claimed_by_id == user.id
    if action in ("claim", "verify") and is_own_challenge(user, challenge):
        raise VerificationError(
            "You created this challenge, so another tester has to claim and verify it."
        )
    if action == "claim":
        if state != "unverified":
            raise VerificationError("Only unverified challenges can be claimed.")
        # Conditional update: when two testers claim at once, only the first one to
        # write still finds the row unverified; the other one updates nothing.
        claimed = db.execute(
            update(Challenge)
            .where(Challenge.id == challenge.id, Challenge.verification_status == "unverified")
            .values(verification_status="testing", claimed_by_id=user.id, claimed_at=now)
        )
        if cast(CursorResult[Any], claimed).rowcount != 1:
            db.rollback()
            raise VerificationError("Another tester claimed this challenge first.")
        db.commit()
        db.refresh(challenge)
        return
    elif action == "release":
        if state != "testing" or not (is_claimer or user.is_admin):
            raise VerificationError("Only the tester who claimed it can release it.")
        challenge.verification_status = "unverified"
        _clear_claim(challenge)
    elif action == "verify":
        if state != "testing" or not (is_claimer or user.is_admin):
            raise VerificationError("Claim the challenge before verifying it.")
        if not _has_accepted_run(db, user, challenge):
            raise VerificationError(
                "The judge must accept one of your submissions on the current version first."
            )
        if not score_confirmed:
            raise VerificationError("Confirm that the score is correct before verifying.")
        challenge.verification_status = "verified"
        challenge.verified_by_id = user.id
        challenge.verified_at = now
        challenge.verified_version = challenge.verification_version
        challenge.verification_notes = notes or None
        _clear_claim(challenge)
    elif action == "report":
        if not (state == "verified" or (state == "testing" and (is_claimer or user.is_admin))):
            raise VerificationError("Only verified or claimed challenges can be reported.")
        if not notes:
            raise VerificationError("Describe the problem before reporting it.")
        challenge.verification_status = "problems"
        challenge.verification_notes = notes
        _clear_claim(challenge)
    elif action == "reopen":
        if state != "problems" or not (challenge.created_by_id == user.id or user.is_admin):
            raise VerificationError("Only the author or an admin can mark a fix as done.")
        challenge.verification_status = "unverified"
    else:
        raise VerificationError("Unknown action.")
    db.commit()


def _bench_user(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if user is None or not (user.is_tester or user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    """What one tester has verified, created and is testing right now."""

    user: User
    verified: tuple[Challenge, ...]
    created: tuple[Challenge, ...]
    testing: tuple[Challenge, ...]


def collect_tester_activity(db: Session, now: datetime | None = None) -> list[ActivitySummary]:
    """Activity of every tester and every admin, since admins can do a tester's work too.

    Anyone else with recorded activity (e.g. a former tester) is listed as well.
    "Verified" counts the challenges whose current, still-valid verification is theirs:
    a verification that was reported, invalidated or outdated by a new judge version
    no longer counts.
    """
    now = now or datetime.now(UTC)
    challenges = db.scalars(select(Challenge).order_by(Challenge.curriculum_order, Challenge.id))
    verified: dict[int, list[Challenge]] = {}
    created: dict[int, list[Challenge]] = {}
    testing: dict[int, list[Challenge]] = {}
    for challenge in challenges:
        state = effective_status(challenge, now)
        if state == "verified" and challenge.verified_by_id is not None:
            verified.setdefault(challenge.verified_by_id, []).append(challenge)
        if state == "testing" and challenge.claimed_by_id is not None:
            testing.setdefault(challenge.claimed_by_id, []).append(challenge)
        if challenge.created_by_id is not None:
            created.setdefault(challenge.created_by_id, []).append(challenge)

    active_ids = set(verified) | set(created) | set(testing)
    users = db.scalars(
        select(User).where(
            User.is_tester.is_(True) | User.is_admin.is_(True) | User.id.in_(active_ids)
        )
    )
    rows = [
        ActivitySummary(
            user=user,
            verified=tuple(verified.get(user.id, ())),
            created=tuple(created.get(user.id, ())),
            testing=tuple(testing.get(user.id, ())),
        )
        for user in users
    ]
    return sorted(
        rows,
        key=lambda row: (
            -len(row.verified),
            -len(row.created),
            row.user.display_name.casefold(),
            row.user.id,
        ),
    )


def bench_order(challenge: Challenge) -> tuple[int, int, int]:
    """Sort key: published-but-unverified first, then unverified drafts, verified last."""
    if effective_status(challenge) == "verified":
        group = 2
    elif challenge.is_active:
        group = 0
    else:
        group = 1
    return group, challenge.curriculum_order, challenge.id


def _render_bench(
    request: Request,
    db: Session,
    user: User,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    # Read-only: stale claims and outdated verifications are shown through
    # effective_status() and only persisted by the POST actions.
    search = request.query_params.get("q", "").strip()[:100]
    query = select(Challenge).options(
        selectinload(Challenge.claimed_by),
        selectinload(Challenge.verified_by),
        selectinload(Challenge.created_by),
    )
    if search:
        query = query.where(Challenge.title.icontains(search, autoescape=True))
    challenges = sorted(db.scalars(query).all(), key=bench_order)
    latest: dict[int, Submission] = {}
    for submission in db.scalars(
        select(Submission)
        .where(Submission.user_id == user.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    ):
        latest.setdefault(submission.challenge_id, submission)
    rows = []
    for challenge in challenges:
        state = effective_status(challenge)
        rows.append(
            {
                "challenge": challenge,
                "state": state,
                "status_label": STATUS_LABELS.get(state, "Unknown"),
                "expires_at": claim_expires_at(challenge) if state == "testing" else None,
                "latest": latest.get(challenge.id),
                "can_edit": user.is_admin or can_tester_edit(user, challenge),
            }
        )
    return templates.TemplateResponse(
        request,
        "testing.html",
        _context(
            request,
            db,
            rows=rows,
            error=error,
            search=search,
            claim_days=CLAIM_DURATION.days,
        ),
        status_code=status_code,
    )


@router.get("/testing", response_class=HTMLResponse)
def testing_bench(request: Request, db: Annotated[Session, Depends(get_session)]) -> Response:
    if _current_user(request, db) is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return _render_bench(request, db, _bench_user(request, db))


@router.post("/testing/{slug}/{action}", response_class=HTMLResponse)
def testing_action(
    slug: str,
    action: str,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    csrf_token: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    score_confirmed: Annotated[str, Form()] = "",
) -> Response:
    require_csrf(request, csrf_token)
    user = _bench_user(request, db)
    if action not in ACTIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    expire_verifications(db)
    challenge = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        apply_action(
            db,
            user,
            challenge,
            action,
            notes=notes.strip()[:2000],
            score_confirmed=score_confirmed == "on",
        )
    except VerificationError as exc:
        return _render_bench(
            request, db, user, error=str(exc), status_code=status.HTTP_409_CONFLICT
        )
    search = request.query_params.get("q", "").strip()
    target = f"/testing?{urlencode({'q': search})}" if search else "/testing"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
