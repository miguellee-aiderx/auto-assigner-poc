"""Slack notifier 테스트."""

from __future__ import annotations

from auto_assigner.slack import SlackNotifier


class CapturingSlackNotifier(SlackNotifier):
    """웹훅 전송 대신 전송 텍스트를 캡처하는 fake notifier."""

    def __init__(self):
        super().__init__(webhook_url="http://fake-webhook")
        self.captured_texts: list[str] = []

    def _send(self, text: str) -> None:
        self.captured_texts.append(text)


def test_notify_includes_pr_link_and_title():
    notifier = CapturingSlackNotifier()

    notifier.notify(
        repo="miguellee-aiderx/auto-assigner-poc",
        pr_number=1,
        title="[TEST] PR #1 for auto-assigner poc",
        author="miguellee-aiderx",
        stage="peer",
        reviewers=["alice-aiderx", "bob-aiderx"],
        reason="인턴 작성자: Peer Review 2명 지정",
        dry_run=True,
    )

    assert len(notifier.captured_texts) == 1
    text = notifier.captured_texts[0]

    assert "[DRY-RUN] Auto Assign Reviewers" in text
    assert "<https://github.com/miguellee-aiderx/auto-assigner-poc/pull/1|#1 [TEST] PR #1 for auto-assigner poc>" in text
    assert "Reviewers: @alice-aiderx, @bob-aiderx" in text
    assert "Stage: Peer" in text


def test_notify_shows_empty_reviewers_as_none():
    notifier = CapturingSlackNotifier()

    notifier.notify(
        repo="miguellee-aiderx/auto-assigner-poc",
        pr_number=2,
        title="No peers available",
        author="wanny-aiderx",
        stage="code_reviewer",
        reviewers=[],
        reason="Peer 후보 부족: Code Reviewer 직행",
        dry_run=True,
    )

    text = notifier.captured_texts[0]
    assert "Reviewers: 없음" in text


def test_notify_failure_includes_repo_and_pr():
    notifier = CapturingSlackNotifier()

    notifier.notify_failure(
        repo="miguellee-aiderx/auto-assigner-poc",
        pr_number=3,
        error="No matching author role",
        dry_run=False,
    )

    text = notifier.captured_texts[0]
    assert "[LIVE] Auto Assign Reviewers FAILED" in text
    assert "PR: #3" in text
    assert "No matching author role" in text
    assert "사람개입이 필요할 수 있습니다" in text
