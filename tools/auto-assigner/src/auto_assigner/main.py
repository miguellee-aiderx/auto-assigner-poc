"""Auto Assigner CLI entrypoint.

GitHub Actions 또는 로컬에서 이벤트 파일을 받아
전체 리뷰어 자동 지정 파이프라인을 실행합니다.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from auto_assigner.assigner import Assigner
from auto_assigner.config import Config
from auto_assigner.event_parser import load_event_from_path, parse_event
from auto_assigner.github_client import GitHubClient
from auto_assigner.slack import SlackNotifier
from auto_assigner.staged import StagedAssigner


def _bool_env(name: str, default: bool) -> bool:
    """환경 변수를 bool로 파싱한다."""
    value = os.environ.get(name, "")
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    """CLI 메인 함수."""
    parser = argparse.ArgumentParser(description="Auto assign reviewers for PRs")
    parser.add_argument(
        "--event-file",
        type=Path,
        default=os.environ.get("EVENT_FILE"),
        help="Path to GitHub webhook payload JSON",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=_bool_env("DRY_RUN", True),
        help="If set, do not write to GitHub",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        help="GitHub token for API calls",
    )
    parser.add_argument(
        "--slack-webhook-url",
        default=os.environ.get("SLACK_WEBHOOK_URL"),
        help="Slack incoming webhook URL",
    )
    parser.add_argument(
        "--config-file",
        default=os.environ.get("AUTO_ASSIGNER_CONFIG"),
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--staged-mode",
        action=argparse.BooleanOptionalAction,
        default=_bool_env("STAGED_MODE", False),
        help="If set, run staged assignment (Peer approval -> Code Reviewer)",
    )
    args = parser.parse_args(argv)

    if not args.event_file:
        print(
            "[ERROR] --event-file or EVENT_FILE environment variable is required",
            file=sys.stderr,
        )
        return 1

    # 1. 설정 로드. --config-file가 없으면 기본 config/config.yaml 사용.
    config = (
        Config.from_yaml(args.config_file) if args.config_file else Config.default()
    )

    # 2. 이벤트 파일 로드 및 파싱.
    event_name, payload = load_event_from_path(args.event_file)
    event = parse_event(payload, event_name)

    if event is None:
        print(f"[INFO] Event {event_name} is not a target; nothing to do")
        return 0

    print(
        f"[INFO] Processing {event.event_name} on "
        f"{event.repo_owner}/{event.repo_name}#{event.pr_number} by {event.actor}"
    )

    # 3. 의존성 객체 생성.
    github_client = GitHubClient(token=args.github_token)
    slack_notifier = SlackNotifier(webhook_url=args.slack_webhook_url)

    repo = f"{event.repo_owner}/{event.repo_name}"
    pr_number = event.pr_number

    # 4. 실행. staged_mode에 따라 초기 라우팅 또는 staged 라우팅 선택.
    try:
        if args.staged_mode:
            staged_assigner = StagedAssigner(
                github_client=github_client,
                slack_notifier=slack_notifier,
                config=config,
                dry_run=args.dry_run,
            )
            staged_result = staged_assigner.run(event)
            if not staged_result.should_act:
                print(f"[INFO] Skipped: {staged_result.skipped_reason}")
                return 0
            print(
                f"[INFO] Assigned Code Reviewer {staged_result.reviewers} "
                f"for PR {staged_result.repo}#{staged_result.pr_number}"
            )
            for action in staged_result.actions_taken:
                print(f"[INFO] Action: {action}")
            return 0

        initial_assigner = Assigner(
            github_client=github_client,
            slack_notifier=slack_notifier,
            config=config,
            dry_run=args.dry_run,
        )
        result = initial_assigner.run(event)
    except Exception as e:  # noqa: BLE001
        slack_notifier.notify_failure(
            repo=repo,
            pr_number=pr_number,
            error=str(e),
            dry_run=args.dry_run,
        )
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    # 5. 결과 출력 (초기 라우팅).
    if not result.should_act:
        print(f"[INFO] Skipped: {result.skipped_reason}")
        return 0

    if result.assignment is None:
        print("[ERROR] Assignment succeeded but no assignment data", file=sys.stderr)
        return 1

    print(
        f"[INFO] Assigned {result.assignment.stage} reviewers "
        f"{result.assignment.reviewers} for PR {result.repo}#{result.pr_number}"
    )
    for action in result.actions_taken:
        print(f"[INFO] Action: {action}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
