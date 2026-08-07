"""Server-rendered application routes."""

import re
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .auth import hash_password, new_session, require_csrf, verify_password
from .db import get_session
from .leaderboards import global_leaderboard
from .models import Challenge, Submission, User

router = APIRouter()
SUBMISSIONS_PAGE_SIZE = 25
templates = Jinja2Templates(
    directory=str(__import__("pathlib").Path(__file__).parent / "templates")
)


def _current_user(request: Request, db: Session) -> User | None:
    user_id = request.state.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def _context(request: Request, db: Session, **values: object) -> dict[str, object]:
    return {
        "request": request,
        "current_user": _current_user(request, db),
        "csrf_token": request.state.session["csrf"],
        **values,
    }


def _validate_netlist(netlist: str, challenge: Challenge) -> None:
    if not netlist:
        raise ValueError("Netlist cannot be empty")
    try:
        from leetspice.judge.validation import validate_netlist
    except ImportError:
        try:
            from leetspice.judge.validator import validate_netlist
        except ImportError:
            # Web development remains usable before an optional judge package is installed.
            return
    validate_netlist(netlist, challenge.expected_subckt, challenge.expected_pins)


def _leaderboard(db: Session, challenge: Challenge) -> Sequence[tuple[User, float]]:
    aggregate = func.min if challenge.lower_is_better else func.max
    best = (
        select(Submission.user_id, aggregate(Submission.score).label("best_score"))
        .where(
            Submission.challenge_id == challenge.id,
            Submission.verification_version == challenge.verification_version,
            Submission.status == "accepted",
            Submission.score.is_not(None),
        )
        .group_by(Submission.user_id)
        .subquery()
    )
    order = best.c.best_score.asc() if challenge.lower_is_better else best.c.best_score.desc()
    return db.execute(
        select(User, best.c.best_score).join(best, best.c.user_id == User.id).order_by(order)
    ).all()


@router.get("/", response_class=HTMLResponse)
def catalog(request: Request, db: Annotated[Session, Depends(get_session)]) -> HTMLResponse:
    challenges = db.scalars(
        select(Challenge).where(Challenge.is_active.is_(True)).order_by(Challenge.id)
    ).all()
    # Group challenges by track
    tracks: dict[str, list[Challenge]] = {}
    for c in challenges:
        tracks.setdefault(c.track, []).append(c)
    return templates.TemplateResponse(
        request,
        "catalog.html",
        _context(request, db, tracks=tracks, challenges_count=len(challenges)),
    )


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, db: Annotated[Session, Depends(get_session)]) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", _context(request, db))


@router.get("/leaderboard", response_class=HTMLResponse)
def global_board(request: Request, db: Annotated[Session, Depends(get_session)]) -> HTMLResponse:
    challenges = db.scalars(
        select(Challenge).where(Challenge.is_active.is_(True)).order_by(Challenge.id)
    ).all()
    return templates.TemplateResponse(
        request,
        "global_leaderboard.html",
        _context(
            request,
            db,
            leaders=global_leaderboard(db),
            maximum_points=sum(
                {"introductory": 1, "intermediate": 2, "advanced": 3, "capstone": 4}[
                    challenge.difficulty
                ]
                * 100
                for challenge in challenges
            ),
        ),
    )


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    email: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse:
    require_csrf(request, csrf_token)
    normalized_email = email.strip().lower()
    name = display_name.strip()
    error = None
    if "@" not in normalized_email or len(normalized_email) > 320:
        error = "Enter a valid email address."
    elif not name or len(name) > 80:
        error = "Display name must be between 1 and 80 characters."
    elif len(password) < 10:
        error = "Password must be at least 10 characters."
    elif db.scalar(select(User.id).where(User.email == normalized_email)):
        error = "An account already exists for that email."
    if error:
        return templates.TemplateResponse(
            request,
            "register.html",
            _context(request, db, error=error, email=normalized_email, display_name=name),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    user = User(email=normalized_email, display_name=name, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.state.session = new_session(user.id, request.app.state.settings)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Annotated[Session, Depends(get_session)]) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", _context(request, db))


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse:
    require_csrf(request, csrf_token)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            _context(request, db, error="Invalid email or password.", email=email),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.state.session = new_session(user.id, request.app.state.settings)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request, csrf_token: Annotated[str, Form()]) -> RedirectResponse:
    require_csrf(request, csrf_token)
    request.state.session = new_session(None, request.app.state.settings)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/challenges/{slug}", response_class=HTMLResponse)
def challenge_detail(
    slug: str, request: Request, db: Annotated[Session, Depends(get_session)]
) -> HTMLResponse:
    challenge = db.scalar(
        select(Challenge).where(Challenge.slug == slug, Challenge.is_active.is_(True))
    )
    if challenge is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "challenge.html",
        _context(request, db, challenge=challenge, leaders=_leaderboard(db, challenge)),
    )


def _challenge_asset(request: Request, challenge: Challenge, asset_id: str) -> tuple[Path, str]:
    asset = next((item for item in challenge.assets if item.get("id") == asset_id), None)
    if asset is None or not challenge.fixture_path:
        raise HTTPException(status_code=404)
    root = (Path(request.app.state.settings.challenges_path) / challenge.fixture_path).resolve()
    candidate = (root / str(asset.get("path", ""))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise HTTPException(status_code=404) from error
    if not candidate.is_file():
        raise HTTPException(status_code=404)
    return candidate, str(asset.get("download_name") or candidate.name)


@router.get("/challenges/{slug}/assets/{asset_id}")
def challenge_asset(
    slug: str,
    asset_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    challenge = db.scalar(
        select(Challenge).where(Challenge.slug == slug, Challenge.is_active.is_(True))
    )
    if challenge is None:
        raise HTTPException(status_code=404)
    path, download_name = _challenge_asset(request, challenge, asset_id)
    return FileResponse(
        path,
        filename=download_name,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/challenges/{slug}/submit", response_class=HTMLResponse)
async def submit(
    slug: str,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    csrf_token: Annotated[str, Form()],
    netlist: Annotated[str, Form()] = "",
    layout: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse:
    require_csrf(request, csrf_token)
    user = _current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    challenge = db.scalar(
        select(Challenge).where(Challenge.slug == slug, Challenge.is_active.is_(True))
    )
    if challenge is None:
        raise HTTPException(status_code=404)
    try:
        if challenge.submission_kind == "gds":
            maximum = int(challenge.submission_config.get("maximum_bytes", 8 * 1024 * 1024))
            extensions = tuple(challenge.submission_config.get("extensions", [".gds"]))
            if layout is None or not layout.filename:
                raise ValueError("Select a GDSII file to submit")
            filename = Path(layout.filename).name
            if Path(filename).suffix.casefold() not in {item.casefold() for item in extensions}:
                raise ValueError("Layout submission must be a .gds file")
            payload = await layout.read(maximum + 1)
            if not payload:
                raise ValueError("GDSII file cannot be empty")
            if len(payload) > maximum:
                raise ValueError(f"GDSII file exceeds {maximum} bytes")
            submission = Submission(
                user_id=user.id,
                challenge_id=challenge.id,
                verification_version=challenge.verification_version,
                submission_kind="gds",
                payload_binary=payload,
                original_filename=filename[:255],
                media_type="application/octet-stream",
                payload_size=len(payload),
                payload_sha256=sha256(payload).hexdigest(),
            )
        else:
            _validate_netlist(netlist, challenge)
            encoded = netlist.encode("utf-8")
            submission = Submission(
                user_id=user.id,
                challenge_id=challenge.id,
                verification_version=challenge.verification_version,
                submission_kind="netlist",
                netlist=netlist,
                payload_size=len(encoded),
                payload_sha256=sha256(encoded).hexdigest(),
            )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "challenge.html",
            _context(
                request,
                db,
                challenge=challenge,
                leaders=_leaderboard(db, challenge),
                error=str(exc),
                submitted_netlist=netlist,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    db.add(submission)
    db.commit()
    return RedirectResponse(f"/submissions/{submission.id}", status_code=status.HTTP_303_SEE_OTHER)


def _owned_submission(db: Session, submission_id: int, user: User | None) -> Submission:
    if user is None:
        raise HTTPException(status_code=404)
    submission = db.scalar(
        select(Submission)
        .options(selectinload(Submission.challenge), selectinload(Submission.judge_runs))
        .where(Submission.id == submission_id, Submission.user_id == user.id)
    )
    if submission is None:
        raise HTTPException(status_code=404)
    return submission


_PVT_MEASUREMENT = re.compile(r"^(?P<metric>.+)_(?P<corner>ss|tt|ff)_(?P<temperature>-?\d+)C$")


def _pvt_results(submission: Submission) -> list[dict[str, object]]:
    measurements = (submission.result_json or {}).get("measurements", [])
    grouped: dict[str, dict[int, list[dict[str, object]]]] = {}
    for measurement in measurements:
        match = _PVT_MEASUREMENT.fullmatch(str(measurement.get("name", "")))
        if match is None:
            continue
        item = dict(measurement)
        item["label"] = match.group("metric").replace("_", " ")
        corner = match.group("corner")
        temperature = int(match.group("temperature"))
        grouped.setdefault(corner, {}).setdefault(temperature, []).append(item)

    return [
        {
            "name": corner,
            "temperatures": [
                {"value": temperature, "measurements": corner_results[temperature]}
                for temperature in sorted(corner_results)
            ],
        }
        for corner in ("ss", "tt", "ff")
        if (corner_results := grouped.get(corner))
    ]


@router.get("/submissions", response_class=HTMLResponse)
def my_submissions(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    status_filter: Annotated[str, Query(alias="status")] = "all",
) -> HTMLResponse:
    user = _current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    filters = {
        "all": (),
        "active": ("queued", "running"),
        "accepted": ("accepted",),
        "failed": ("failed", "rejected"),
    }
    if status_filter not in filters:
        raise HTTPException(status_code=404)
    conditions = [Submission.user_id == user.id]
    if filters[status_filter]:
        conditions.append(Submission.status.in_(filters[status_filter]))
    total = db.scalar(select(func.count(Submission.id)).where(*conditions)) or 0
    page_count = max(1, (total + SUBMISSIONS_PAGE_SIZE - 1) // SUBMISSIONS_PAGE_SIZE)
    if page > page_count:
        raise HTTPException(status_code=404)
    submissions = db.scalars(
        select(Submission)
        .options(selectinload(Submission.challenge))
        .where(*conditions)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .offset((page - 1) * SUBMISSIONS_PAGE_SIZE)
        .limit(SUBMISSIONS_PAGE_SIZE)
    ).all()
    return templates.TemplateResponse(
        request,
        "my_submissions.html",
        _context(
            request,
            db,
            submissions=submissions,
            page=page,
            page_count=page_count,
            status_filter=status_filter,
            total=total,
        ),
    )


@router.get("/submissions/{submission_id}", response_class=HTMLResponse)
def submission_detail(
    submission_id: int, request: Request, db: Annotated[Session, Depends(get_session)]
) -> HTMLResponse:
    submission = _owned_submission(db, submission_id, _current_user(request, db))
    return templates.TemplateResponse(
        request,
        "submission.html",
        _context(request, db, submission=submission, pvt_results=_pvt_results(submission)),
    )


@router.get("/submissions/{submission_id}/status", response_class=HTMLResponse)
def submission_status(
    submission_id: int, request: Request, db: Annotated[Session, Depends(get_session)]
) -> HTMLResponse:
    submission = _owned_submission(db, submission_id, _current_user(request, db))
    return templates.TemplateResponse(
        request,
        "_submission_status.html",
        {"submission": submission, "pvt_results": _pvt_results(submission)},
    )


@router.get("/challenges/{slug}/leaderboard", response_class=HTMLResponse)
def leaderboard(
    slug: str, request: Request, db: Annotated[Session, Depends(get_session)]
) -> HTMLResponse:
    challenge = db.scalar(
        select(Challenge).where(Challenge.slug == slug, Challenge.is_active.is_(True))
    )
    if challenge is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "leaderboard.html",
        _context(request, db, challenge=challenge, leaders=_leaderboard(db, challenge)),
    )
