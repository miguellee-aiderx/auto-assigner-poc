"""staged 모듈 테스트."""

from __future__ import annotations

from auto_assigner.config import Config
from auto_assigner.event_parser import Event
from auto_assigner.github_client import GitHubClient
from auto_assigner.slack import SlackNotifier
from auto_assigner.staged import StagedAssigner

CONFIG = Config.default()


class FakeGitHubClient(GitHubClient):
    """GitHub API 호출을 기록하는 fake client."""

    def __init__(self, pr_data: dict):
        super().__init__(token="fake")
        self.pr_data = pr_data
        self.calls: list[tuple[str, dict]] = []

    def fetch_pr(self, repo: str, pr_number: int) -> dict:
        return self.pr_data

    def request_reviewers(
        self, repo: str, pr_number: int, reviewers: list[str], *, dry_run: bool
    ) -> None:
        self.calls.append(("request_reviewers", {"reviewers": reviewers, "dry_run": dry_run}))

    def mark_ready_for_review(self, repo: str, pr_number: int, *, dry_run: bool) -> None:
        self.calls.append(("mark_ready_for_review", {"dry_run": dry_run}))

    def add_label(self, repo: str, pr_number: int, label: str, *, dry_run: bool) -> None:
        self.calls.append(("add_label", {"label": label, "dry_run": dry_run}))


class FakeSlackNotifier(SlackNotifier):
    """Slack 호출을 기록하는 fake notifier."""

    def __init__(self):
        super().__init__(webhook_url="http://fake")
        self.messages: list[dict] = []

    def notify(self, *, repo, pr_number, title, author, stage, reviewers, reason, dry_run) -> None:
        self.messages.append(
            {
                "repo": repo,
                "pr_number": pr_number,
                "title": title,
                "author": author,
                "stage": stage,
                "reviewers": reviewers,
                "reason": reason,
                "dry_run": dry_run,
            }
        )


def _make_event(actor: str = "claude") -> Event:
    return Event(
        event_name="pull_request_review",
        repo_owner="aiderx-corp",
        repo_name="a2-adm",
        pr_number=352,
        actor=actor,
        is_lgtm=True,
        raw={},
    )


def _make_pr_data(
    author: str,
    labels: list[str],
    reviews: list[dict],
    is_draft: bool = False,
) -> dict:
    return {
        "number": 352,
        "title": "test",
        "body": "body",
        "author": author,
        "labels": labels,
        "files": ["src/main.py"],
        "is_draft": is_draft,
        "reviews": reviews,
    }


def test_staged_assigns_code_reviewer_when_peers_approved():
    pr_data = _make_pr_data(
        author="junokim-aiderx",
        labels=["auto-routed"],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
            {"state": "APPROVED", "author": {"login": "sophiepark-aiderx"}},
        ],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=True)

    result = assigner.run(_make_event())

    assert result.should_act is True
    assert len(result.reviewers) == 1
    assert result.reviewers[0] in CONFIG.code_reviewer_weights

    actions = [c[0] for c in fake_github.calls]
    assert "request_reviewers" in actions
    assert len(fake_slack.messages) == 1


def test_staged_skips_when_auto_routed_label_missing():
    pr_data = _make_pr_data(
        author="junokim-aiderx",
        labels=[],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
            {"state": "APPROVED", "author": {"login": "sophiepark-aiderx"}},
        ],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(_make_event())

    assert result.should_act is False
    assert "auto-routed" in (result.skipped_reason or "")
    assert len(fake_github.calls) == 0


def test_staged_skips_when_skip_peer_label_present():
    pr_data = _make_pr_data(
        author="junokim-aiderx",
        labels=["auto-routed", "skip-peer-review"],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
            {"state": "APPROVED", "author": {"login": "sophiepark-aiderx"}},
        ],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(_make_event())

    assert result.should_act is False
    assert "skip-peer-review" in (result.skipped_reason or "")


def test_staged_skips_when_only_one_peer_approved():
    pr_data = _make_pr_data(
        author="junokim-aiderx",
        labels=["auto-routed"],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
        ],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(_make_event())

    assert result.should_act is False
    assert "Peer 승인 부족" in (result.skipped_reason or "")


def test_staged_skips_when_code_reviewer_already_approved():
    pr_data = _make_pr_data(
        author="junokim-aiderx",
        labels=["auto-routed"],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
            {"state": "APPROVED", "author": {"login": "sophiepark-aiderx"}},
            {"state": "APPROVED", "author": {"login": "lucaskim-aiderx"}},
        ],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(_make_event())

    assert result.should_act is False
    assert "Code Reviewer가 이미 지정/승인됨" in (result.skipped_reason or "")


def test_staged_skips_non_intern_author():
    pr_data = _make_pr_data(
        author="wannykim-aiderx",
        labels=["auto-routed"],
        reviews=[{"state": "APPROVED", "author": {"login": "tonychoi-aiderx"}}],
    )

    fake_github = FakeGitHubClient(pr_data)
    fake_slack = FakeSlackNotifier()
    assigner = StagedAssigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(_make_event())

    assert result.should_act is False
    assert "Peer 풀이 없음" in (result.skipped_reason or "")
