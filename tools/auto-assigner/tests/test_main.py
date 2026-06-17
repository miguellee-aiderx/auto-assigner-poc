"""main 모듈 CLI 테스트."""

from __future__ import annotations

from pathlib import Path

from auto_assigner.main import main

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


def test_main_with_dry_run(load_fixture, tmp_path, monkeypatch):
    fixture = load_fixture("backend_intern_lgtm.json")
    event_file = tmp_path / "event.json"
    event_file.write_text(__import__("json").dumps(fixture))

    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("AUTO_ASSIGNER_CONFIG", str(CONFIG_PATH))

    # GitHubClient.fetch_pr만 mock; 나머지 쓰기는 dry_run이 막는다.
    def fake_fetch_pr(self, repo, pr_number):
        return {
            "number": 352,
            "title": "test",
            "body": "body",
            "author": "junokim-aiderx",
            "labels": [],
            "files": ["src/main.py"],
            "is_draft": False,
            "reviews": [],
        }

    monkeypatch.setattr(
        "auto_assigner.github_client.GitHubClient.fetch_pr", fake_fetch_pr
    )

    # Slack notifier는 URL 없으면 skip되므로 Slack 호출 mock 필요 없음
    code = main(["--event-file", str(event_file)])
    assert code == 0
