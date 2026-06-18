"""GitHub API 클라이언트.

GitHub CLI(`gh`)를 subprocess로 호출하여 PR 메타데이터를 조회하고,
리뷰어 지정 / Ready for Review / 라벨 추가를 수행합니다.
GitHub Actions runner에는 `gh`가 기본 설치되어 있어 별도 의존성이 필요 없습니다.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class GitHubClient:
    """gh CLI를 사용하는 GitHub API 클라이언트."""

    def __init__(self, token: str | None = None):
        self.token = token

    def fetch_pr(self, repo: str, pr_number: int) -> dict[str, Any]:
        """PR 메타데이터를 조회하여 assigner가 사용하는 형식으로 반환한다."""
        # gh pr view --json으로 한 번에 필요한 필드를 조회.
        fields = [
            "number",
            "title",
            "body",
            "author",
            "labels",
            "files",
            "isDraft",
            "reviews",
        ]
        out = self._run_gh([
            "pr", "view", str(pr_number),
            "--repo", repo,
            "--json", ",".join(fields),
        ])
        data = json.loads(out)

        author_login = data.get("author", {}).get("login", "")
        labels = [label["name"] for label in data.get("labels", [])]
        files = [f.get("path", "") for f in data.get("files", [])]
        reviews = data.get("reviews", [])

        return {
            "number": data.get("number", pr_number),
            "title": data.get("title"),
            "body": data.get("body"),
            "author": author_login,
            "labels": labels,
            "files": files,
            "is_draft": data.get("isDraft", False),
            "reviews": reviews,
        }

    def fetch_files_and_reviews(
        self,
        repo: str,
        pr_number: int,
        raw_event: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """변경 파일 목록과 리뷰 목록을 조회한다.

        payload에 mock files/reviews가 있으면 GitHub API 조회를 생략하고
        그것을 사용한다. 그렇지 않으면 gh pr view로 조회.
        """
        if raw_event:
            pr = raw_event.get("pull_request", {})
            raw_files = pr.get("files", [])
            raw_reviews = pr.get("reviews", [])
            if raw_files or raw_reviews:
                files = [
                    f.get("path", "") if isinstance(f, dict) else str(f)
                    for f in raw_files
                ]
                reviews = [r for r in raw_reviews if isinstance(r, dict)]
                return files, reviews

        fields = ["files", "reviews"]
        out = self._run_gh([
            "pr", "view", str(pr_number),
            "--repo", repo,
            "--json", ",".join(fields),
        ])
        data = json.loads(out)
        files = [f.get("path", "") for f in data.get("files", [])]
        reviews = data.get("reviews", [])
        return files, reviews

    def request_reviewers(
        self,
        repo: str,
        pr_number: int,
        reviewers: list[str],
        *,
        dry_run: bool,
    ) -> None:
        """PR에 리뷰어를 지정한다."""
        if dry_run:
            print(f"[DRY-RUN] Would request reviewers {reviewers} on {repo}#{pr_number}")
            return

        # GitHub REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers
        self._run_gh([
            "api",
            f"repos/{repo}/pulls/{pr_number}/requested_reviewers",
            "--method", "POST",
            "--input", "-",
        ], input=json.dumps({"reviewers": reviewers}))

    def mark_ready_for_review(
        self, repo: str, pr_number: int, *, dry_run: bool
    ) -> None:
        """Draft PR을 Ready for Review 상태로 변경한다."""
        if dry_run:
            print(f"[DRY-RUN] Would mark {repo}#{pr_number} as ready for review")
            return

        # GitHub REST API: PATCH /repos/{owner}/{repo}/pulls/{pull_number}
        self._run_gh([
            "api",
            f"repos/{repo}/pulls/{pr_number}",
            "--method", "PATCH",
            "--input", "-",
        ], input=json.dumps({"draft": False}))

    def add_label(
        self, repo: str, pr_number: int, label: str, *, dry_run: bool
    ) -> None:
        """PR(Issue)에 라벨을 추가한다."""
        if dry_run:
            print(f"[DRY-RUN] Would add label '{label}' to {repo}#{pr_number}")
            return

        # GitHub REST API: POST /repos/{owner}/{repo}/issues/{issue_number}/labels
        # PR도 issue이므로 동일 endpoint 사용.
        self._run_gh([
            "api",
            f"repos/{repo}/issues/{pr_number}/labels",
            "--method", "POST",
            "--input", "-",
        ], input=json.dumps({"labels": [label]}))

    def _run_gh(
        self, args: list[str], input: str | None = None
    ) -> str:
        """gh CLI 명령을 실행한다.

        Note:
            env={} 대신 os.environ.copy()를 사용하여 PATH 등 기존 환경을 유지.
            그렇지 않으면 runner에서 `gh` 바이너리를 찾지 못할 수 있음.
        """
        env = os.environ.copy()
        if self.token:
            env["GH_TOKEN"] = self.token
        result = subprocess.run(
            ["gh", *args],
            input=input,
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return result.stdout
