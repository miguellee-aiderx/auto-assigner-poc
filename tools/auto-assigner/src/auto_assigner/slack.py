"""Slack incoming webhook 알림.

기존 aiderx-slack-app/slack.py와 동일한 방식으로
requests.Session을 사용해 Slack incoming webhook URL로 POST합니다.
"""

from __future__ import annotations

import os

import requests


class SlackNotifier:
    """Slack webhook notifier."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
        # 세션 재사용으로 반복 호출 시 연결 비용 절감.
        self.session = requests.Session()

    def _send(self, text: str) -> None:
        """Slack에 텍스트 메시지를 전송한다.

        webhook URL이 설정되지 않으면 경고만 남기고 skip.
        Slack 전송 실패는 workflow를 중단하지 않고 로그만 남김.
        """
        if not self.webhook_url:
            print("[WARN] SLACK_WEBHOOK_URL not set; skipping Slack notification")
            return

        try:
            resp = self.session.post(self.webhook_url, json={"text": text})
            resp.raise_for_status()
            print("[INFO] Slack notification sent")
        except requests.RequestException as e:
            print(f"[ERROR] Failed to send Slack notification: {e}")

    def notify(
        self,
        *,
        repo: str,
        pr_number: int,
        title: str,
        author: str,
        stage: str,
        reviewers: list[str],
        reason: str,
        dry_run: bool,
    ) -> None:
        """리뷰어 지정 결과를 Slack 채널에 알린다.

        dry-run에서도 전송하여 6/17~6/19 기간 오탐 빈도를 측정.
        """
        mode = "DRY-RUN" if dry_run else "LIVE"
        stage_display = "Peer" if stage == "peer" else "Code Reviewer"
        reviewers_text = ", ".join(f"@{r}" for r in reviewers) if reviewers else "없음"

        pr_url = f"https://github.com/{repo}/pull/{pr_number}"
        text = (
            f"[{mode}] Auto Assign Reviewers\n"
            f"Repo: {repo}\n"
            f"PR: <{pr_url}|#{pr_number} {title}>\n"
            f"Author: @{author}\n"
            f"Stage: {stage_display}\n"
            f"Reviewers: {reviewers_text}\n"
            f"Reason: {reason}"
        )
        self._send(text)

    def notify_failure(
        self,
        *,
        repo: str,
        pr_number: int,
        error: str,
        dry_run: bool,
    ) -> None:
        """리뷰어 지정 실패 시 Slack 채널에 경고한다."""
        mode = "DRY-RUN" if dry_run else "LIVE"
        text = (
            f"[{mode}] Auto Assign Reviewers FAILED\n"
            f"Repo: {repo}\n"
            f"PR: #{pr_number}\n"
            f"Error: {error}\n"
            f"‼️사람개입이 필요할 수 있습니다."
        )
        self._send(text)
