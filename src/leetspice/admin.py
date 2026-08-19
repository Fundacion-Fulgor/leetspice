"""SQLAdmin panel with session-based authentication and challenge statistics."""

from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import func, select
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


# ---------------------------------------------------------------------------
# Model views
# ---------------------------------------------------------------------------

class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [User.id, User.email, User.display_name, User.is_admin, User.created_at]
    column_searchable_list = [User.email, User.display_name]
    column_sortable_list = [User.id, User.email, User.display_name, User.is_admin, User.created_at]
    form_excluded_columns = [User.password_hash, User.submissions]
    can_create = False
    can_delete = True


class ChallengeAdmin(ModelView, model=Challenge):
    name = "Challenge"
    name_plural = "Challenges"
    icon = "fa-solid fa-bolt"
    column_list = [
        Challenge.id, Challenge.slug, Challenge.title, Challenge.track,
        Challenge.difficulty, Challenge.is_active, Challenge.is_ranked,
        Challenge.curriculum_order,
    ]
    column_searchable_list = [Challenge.slug, Challenge.title, Challenge.track]
    column_sortable_list = [
        Challenge.id, Challenge.slug, Challenge.title, Challenge.track,
        Challenge.difficulty, Challenge.is_active, Challenge.curriculum_order,
    ]
    column_default_sort = [(Challenge.curriculum_order, False), (Challenge.id, False)]
    form_excluded_columns = [Challenge.submissions]
    can_create = True
    can_edit = True
    can_delete = True


class SubmissionAdmin(ModelView, model=Submission):
    name = "Submission"
    name_plural = "Submissions"
    icon = "fa-solid fa-paper-plane"
    column_list = [
        Submission.id, Submission.user_id, Submission.challenge_id,
        Submission.status, Submission.score, Submission.submission_kind,
        Submission.created_at,
    ]
    column_searchable_list = [Submission.status]
    column_sortable_list = [
        Submission.id, Submission.status, Submission.score, Submission.created_at,
    ]
    column_default_sort = (Submission.created_at, True)
    form_excluded_columns = [Submission.payload_binary]
    can_create = False
    can_delete = True


class JudgeRunAdmin(ModelView, model=JudgeRun):
    name = "Judge Run"
    name_plural = "Judge Runs"
    icon = "fa-solid fa-gavel"
    column_list = [
        JudgeRun.id, JudgeRun.submission_id, JudgeRun.status,
        JudgeRun.backend, JudgeRun.started_at, JudgeRun.finished_at,
    ]
    column_sortable_list = [JudgeRun.id, JudgeRun.status, JudgeRun.started_at]
    can_create = False
    can_delete = False


class MeasurementAdmin(ModelView, model=Measurement):
    name = "Measurement"
    name_plural = "Measurements"
    icon = "fa-solid fa-ruler"
    column_list = [
        Measurement.id, Measurement.judge_run_id, Measurement.name,
        Measurement.value, Measurement.unit, Measurement.passed,
    ]
    column_sortable_list = [Measurement.id, Measurement.name, Measurement.value]
    can_create = False
    can_delete = False


# ---------------------------------------------------------------------------
# Custom statistics view
# ---------------------------------------------------------------------------

class ChallengeStatsView(BaseView):
    name = "Challenge Stats"
    icon = "fa-solid fa-chart-bar"

    @expose("/challenge-stats", methods=["GET"])
    async def challenge_stats(self, request: Request) -> Response:
        with SessionLocal() as session:
            challenges = session.scalars(
                select(Challenge)
                .where(Challenge.is_active.is_(True))
                .order_by(Challenge.curriculum_order, Challenge.id)
            ).all()

            stats: list[dict] = []
            for challenge in challenges:
                total = session.scalar(
                    select(func.count(Submission.id))
                    .where(Submission.challenge_id == challenge.id)
                ) or 0
                accepted = session.scalar(
                    select(func.count(Submission.id))
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status == "accepted",
                    )
                ) or 0
                failed = session.scalar(
                    select(func.count(Submission.id))
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status.in_(["failed", "rejected"]),
                    )
                ) or 0
                queued = session.scalar(
                    select(func.count(Submission.id))
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status.in_(["queued", "running"]),
                    )
                ) or 0
                unique_users = session.scalar(
                    select(func.count(func.distinct(Submission.user_id)))
                    .where(Submission.challenge_id == challenge.id)
                ) or 0
                users_accepted = session.scalar(
                    select(func.count(func.distinct(Submission.user_id)))
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status == "accepted",
                    )
                ) or 0
                avg_score = session.scalar(
                    select(func.avg(Submission.score))
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status == "accepted",
                        Submission.score.is_not(None),
                    )
                )
                best_score = session.scalar(
                    select(
                        func.min(Submission.score)
                        if challenge.lower_is_better
                        else func.max(Submission.score)
                    )
                    .where(
                        Submission.challenge_id == challenge.id,
                        Submission.status == "accepted",
                        Submission.score.is_not(None),
                    )
                )
                acceptance_rate = (accepted / total * 100) if total > 0 else 0

                stats.append({
                    "challenge": challenge,
                    "total_submissions": total,
                    "accepted": accepted,
                    "failed": failed,
                    "queued": queued,
                    "unique_users": unique_users,
                    "users_accepted": users_accepted,
                    "acceptance_rate": round(acceptance_rate, 1),
                    "avg_score": round(avg_score, 4) if avg_score is not None else None,
                    "best_score": round(best_score, 4) if best_score is not None else None,
                })

            # Summary totals
            total_challenges = len(challenges)
            total_submissions = sum(s["total_submissions"] for s in stats)
            total_users = session.scalar(select(func.count(User.id))) or 0
            total_accepted = sum(s["accepted"] for s in stats)

        # Render using a simple HTML template embedded in the response
        html = _render_stats_page(stats, total_challenges, total_submissions, total_users, total_accepted)

        from starlette.responses import HTMLResponse
        return HTMLResponse(html)


def _render_stats_page(
    stats: list[dict],
    total_challenges: int,
    total_submissions: int,
    total_users: int,
    total_accepted: int,
) -> str:
    """Render the statistics dashboard as self-contained HTML."""

    rows = ""
    for s in stats:
        c = s["challenge"]
        avg = f'{s["avg_score"]:.4g}' if s["avg_score"] is not None else "—"
        best = f'{s["best_score"]:.4g}' if s["best_score"] is not None else "—"
        active_badge = (
            '<span style="color:#2e7d32;font-weight:600">● Active</span>'
            if c.is_active
            else '<span style="color:#c62828;font-weight:600">● Inactive</span>'
        )
        diff_colors = {
            "introductory": "#2e7d32",
            "intermediate": "#ef6c00",
            "advanced": "#c62828",
            "capstone": "#6a1b9a",
        }
        diff_color = diff_colors.get(c.difficulty, "#555")
        rows += f"""
        <tr>
          <td><strong>{c.title}</strong><br><small style="color:#888">{c.slug}</small></td>
          <td>{c.track}</td>
          <td><span style="color:{diff_color};font-weight:600;text-transform:uppercase;font-size:11px">{c.difficulty}</span></td>
          <td style="text-align:center">{active_badge}</td>
          <td style="text-align:right">{s["total_submissions"]}</td>
          <td style="text-align:right"><span style="color:#2e7d32">{s["accepted"]}</span></td>
          <td style="text-align:right"><span style="color:#c62828">{s["failed"]}</span></td>
          <td style="text-align:right">{s["queued"]}</td>
          <td style="text-align:right">{s["acceptance_rate"]}%</td>
          <td style="text-align:right">{s["unique_users"]}</td>
          <td style="text-align:right">{s["users_accepted"]}</td>
          <td style="text-align:right">{avg} {c.score_unit}</td>
          <td style="text-align:right"><strong>{best}</strong> {c.score_unit if best != '—' else ''}</td>
        </tr>
        """

    overall_rate = round(total_accepted / total_submissions * 100, 1) if total_submissions > 0 else 0

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Challenge Statistics · LeetSpice Admin</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; }}
  .stats-header {{ background: linear-gradient(135deg, #111815 0%, #1a2318 100%); color: #dbff3d; padding: 30px 0; }}
  .stat-card {{ background: white; border-radius: 12px; padding: 24px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .stat-card .number {{ font-size: 36px; font-weight: 800; color: #111815; }}
  .stat-card .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-top: 4px; }}
  .stats-table {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }}
  .stats-table table {{ margin: 0; }}
  .stats-table thead th {{ background: #111815; color: #dbff3d; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 14px 12px; border: none; white-space: nowrap; }}
  .stats-table tbody td {{ padding: 12px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: middle; }}
  .stats-table tbody tr:hover {{ background: #f8fff0; }}
  .back-link {{ color: #dbff3d; text-decoration: none; font-size: 13px; }}
  .back-link:hover {{ color: #fff; }}
</style>
</head>
<body>
<div class="stats-header">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <a href="/admin" class="back-link"><i class="fa-solid fa-arrow-left"></i> Back to Admin</a>
      <span style="font-size:11px;letter-spacing:2px;opacity:.6">LEETSPICE ADMIN</span>
    </div>
    <h1 style="font-weight:800;letter-spacing:-1px;margin:0"><i class="fa-solid fa-chart-bar"></i> Challenge Statistics</h1>
    <p style="opacity:.7;margin:8px 0 0">Per-challenge performance metrics across all users</p>
  </div>
</div>

<div class="container py-4">
  <div class="row g-3 mb-4">
    <div class="col-md-3">
      <div class="stat-card">
        <div class="number">{total_challenges}</div>
        <div class="label">Active Challenges</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card">
        <div class="number">{total_submissions}</div>
        <div class="label">Total Submissions</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card">
        <div class="number">{total_users}</div>
        <div class="label">Registered Users</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card">
        <div class="number">{overall_rate}%</div>
        <div class="label">Overall Acceptance Rate</div>
      </div>
    </div>
  </div>

  <div class="stats-table">
    <div style="padding:20px 20px 10px;border-bottom:1px solid #eee">
      <h5 style="margin:0;font-weight:700"><i class="fa-solid fa-list-check"></i> Per-Challenge Breakdown</h5>
    </div>
    <div class="table-responsive">
      <table class="table table-sm mb-0">
        <thead>
          <tr>
            <th>Challenge</th>
            <th>Track</th>
            <th>Difficulty</th>
            <th style="text-align:center">Status</th>
            <th style="text-align:right">Submissions</th>
            <th style="text-align:right">Accepted</th>
            <th style="text-align:right">Failed</th>
            <th style="text-align:right">Queued</th>
            <th style="text-align:right">Accept %</th>
            <th style="text-align:right">Users</th>
            <th style="text-align:right">Solved By</th>
            <th style="text-align:right">Avg Score</th>
            <th style="text-align:right">Best Score</th>
          </tr>
        </thead>
        <tbody>
          {rows if rows else '<tr><td colspan="13" style="text-align:center;color:#888;padding:40px">No submissions yet</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <div class="mt-3 text-center">
    <small style="color:#888">
      <i class="fa-solid fa-circle-info"></i>
      To activate/deactivate challenges, go to
      <a href="/admin/challenge/list" style="color:#d56a3a">Challenges</a>
      and edit the <strong>is_active</strong> field.
      &nbsp;|&nbsp;
      To add a new challenge, use <a href="/admin/challenge/create" style="color:#d56a3a">Create Challenge</a>.
    </small>
  </div>
</div>
</body>
</html>"""


def setup_admin(app, engine, settings: Settings) -> Admin:
    auth_backend = AdminAuth(settings)
    admin = Admin(
        app,
        engine,
        authentication_backend=auth_backend,
        title="LeetSpice Admin",
    )
    admin.add_view(ChallengeStatsView)
    admin.add_view(UserAdmin)
    admin.add_view(ChallengeAdmin)
    admin.add_view(SubmissionAdmin)
    admin.add_view(JudgeRunAdmin)
    admin.add_view(MeasurementAdmin)
    return admin
