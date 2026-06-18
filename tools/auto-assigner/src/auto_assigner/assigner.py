"""리뷰어 지정 orchestrator.

이벤트 파싱 → GitHub API로 PR 메타데이터 조회 → 규칙 기반 리뷰어 선정
→ Review Request / Ready for Review / 라벨 추가 → Slack 알림
의 전체 흐름을 조립합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from auto_assigner.config import Config
from auto_assigner.event_parser import Event
from auto_assigner.github_client import GitHubClient
from auto_assigner.rules import AssignmentResult, assign_reviewers
from auto_assigner.slack import SlackNotifier


@dataclass(frozen=True)
class AssignerResult:
    """전체 실행 결과.

    Attributes:
        should_act: 실제로 리뷰어 지정 동작을 했는지 여부.
        skipped_reason: 동작을 하지 않은 경우 그 이유.
        assignment: 선정된 리뷰어 정보(should_act가 False면 None).
        repo: "owner/repo" 형식의 대상 repo.
        pr_number: 대상 PR 번호.
        author: PR 작성자 login(파싱된 경우).
        actions_taken: 수행하려고 한 GitHub 작업 목록.
    """

    should_act: bool
    skipped_reason: str | None
    assignment: AssignmentResult | None
    repo: str
    pr_number: int
    author: str | None
    actions_taken: list[str]


class Assigner:
    """PR 메타데이터를 읽고 규칙에 따라 리뷰어를 지정한다."""

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

    def run(self, event: Event) -> AssignerResult:
        """이벤트를 처리하고 리뷰어 지정 결과를 반환한다."""
        repo = f"{event.repo_owner}/{event.repo_name}"
        pr_number = event.pr_number
        auto_routed_label = self.config.auto_routed_label

        # 1. 트리거 검증: claude가 남긴 LGTM/APPROVE 이벤트만 처리.
        if not self._should_process(event):
            return AssignerResult(
                should_act=False,
                skipped_reason="claude가 남긴 LGTM 이벤트가 아님",
                assignment=None,
                repo=repo,
                pr_number=pr_number,
                author=None,
                actions_taken=[],
            )

        # 2. PR 메타데이터 조회.
        # payload에 mock PR 메타데이터가 있으면 우선 사용하고,
        # 실제 GitHub API로는 변경 파일과 리뷰 목록만 보완 조회.
        if event.pr_author is not None:
            author = event.pr_author
            labels = event.pr_labels or []
            title = event.pr_title
            body = event.pr_body
            is_draft = event.pr_is_draft or False
            files, reviews = self.github.fetch_files_and_reviews(repo, pr_number)
        else:
            pr_data = self.github.fetch_pr(repo, pr_number)
            author = pr_data["author"]
            labels = pr_data["labels"]
            title = pr_data["title"]
            body = pr_data["body"]
            files = pr_data["files"]
            reviews = pr_data["reviews"]
            is_draft = pr_data["is_draft"]

        # 3. 멱등 가드: 사람이 수동으로 수정한 경우를 보호.
        # auto-routed 라벨이 있으면 이 엔진은 다시 개입하지 않음.
        if auto_routed_label in labels:
            return AssignerResult(
                should_act=False,
                skipped_reason=f"{auto_routed_label} 라벨이 이미 존재",
                assignment=None,
                repo=repo,
                pr_number=pr_number,
                author=author,
                actions_taken=[],
            )

        # 4. 규칙 엔진으로 리뷰어 선정.
        assignment = assign_reviewers(
            author=author,
            labels=labels,
            title=title,
            body=body,
            files=files,
            reviews=reviews,
            config=self.config,
        )

        actions: list[str] = []

        # 5. Review Request.
        if assignment.reviewers:
            self.github.request_reviewers(
                repo=repo,
                pr_number=pr_number,
                reviewers=assignment.reviewers,
                dry_run=self.dry_run,
            )
            actions.append(f"request_reviewers={','.join(assignment.reviewers)}")

        # 6. Draft PR인 경우 Ready for Review로 전환.
        if is_draft:
            self.github.mark_ready_for_review(
                repo=repo, pr_number=pr_number, dry_run=self.dry_run
            )
            actions.append("mark_ready_for_review")

        # 7. 멱등 라벨 부착. 실패하더라도 다음 트리거에서 재개입 방지.
        self.github.add_label(
            repo=repo,
            pr_number=pr_number,
            label=auto_routed_label,
            dry_run=self.dry_run,
        )
        actions.append(f"add_label={auto_routed_label}")

        # 8. Slack 알림(dry-run에서도 전송하여 오탐/정확도를 모니터링).
        self.slack.notify(
            repo=repo,
            pr_number=pr_number,
            title=title,
            author=author,
            stage=assignment.stage,
            reviewers=assignment.reviewers,
            reason=assignment.reason,
            dry_run=self.dry_run,
        )

        return AssignerResult(
            should_act=True,
            skipped_reason=None,
            assignment=assignment,
            repo=repo,
            pr_number=pr_number,
            author=author,
            actions_taken=actions,
        )

    def _should_process(self, event: Event) -> bool:
        """claude 봇이 남긴 LGTM 이벤트인지 확인한다."""
        return event.actor == "claude" and event.is_lgtm
