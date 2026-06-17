"""Peer 승인 완료 후 Code Reviewer 자동 지정 (staged mode).

인턴 PR의 경우 1차 라우팅에서 Peer 리뷰어가 지정되고,
Peer 리뷰어들이 모두 APPROVED 상태가 되면 본 모듈이 Code Reviewer를 자동 지정합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auto_assigner.config import Config
from auto_assigner.event_parser import Event
from auto_assigner.github_client import GitHubClient
from auto_assigner.rules import _detect_devops, _merge_devops_candidates
from auto_assigner.selector import select_code_reviewers
from auto_assigner.slack import SlackNotifier


@dataclass(frozen=True)
class StagedResult:
    """staged 모드 실행 결과."""

    should_act: bool
    skipped_reason: str | None
    reviewers: list[str]
    repo: str
    pr_number: int
    author: str | None
    actions_taken: list[str]


class StagedAssigner:
    """Peer 승인 후 Code Reviewer를 자동 지정한다."""

    def __init__(
        self,
        github_client: GitHubClient,
        slack_notifier: SlackNotifier,
        *,
        config: Config,
        dry_run: bool,
    ):
        self.github = github_client
        self.slack = slack_notifier
        self.config = config
        self.dry_run = dry_run

    def run(self, event: Event) -> StagedResult:
        """이벤트를 처리한다."""
        repo = f"{event.repo_owner}/{event.repo_name}"
        pr_number = event.pr_number

        pr_data = self.github.fetch_pr(repo, pr_number)
        author = pr_data["author"]
        labels = pr_data["labels"]
        title = pr_data["title"]
        body = pr_data["body"]
        files = pr_data["files"]
        reviews = pr_data["reviews"]

        auto_routed_label = self.config.auto_routed_label
        skip_peer_label = self.config.skip_peer_label
        code_reviewer_assigned_label = self.config.code_reviewer_assigned_label

        # 0. 멱등 가드: Code Reviewer가 이미 지정된 PR은 재실행 방지.
        # 동시성 race로 인한 CR 중복 지정을 막기 위해 라벨 기반 원자성 사용.
        if code_reviewer_assigned_label in labels:
            return StagedResult(
                should_act=False,
                skipped_reason=f"{code_reviewer_assigned_label} 라벨이 이미 존재",
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 1. 멱등 가드: 1차 라우팅이 실행된 PR만 staged 대상.
        if auto_routed_label not in labels:
            return StagedResult(
                should_act=False,
                skipped_reason=f"{auto_routed_label} 라벨이 없어 1차 라우팅 미실행",
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 2. skip-peer-review 라벨이 있으면 이미 1차에서 CR 직행됨.
        if skip_peer_label in labels:
            return StagedResult(
                should_act=False,
                skipped_reason=f"{skip_peer_label} 라벨로 Peer 단계 생략됨",
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 3. author 역할에 따른 Peer 풀 확인. Peer 풀이 없으면 staged 대상 아님.
        role = self.config.get_role(author)
        team = self.config.get_team_config(role)
        peer_pool = team.peer_pool
        if not peer_pool:
            return StagedResult(
                should_act=False,
                skipped_reason=f"{role} 작성자는 Peer 풀이 없음",
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 4. Peer 풀 내 승인 현황 확인.
        approved_peers = self._approved_in_pool(peer_pool, reviews)
        required_peers = min(self.config.peer_count, len(peer_pool))

        if len(approved_peers) < required_peers:
            return StagedResult(
                should_act=False,
                skipped_reason=(
                    f"Peer 승인 부족: {len(approved_peers)}/{required_peers} "
                    f"(approved={sorted(approved_peers)})"
                ),
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 5. 이미 Code Reviewer가 지정/승인되어 있으면 skip.
        if self._has_active_code_reviewer(reviews):
            return StagedResult(
                should_act=False,
                skipped_reason="Code Reviewer가 이미 지정/승인됨",
                reviewers=[],
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 6. Code Reviewer 선정.
        is_devops = _detect_devops(title, body, files, self.config)
        candidate_weights = dict(team.code_reviewer_weights)
        if is_devops:
            candidate_weights = _merge_devops_candidates(
                candidate_weights, team.devops_candidates
            )

        # Peer 승인자와 작성자는 후보에서 제외.
        exclude = {author} | approved_peers
        reviewers = select_code_reviewers(candidate_weights, exclude=exclude, count=1)

        # 7. Review Request.
        self.github.request_reviewers(
            repo=repo,
            pr_number=pr_number,
            reviewers=reviewers,
            dry_run=self.dry_run,
        )

        actions = [f"request_reviewers={','.join(reviewers)}"]

        # 8. Code Reviewer 지정 멱등 라벨 부착.
        self.github.add_label(
            repo=repo,
            pr_number=pr_number,
            label=code_reviewer_assigned_label,
            dry_run=self.dry_run,
        )
        actions.append(f"add_label={code_reviewer_assigned_label}")

        # 9. Slack 알림.
        reason = f"Peer {len(approved_peers)}명 승인 완료로 Code Reviewer 자동 지정"
        if is_devops:
            reason += " (DevOps 키워드 감지)"
        self.slack.notify(
            repo=repo,
            pr_number=pr_number,
            title=title,
            author=author,
            stage=self.config.STAGE_CODE_REVIEWER,
            reviewers=reviewers,
            reason=reason,
            dry_run=self.dry_run,
        )

        return StagedResult(
            should_act=True,
            skipped_reason=None,
            reviewers=reviewers,
            repo=repo,
            pr_number=pr_number,
            author=author,
            actions_taken=actions,
        )

    def _approved_in_pool(
        self, peer_pool: frozenset[str], reviews: list[dict[str, Any]]
    ) -> set[str]:
        """Peer 풀 내에서 APPROVED 상태인 리뷰어 login 집합을 반환한다."""
        approved: set[str] = set()
        for review in reviews:
            if review.get("state") != "APPROVED":
                continue
            login = review.get("author", {}).get("login") or review.get("user", {}).get("login")
            if login and login in peer_pool:
                approved.add(login)
        return approved

    def _has_active_code_reviewer(self, reviews: list[dict[str, Any]]) -> bool:
        """Code Reviewer 후보가 이미 APPROVED 상태인지 확인한다.

        requestedReviewers는 gh pr view --json reviews에 포함되지 않으므로
        일단 reviews 기반으로만 판단. 추가 개선이 필요하면 fetch_pr 필드 확장.
        """
        code_reviewers = set(self.config.code_reviewer_weights.keys())
        for review in reviews:
            login = review.get("author", {}).get("login") or review.get("user", {}).get("login")
            if login in code_reviewers and review.get("state") == "APPROVED":
                return True
        return False
