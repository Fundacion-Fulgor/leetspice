"""SQLAdmin panel with session-based authentication, statistics, and leaderboard."""

from html import escape

from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .auth import read_session
from .config import Settings
from .db import SessionLocal
from .leaderboards import DIFFICULTY_WEIGHTS, global_leaderboard
from .models import Challenge, JudgeRun, Measurement, Submission, User


# ---------------------------------------------------------------------------
# Shared page layout
# ---------------------------------------------------------------------------

_CSS = """\
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; }
.admin-header { background: linear-gradient(135deg, #111815 0%, #1a2318 100%); color: #dbff3d; padding: 30px 0; }
.stat-card { background: white; border-radius: 12px; padding: 24px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.stat-card .number { font-size: 36px; font-weight: 800; color: #111815; }
.stat-card .label { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-top: 4px; }
.data-table { background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }
.data-table table { margin: 0; }
.data-table thead th { background: #111815; color: #dbff3d; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 14px 12px; border: none; white-space: nowrap; }
.data-table tbody td { padding: 12px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: middle; }
.data-table tbody tr:hover { background: #f8fff0; }
.back-link { color: #dbff3d; text-decoration: none; font-size: 13px; }
.back-link:hover { color: #fff; }
.nav-pills .nav-link { color: #555; font-size: 13px; font-weight: 600; }
.nav-pills .nav-link.active { background: #111815; color: #dbff3d; }
.rank-1 { color: #d4a017; font-weight: 800; }
.rank-2 { color: #8a8a8a; font-weight: 700; }
.rank-3 { color: #b87333; font-weight: 700; }
.medal { font-size: 18px; }
.section-title { padding: 20px 20px 10px; border-bottom: 1px solid #eee; }
.section-title h5 { margin: 0; font-weight: 700; }
.detail-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; margin: 1px; }
.detail-badge.intro { background: #e8f5e9; color: #2e7d32; }
.detail-badge.inter { background: #fff8e1; color: #ef6c00; }
.detail-badge.adv { background: #fce4ec; color: #c62828; }
.detail-badge.cap { background: #f3e5f5; color: #6a1b9a; }
.activity-item { padding: 12px 16px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 12px; font-size: 13px; }
.activity-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.activity-dot.accepted { background: #2e7d32; }
.activity-dot.failed, .activity-dot.rejected { background: #c62828; }
.activity-dot.queued, .activity-dot.running { background: #e2a723; }
"""


def _page(title: str, icon: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} \u00b7 LeetSpice Admin</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="admin-header">
  <div class="container">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <a href="/admin" class="back-link"><i class="fa-solid fa-arrow-left"></i> Back to Admin</a>
      <span style="font-size:11px;letter-spacing:2px;opacity:.6">LEETSPICE ADMIN</span>
    </div>
    <h1 style="font-weight:800;letter-spacing:-1px;margin:0"><i class="fa-solid fa-{icon}"></i> {escape(title)}</h1>
    <p style="opacity:.7;margin:8px 0 0">{escape(subtitle)}</p>
  </div>
</div>
<div class="container py-4">{body}</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

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
# Challenge Statistics view
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

            total_challenges = len(challenges)
            total_submissions = sum(s["total_submissions"] for s in stats)
            total_users = session.scalar(select(func.count(User.id))) or 0
            total_accepted = sum(s["accepted"] for s in stats)

        return HTMLResponse(_render_stats_page(
            stats, total_challenges, total_submissions, total_users, total_accepted,
        ))


# ---------------------------------------------------------------------------
# Global Leaderboard view
# ---------------------------------------------------------------------------

class GlobalLeaderboardView(BaseView):
    name = "Global Ranking"
    icon = "fa-solid fa-trophy"

    @expose("/global-ranking", methods=["GET"])
    async def global_ranking(self, request: Request) -> Response:
        with SessionLocal() as session:
            leaders = global_leaderboard(session)
            challenges = session.scalars(
                select(Challenge)
                .where(Challenge.is_active.is_(True), Challenge.is_ranked.is_(True))
                .order_by(Challenge.curriculum_order, Challenge.id)
            ).all()
            max_points = sum(
                DIFFICULTY_WEIGHTS.get(c.difficulty, 1) * 100 for c in challenges
            )
            total_users = session.scalar(select(func.count(User.id))) or 0
            users_with_submissions = session.scalar(
                select(func.count(func.distinct(Submission.user_id)))
                .where(Submission.status == "accepted")
            ) or 0

        return HTMLResponse(_render_leaderboard_page(
            leaders, challenges, max_points, total_users, users_with_submissions,
        ))


# ---------------------------------------------------------------------------
# Recent Activity view
# ---------------------------------------------------------------------------

class RecentActivityView(BaseView):
    name = "Recent Activity"
    icon = "fa-solid fa-clock-rotate-left"

    @expose("/recent-activity", methods=["GET"])
    async def recent_activity(self, request: Request) -> Response:
        with SessionLocal() as session:
            recent = session.execute(
                select(Submission, User, Challenge)
                .join(User, Submission.user_id == User.id)
                .join(Challenge, Submission.challenge_id == Challenge.id)
                .order_by(Submission.created_at.desc())
                .limit(50)
            ).all()

            # Recent registrations
            recent_users = session.scalars(
                select(User).order_by(User.created_at.desc()).limit(10)
            ).all()

            total_today = session.scalar(
                select(func.count(Submission.id))
                .where(Submission.created_at >= func.current_date())
            ) or 0
            accepted_today = session.scalar(
                select(func.count(Submission.id))
                .where(
                    Submission.created_at >= func.current_date(),
                    Submission.status == "accepted",
                )
            ) or 0

        return HTMLResponse(_render_activity_page(
            recent, recent_users, total_today, accepted_today,
        ))


# ---------------------------------------------------------------------------
# HTML renderers
# ---------------------------------------------------------------------------

def _render_stats_page(
    stats: list[dict],
    total_challenges: int,
    total_submissions: int,
    total_users: int,
    total_accepted: int,
) -> str:
    rows = ""
    for s in stats:
        c = s["challenge"]
        avg = f'{s["avg_score"]:.4g}' if s["avg_score"] is not None else "\u2014"
        best = f'{s["best_score"]:.4g}' if s["best_score"] is not None else "\u2014"
        active_badge = (
            '<span style="color:#2e7d32;font-weight:600">\u25cf Active</span>'
            if c.is_active
            else '<span style="color:#c62828;font-weight:600">\u25cf Inactive</span>'
        )
        diff_colors = {
            "introductory": "#2e7d32", "intermediate": "#ef6c00",
            "advanced": "#c62828", "capstone": "#6a1b9a",
        }
        diff_color = diff_colors.get(c.difficulty, "#555")
        rows += f"""<tr>
          <td><strong>{escape(c.title)}</strong><br><small style="color:#888">{escape(c.slug)}</small></td>
          <td>{escape(c.track)}</td>
          <td><span style="color:{diff_color};font-weight:600;text-transform:uppercase;font-size:11px">{escape(c.difficulty)}</span></td>
          <td style="text-align:center">{active_badge}</td>
          <td style="text-align:right">{s["total_submissions"]}</td>
          <td style="text-align:right"><span style="color:#2e7d32">{s["accepted"]}</span></td>
          <td style="text-align:right"><span style="color:#c62828">{s["failed"]}</span></td>
          <td style="text-align:right">{s["queued"]}</td>
          <td style="text-align:right">{s["acceptance_rate"]}%</td>
          <td style="text-align:right">{s["unique_users"]}</td>
          <td style="text-align:right">{s["users_accepted"]}</td>
          <td style="text-align:right">{avg} {escape(c.score_unit)}</td>
          <td style="text-align:right"><strong>{best}</strong> {escape(c.score_unit) if best != chr(0x2014) else ''}</td>
        </tr>"""

    overall_rate = round(total_accepted / total_submissions * 100, 1) if total_submissions > 0 else 0

    cards = f"""<div class="row g-3 mb-4">
    <div class="col-md-3"><div class="stat-card"><div class="number">{total_challenges}</div><div class="label">Active Challenges</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{total_submissions}</div><div class="label">Total Submissions</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{total_users}</div><div class="label">Registered Users</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{overall_rate}%</div><div class="label">Overall Acceptance Rate</div></div></div>
  </div>"""

    empty = '<tr><td colspan="13" style="text-align:center;color:#888;padding:40px">No submissions yet</td></tr>'
    table = f"""<div class="data-table">
    <div class="section-title"><h5><i class="fa-solid fa-list-check"></i> Per-Challenge Breakdown</h5></div>
    <div class="table-responsive"><table class="table table-sm mb-0">
      <thead><tr>
        <th>Challenge</th><th>Track</th><th>Difficulty</th><th style="text-align:center">Status</th>
        <th style="text-align:right">Submissions</th><th style="text-align:right">Accepted</th>
        <th style="text-align:right">Failed</th><th style="text-align:right">Queued</th>
        <th style="text-align:right">Accept %</th><th style="text-align:right">Users</th>
        <th style="text-align:right">Solved By</th><th style="text-align:right">Avg Score</th>
        <th style="text-align:right">Best Score</th>
      </tr></thead>
      <tbody>{rows or empty}</tbody>
    </table></div>
  </div>
  <div class="mt-3 text-center"><small style="color:#888">
    <i class="fa-solid fa-circle-info"></i>
    To activate/deactivate challenges, go to <a href="/admin/challenge/list" style="color:#d56a3a">Challenges</a>
    and edit the <strong>is_active</strong> field.
    &nbsp;|&nbsp;
    To add a new challenge, use <a href="/admin/challenge/create" style="color:#d56a3a">Create Challenge</a>.
  </small></div>"""

    return _page("Challenge Statistics", "chart-bar",
                  "Per-challenge performance metrics across all users",
                  cards + table)


def _render_leaderboard_page(
    leaders: list,
    challenges: list,
    max_points: float,
    total_users: int,
    users_with_submissions: int,
) -> str:
    cards = f"""<div class="row g-3 mb-4">
    <div class="col-md-3"><div class="stat-card"><div class="number">{len(leaders)}</div><div class="label">Ranked Students</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{total_users}</div><div class="label">Registered Users</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{users_with_submissions}</div><div class="label">With Accepted Work</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{max_points:.0f}</div><div class="label">Maximum Points</div></div></div>
  </div>"""

    # Challenge column headers
    ch_headers = ""
    for c in challenges:
        diff_cls = {"introductory": "intro", "intermediate": "inter",
                    "advanced": "adv", "capstone": "cap"}.get(c.difficulty, "")
        ch_headers += f'<th style="text-align:center;font-size:9px;max-width:80px;white-space:normal;line-height:1.2" title="{escape(c.title)}">{escape(c.title[:18])}</th>'

    rows = ""
    for leader in leaders:
        medal = ""
        rank_cls = ""
        if leader.rank == 1:
            medal = '<span class="medal">\U0001f947</span> '
            rank_cls = " rank-1"
        elif leader.rank == 2:
            medal = '<span class="medal">\U0001f948</span> '
            rank_cls = " rank-2"
        elif leader.rank == 3:
            medal = '<span class="medal">\U0001f949</span> '
            rank_cls = " rank-3"

        pct = (leader.total_points / max_points * 100) if max_points > 0 else 0
        bar_color = "#2e7d32" if pct >= 70 else "#ef6c00" if pct >= 40 else "#c62828"

        # Build per-challenge detail cells
        detail_map = {d.challenge.id: d for d in leader.details}
        ch_cells = ""
        for c in challenges:
            d = detail_map.get(c.id)
            if d:
                diff_cls = {"introductory": "intro", "intermediate": "inter",
                            "advanced": "adv", "capstone": "cap"}.get(c.difficulty, "")
                ch_cells += f'<td style="text-align:center"><span class="detail-badge {diff_cls}" title="{d.score:.4g} {escape(c.score_unit)} \u2014 {d.points:.0f} pts">{d.points:.0f}</span></td>'
            else:
                ch_cells += '<td style="text-align:center;color:#ddd">\u2014</td>'

        rows += f"""<tr>
          <td class="{rank_cls}" style="text-align:center;font-size:18px;width:50px">{medal}{leader.rank}</td>
          <td><strong>{escape(leader.user.display_name)}</strong><br><small style="color:#888">{escape(leader.user.email)}</small></td>
          <td style="text-align:right"><strong style="font-size:18px">{leader.total_points:.0f}</strong><br><small style="color:#888">/ {max_points:.0f}</small></td>
          <td style="text-align:center">{leader.completed} / {len(challenges)}</td>
          <td style="width:120px">
            <div style="background:#eee;border-radius:4px;height:8px;overflow:hidden">
              <div style="background:{bar_color};height:100%;width:{pct:.0f}%"></div>
            </div>
            <small style="color:#888;font-size:10px">{pct:.1f}%</small>
          </td>
          {ch_cells}
        </tr>"""

    empty = f'<tr><td colspan="{5 + len(challenges)}" style="text-align:center;color:#888;padding:40px">No ranked students yet. Rankings appear once a student has an accepted submission.</td></tr>'

    table = f"""<div class="data-table">
    <div class="section-title">
      <h5><i class="fa-solid fa-ranking-star"></i> Full Global Ranking</h5>
      <small style="color:#888;display:block;margin-top:4px">
        Points = percentile \u00d7 difficulty weight (introductory=1, intermediate=2, advanced=3, capstone=4).
        Higher is better. Tied students share the same rank.
      </small>
    </div>
    <div class="table-responsive"><table class="table table-sm mb-0">
      <thead><tr>
        <th style="text-align:center">Rank</th>
        <th>Student</th>
        <th style="text-align:right">Points</th>
        <th style="text-align:center">Solved</th>
        <th>Progress</th>
        {ch_headers}
      </tr></thead>
      <tbody>{rows or empty}</tbody>
    </table></div>
  </div>
  <div class="mt-3 text-center"><small style="color:#888">
    <i class="fa-solid fa-circle-info"></i>
    This is the same ranking used to determine <strong>Fundaci\u00f3n Fulgor scholarships</strong>.
    The highest-ranking students automatically earn scholarships.
  </small></div>"""

    return _page("Global Ranking", "trophy",
                  "Complete difficulty-weighted leaderboard across all challenges",
                  cards + table)


def _render_activity_page(
    recent: list,
    recent_users: list,
    total_today: int,
    accepted_today: int,
) -> str:
    cards = f"""<div class="row g-3 mb-4">
    <div class="col-md-3"><div class="stat-card"><div class="number">{total_today}</div><div class="label">Submissions Today</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{accepted_today}</div><div class="label">Accepted Today</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{len(recent_users)}</div><div class="label">Recent Registrations</div></div></div>
    <div class="col-md-3"><div class="stat-card"><div class="number">{len(recent)}</div><div class="label">Showing Last N</div></div></div>
  </div>"""

    # Recent submissions
    sub_rows = ""
    for submission, user, challenge in recent:
        status_color = {
            "accepted": "#2e7d32", "failed": "#c62828", "rejected": "#c62828",
            "queued": "#e2a723", "running": "#e2a723",
        }.get(submission.status, "#888")
        score_str = f"{submission.score:.4g} {challenge.score_unit}" if submission.score is not None else "\u2014"
        ts = submission.created_at.strftime("%Y-%m-%d %H:%M") if submission.created_at else "\u2014"
        sub_rows += f"""<tr>
          <td style="text-align:center;font-size:12px;color:#888">#{submission.id}</td>
          <td><strong>{escape(user.display_name)}</strong></td>
          <td>{escape(challenge.title)}<br><small style="color:#888">{escape(challenge.track)}</small></td>
          <td style="text-align:center"><span style="color:{status_color};font-weight:600;text-transform:uppercase;font-size:11px">{escape(submission.status)}</span></td>
          <td style="text-align:right">{score_str}</td>
          <td style="text-align:right;color:#888;font-size:12px">{ts}</td>
        </tr>"""

    empty_subs = '<tr><td colspan="6" style="text-align:center;color:#888;padding:40px">No submissions yet</td></tr>'

    submissions_table = f"""<div class="data-table mb-4">
    <div class="section-title"><h5><i class="fa-solid fa-paper-plane"></i> Last 50 Submissions</h5></div>
    <div class="table-responsive"><table class="table table-sm mb-0">
      <thead><tr>
        <th style="text-align:center">ID</th><th>User</th><th>Challenge</th>
        <th style="text-align:center">Status</th><th style="text-align:right">Score</th>
        <th style="text-align:right">Time</th>
      </tr></thead>
      <tbody>{sub_rows or empty_subs}</tbody>
    </table></div>
  </div>"""

    # Recent registrations
    user_rows = ""
    for u in recent_users:
        ts = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "\u2014"
        admin_badge = ' <span style="background:#dbff3d;color:#111815;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700">ADMIN</span>' if u.is_admin else ""
        user_rows += f"""<tr>
          <td style="text-align:center;color:#888">#{u.id}</td>
          <td><strong>{escape(u.display_name)}</strong>{admin_badge}</td>
          <td>{escape(u.email)}</td>
          <td style="text-align:right;color:#888;font-size:12px">{ts}</td>
        </tr>"""

    users_table = f"""<div class="data-table">
    <div class="section-title"><h5><i class="fa-solid fa-user-plus"></i> Recent Registrations</h5></div>
    <div class="table-responsive"><table class="table table-sm mb-0">
      <thead><tr><th style="text-align:center">ID</th><th>Name</th><th>Email</th><th style="text-align:right">Registered</th></tr></thead>
      <tbody>{user_rows or '<tr><td colspan="4" style="text-align:center;color:#888;padding:20px">No users yet</td></tr>'}</tbody>
    </table></div>
  </div>"""

    return _page("Recent Activity", "clock-rotate-left",
                  "Latest submissions and user registrations",
                  cards + submissions_table + users_table)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_admin(app, engine, settings: Settings) -> Admin:
    auth_backend = AdminAuth(settings)
    admin = Admin(
        app,
        engine,
        authentication_backend=auth_backend,
        title="LeetSpice Admin",
    )
    admin.add_view(ChallengeStatsView)
    admin.add_view(GlobalLeaderboardView)
    admin.add_view(RecentActivityView)
    admin.add_view(UserAdmin)
    admin.add_view(ChallengeAdmin)
    admin.add_view(SubmissionAdmin)
    admin.add_view(JudgeRunAdmin)
    admin.add_view(MeasurementAdmin)
    return admin
