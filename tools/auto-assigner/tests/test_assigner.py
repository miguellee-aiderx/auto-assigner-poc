"""assigner orchestrator 테스트."""

from __future__ import annotations

from auto_assigner.assigner import Assigner
from auto_assigner.config import Config
from auto_assigner.event_parser import parse_event
from auto_assigner.github_client import GitHubClient
from auto_assigner.slack import SlackNotifier

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


def _make_pr_data(author: str, labels: list[str], is_draft: bool = False) -> dict:
    return {
        "number": 352,
        "title": "test",
        "body": "body",
        "author": author,
        "labels": labels,
        "files": ["src/main.py"],
        "is_draft": is_draft,
        "reviews": [],
    }


def test_assigner_requests_peers_and_label(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    event = parse_event(payload, "issue_comment")

    fake_github = FakeGitHubClient(_make_pr_data("junokim-aiderx", []))
    fake_slack = FakeSlackNotifier()
    assigner = Assigner(fake_github, fake_slack, config=CONFIG, dry_run=True)

    result = assigner.run(event)

    assert result.should_act is True
    assert result.assignment.stage == CONFIG.STAGE_PEER
    assert len(result.assignment.reviewers) == 2

    actions = [c[0] for c in fake_github.calls]
    assert "request_reviewers" in actions
    assert "add_label" in actions
    assert len(fake_slack.messages) == 1


def test_assigner_skips_if_auto_routed_label_exists(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    event = parse_event(payload, "issue_comment")

    fake_github = FakeGitHubClient(_make_pr_data("junokim-aiderx", ["auto-routed"]))
    fake_slack = FakeSlackNotifier()
    assigner = Assigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(event)

    assert result.should_act is False
    assert "auto-routed" in (result.skipped_reason or "")
    assert len(fake_github.calls) == 0
    assert len(fake_slack.messages) == 0


def test_assigner_marks_ready_for_review_for_draft(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    event = parse_event(payload, "issue_comment")

    fake_github = FakeGitHubClient(_make_pr_data("junokim-aiderx", [], is_draft=True))
    fake_slack = FakeSlackNotifier()
    assigner = Assigner(fake_github, fake_slack, config=CONFIG, dry_run=True)

    assigner.run(event)

    actions = [c[0] for c in fake_github.calls]
    assert "mark_ready_for_review" in actions


def test_assigner_ignores_non_claude_actor(load_fixture):
    payload = load_fixture("backend_intern_lgtm.json")
    payload["comment"]["user"]["login"] = "someone"
    event = parse_event(payload, "issue_comment")

    fake_github = FakeGitHubClient(_make_pr_data("junokim-aiderx", []))
    fake_slack = FakeSlackNotifier()
    assigner = Assigner(fake_github, fake_slack, config=CONFIG, dry_run=False)

    result = assigner.run(event)

    assert result.should_act is False
    assert len(fake_github.calls) == 0
