"""GitHub webhook payload 파싱.

GitHub Actions에서 발생하는 issue_comment / pull_request_review 이벤트를
auto-assigner 내부에서 다룰 수 있는 정규화된 Event 객체로 변환합니다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Event:
    """정규화된 GitHub 이벤트.

    Attributes:
        event_name: 원본 GitHub 이벤트 이름(issue_comment, pull_request_review 등).
        repo_owner: repo owner 조직/사용자 이름.
        repo_name: repo 이름.
        pr_number: PR 번호.
        actor: 이벤트를 발생시킨 GitHub login.
        is_lgtm: 본문에 LGTM 문자열이 포함되어 있는지 여부.
        raw: 원본 JSON payload(디버깅/확장용).
    """

    event_name: str
    repo_owner: str
    repo_name: str
    pr_number: int
    actor: str
    is_lgtm: bool
    raw: dict[str, Any]


def _extract_repo(event: dict[str, Any]) -> tuple[str, str]:
    """repository 객체에서 owner/repo 이름을 추출한다."""
    repo = event.get("repository", {})
    full_name = repo.get("full_name", "")
    if "/" in full_name:
        owner, name = full_name.split("/", 1)
        return owner, name
    # full_name이 없는 경우를 대비해 owner/login과 name을 각각 조회.
    return repo.get("owner", {}).get("login", ""), repo.get("name", "")


def _contains_lgtm(text: str | None) -> bool:
    """텍스트에 LGTM(대소문자 무관)이 포함되어 있는지 확인한다."""
    if not text:
        return False
    return "LGTM" in text.upper()


def parse_issue_comment(event: dict[str, Any]) -> Event | None:
    """issue_comment.created 이벤트 중 PR 코멘트만 파싱한다.

    일반 issue 코멘트는 PR이 아니므로 무시.
    """
    if event.get("action") != "created":
        return None

    issue = event.get("issue", {})
    if not issue.get("pull_request"):
        return None

    comment = event.get("comment", {})
    actor = comment.get("user", {}).get("login", "")
    body = comment.get("body", "")

    owner, name = _extract_repo(event)
    pr_number = issue.get("number", 0)

    return Event(
        event_name="issue_comment",
        repo_owner=owner,
        repo_name=name,
        pr_number=pr_number,
        actor=actor,
        is_lgtm=_contains_lgtm(body),
        raw=event,
    )


def parse_pull_request_review(event: dict[str, Any]) -> Event | None:
    """pull_request_review.submitted 이벤트를 파싱한다.

    Claude가 approve 상태의 review에 LGTM을 적은 경우에만 처리 대상.
    """
    if event.get("action") != "submitted":
        return None

    review = event.get("review", {})
    actor = review.get("user", {}).get("login", "")
    state = review.get("state", "")
    body = review.get("body", "")

    pr = event.get("pull_request", {})
    owner, name = _extract_repo(event)
    pr_number = pr.get("number", 0)

    is_lgtm = state == "APPROVED" and _contains_lgtm(body)

    return Event(
        event_name="pull_request_review",
        repo_owner=owner,
        repo_name=name,
        pr_number=pr_number,
        actor=actor,
        is_lgtm=is_lgtm,
        raw=event,
    )


def parse_event(event: dict[str, Any], event_name: str) -> Event | None:
    """이벤트 이름에 따라 적절한 파서를 선택한다.

    지원하지 않는 이벤트는 None을 반환하여 상위에서 무시.
    """
    if event_name == "issue_comment":
        return parse_issue_comment(event)
    if event_name == "pull_request_review":
        return parse_pull_request_review(event)
    return None


def load_event_from_path(path: str | Path) -> tuple[str, dict[str, Any]]:
    """JSON 파일에서 이벤트 payload를 로드하고 이벤트 이름을 결정한다.

    우선순위:
    1. payload 내부의 __event_name(로컬 테스트용 override).
    2. GITHUB_EVENT_NAME 환경 변수(GitHub Actions 제공).
    3. unknown.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    event_name = (
        data.get("__event_name")
        or os.environ.get("GITHUB_EVENT_NAME", "unknown")
    )
    return event_name, data
