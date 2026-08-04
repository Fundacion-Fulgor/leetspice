"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from . import db
from .auth import new_session, read_session, set_session_cookie
from .config import Settings, get_settings
from .models import Challenge
from .schemas import HealthRead
from .web import router


def _seed_demo_challenge() -> None:
    with db.SessionLocal() as session:
        if session.scalar(select(Challenge.id).limit(1)) is not None:
            return
        session.add(
            Challenge(
                slug="demo-cmos-inverter",
                title="CMOS Inverter: First Switch",
                summary="Size a complementary MOS inverter for a clean digital transition.",
                description=(
                    "Build a CMOS inverter from complementary MOSFETs. The deterministic local "
                    "judge rewards low delay, power, area, and unnecessary device complexity."
                ),
                expected_subckt="inverter",
                expected_pins=["in", "out", "vdd", "vss"],
                starter_netlist=(
                    ".subckt inverter in out vdd vss\n"
                    "M1 out in vss vss nmos W=1u L=0.18u\n"
                    "M2 out in vdd vdd pmos W=2u L=0.18u\n"
                    ".ends inverter\n"
                ),
                score_unit="points",
                lower_is_better=False,
            )
        )
        session.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if str(db.engine.url) != settings.database_url:
        db.configure_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        db.create_schema()
        if settings.seed_demo:
            _seed_demo_challenge()
        yield

    application = FastAPI(title="LeetSpice", lifespan=lifespan)
    application.state.settings = settings

    @application.middleware("http")
    async def session_middleware(request: Request, call_next: object) -> Response:
        payload = read_session(request, settings)
        if not payload:
            payload = new_session(None, settings)
        request.state.session = payload
        response = await call_next(request)  # type: ignore[operator]
        set_session_cookie(response, request.state.session, settings)
        return response

    @application.get("/health", response_model=HealthRead)
    def health() -> HealthRead:
        with db.SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return HealthRead()

    application.mount(
        "/static",
        StaticFiles(directory=str(__import__("pathlib").Path(__file__).parent / "static")),
        name="static",
    )
    application.include_router(router)
    return application


app = create_app()
