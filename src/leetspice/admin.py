"""SQLAdmin panel with session-based authentication."""

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from .auth import read_session
from .config import Settings
from .db import SessionLocal
from .models import Challenge, JudgeRun, Measurement, Submission, User


class AdminAuth(AuthenticationBackend):
    def __init__(self, settings: Settings) -> None:
        super().__init__(secret_key=settings.secret_key)
        self._settings = settings

    async def login(self, request: Request) -> bool:
        return False

    async def logout(self, request: Request) -> bool:
        return False

    async def authenticate(self, request: Request) -> bool | Response:
        payload = read_session(request, self._settings)
        user_id = payload.get("user_id")
        if not user_id:
            return RedirectResponse(request.url_for("login_form"), status_code=302)
        with SessionLocal() as session:
            user = session.get(User, user_id)
            if not user or not user.is_admin:
                return RedirectResponse(request.url_for("login_form"), status_code=302)
        return True


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.display_name, User.is_admin, User.created_at]
    column_searchable_list = [User.email, User.display_name]
    form_excluded_columns = [User.password_hash, User.submissions]


class ChallengeAdmin(ModelView, model=Challenge):
    column_list = [
        Challenge.id, Challenge.slug, Challenge.title, Challenge.track,
        Challenge.difficulty, Challenge.is_active, Challenge.is_ranked,
    ]
    column_searchable_list = [Challenge.slug, Challenge.title]
    form_excluded_columns = [Challenge.submissions]


class SubmissionAdmin(ModelView, model=Submission):
    column_list = [
        Submission.id, Submission.user_id, Submission.challenge_id,
        Submission.status, Submission.score, Submission.created_at,
    ]
    form_excluded_columns = [Submission.payload_binary]


class JudgeRunAdmin(ModelView, model=JudgeRun):
    column_list = [
        JudgeRun.id, JudgeRun.submission_id, JudgeRun.status,
        JudgeRun.backend, JudgeRun.started_at, JudgeRun.finished_at,
    ]


class MeasurementAdmin(ModelView, model=Measurement):
    column_list = [
        Measurement.id, Measurement.judge_run_id, Measurement.name,
        Measurement.value, Measurement.unit, Measurement.passed,
    ]


def setup_admin(app, engine, settings: Settings) -> Admin:
    auth_backend = AdminAuth(settings)
    admin = Admin(app, engine, authentication_backend=auth_backend)
    admin.add_view(UserAdmin)
    admin.add_view(ChallengeAdmin)
    admin.add_view(SubmissionAdmin)
    admin.add_view(JudgeRunAdmin)
    admin.add_view(MeasurementAdmin)
    return admin
