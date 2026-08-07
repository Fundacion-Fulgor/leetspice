"""Cross-challenge ranking calculations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Challenge, Submission, User

DIFFICULTY_WEIGHTS = {
    "introductory": 1,
    "intermediate": 2,
    "advanced": 3,
    "capstone": 4,
}


@dataclass(frozen=True, slots=True)
class ChallengePoints:
    challenge: Challenge
    score: float
    percentile: float
    points: float


@dataclass(frozen=True, slots=True)
class GlobalLeader:
    rank: int
    user: User
    total_points: float
    completed: int
    details: tuple[ChallengePoints, ...]


def global_leaderboard(session: Session) -> list[GlobalLeader]:
    challenges = session.scalars(
        select(Challenge)
        .where(Challenge.is_active.is_(True), Challenge.is_ranked.is_(True))
        .order_by(Challenge.curriculum_order, Challenge.id)
    ).all()
    if not challenges:
        return []
    current_versions = {challenge.id: challenge.verification_version for challenge in challenges}
    submissions = session.scalars(
        select(Submission)
        .join(Submission.challenge)
        .where(
            Challenge.is_active.is_(True),
            Challenge.is_ranked.is_(True),
            Submission.status == "accepted",
            Submission.score.is_not(None),
        )
        .options(joinedload(Submission.user))
    ).all()

    best: dict[tuple[int, int], Submission] = {}
    for submission in submissions:
        if submission.verification_version != current_versions[submission.challenge_id]:
            continue
        key = (submission.user_id, submission.challenge_id)
        previous = best.get(key)
        if previous is None or (
            submission.score < previous.score
            if submission.challenge.lower_is_better
            else submission.score > previous.score
        ):
            best[key] = submission

    by_challenge: dict[int, list[Submission]] = {}
    for submission in best.values():
        by_challenge.setdefault(submission.challenge_id, []).append(submission)

    details_by_user: dict[int, list[ChallengePoints]] = {}
    users: dict[int, User] = {}
    for challenge in challenges:
        entries = by_challenge.get(challenge.id, [])
        count = len(entries)
        weight = DIFFICULTY_WEIGHTS[challenge.difficulty]
        for submission in entries:
            assert submission.score is not None
            no_better = sum(
                other.score >= submission.score
                if challenge.lower_is_better
                else other.score <= submission.score
                for other in entries
            )
            percentile = 100.0 * no_better / count
            users[submission.user_id] = submission.user
            details_by_user.setdefault(submission.user_id, []).append(
                ChallengePoints(
                    challenge=challenge,
                    score=submission.score,
                    percentile=percentile,
                    points=percentile * weight,
                )
            )

    ordered = sorted(
        (
            (user_id, sum(detail.points for detail in details), details)
            for user_id, details in details_by_user.items()
        ),
        key=lambda item: (-item[1], users[item[0]].display_name.casefold(), item[0]),
    )
    leaders = []
    previous_points = None
    rank = 0
    for position, (user_id, total, details) in enumerate(ordered, start=1):
        if previous_points is None or total != previous_points:
            rank = position
        leaders.append(
            GlobalLeader(
                rank=rank,
                user=users[user_id],
                total_points=total,
                completed=len(details),
                details=tuple(details),
            )
        )
        previous_points = total
    return leaders
