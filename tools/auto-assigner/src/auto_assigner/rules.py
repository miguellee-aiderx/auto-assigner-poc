"""리뷰어 지정 규칙 엔진.

요약 문서의 '라우팅 규칙'을 코드로 구현합니다.
- 인턴 PR → Peer 2명 지정
- 정직원/MLops/DevOps/Code Reviewer/ian → Code Reviewer 직행
- DevOps 키워드 → han 후보 추가
- skip-peer-review 라벨 → Peer 생략

실제 팀/역할/가중치는 config/config.yaml에서 관리됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auto_assigner.config import Config
from auto_assigner.selector import select_code_reviewers, select_peers


@dataclass(frozen=True)
class AssignmentResult:
    """리뷰어 지정 결과.

    Attributes:
        stage: "peer" 또는 "code_reviewer". 현재 단계를 나타냄.
        reviewers: 실제로 지정할 GitHub login 목록.
        reason: 왜 이렇게 선정되었는지 사람이 readable한 설명.
        skip_peer: skip-peer-review 라벨이 있었는지 여부.
        is_devops: DevOps 키워드가 감지되었는지 여부.
    """

    stage: str
    reviewers: list[str]
    reason: str
    skip_peer: bool
    is_devops: bool


def _normalize(text: str | None) -> str:
    """대소문자 구분 없는 검색을 위해 소문자로 정규화한다."""
    if not text:
        return ""
    return text.lower()


def _detect_devops(
    title: str | None, body: str | None, files: list[str], config: Config
) -> bool:
    """PR 제목/본문/변경 파일에 DevOps 키워드가 포함되어 있는지 확인한다.

    키워드 매칭 시 단어 경계(공백, /, _, -)를 고려하여
    'cd'가 'abcd'처럼 잘못 매칭되는 false positive를 줄입니다.
    """
    haystack = _normalize(title) + " " + _normalize(body)
    haystack += " " + " ".join(f.lower() for f in files)

    # 키워드 양옆에 경계 문자를 추가해 단어 단위 매칭 수행.
    # 예: "ci/cd" → " ci cd " 와 " ci " 매칭 가능.
    # 파일 확장자(예: "ci.yml")에서도 분리되도록 "."도 경계로 처리.
    bounded_haystack = (
        f" {haystack} "
        .replace("/", " ")
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", " ")
    )

    for keyword in config.devops_keywords:
        # 공백이 포함된 키워드(예: "docker compose")는 bounded_haystack에서 그대로 검색.
        if " " in keyword:
            if f" {keyword} " in bounded_haystack:
                return True
            continue

        # 단일 토큰 키워드는 공백 경계 기준으로 검색.
        if f" {keyword} " in bounded_haystack:
            return True

    return False


def _has_label(labels: list[str], target: str) -> bool:
    """라벨 목록에서 target 라벨 존재 여부를 대소문자 구분 없이 확인한다."""
    return any(label.lower() == target.lower() for label in labels)


def _already_approved(reviews: list[dict[str, Any]], reviewers: set[str]) -> set[str]:
    """리뷰 목록에서 이미 APPROVED 상태인 사용자의 login 집합을 반환한다.

    GitHub API 응답 형식에 따라 author 또는 user 필드에서 login을 추출.
    """
    approved: set[str] = set()
    for review in reviews:
        if review.get("state") == "APPROVED":
            login = review.get("author", {}).get("login") or review.get("user", {}).get("login")
            if login:
                approved.add(login)
    return approved


def assign_reviewers(
    author: str,
    labels: list[str],
    title: str | None,
    body: str | None,
    files: list[str],
    reviews: list[dict[str, Any]],
    *,
    config: Config,
) -> AssignmentResult:
    """작성자 역할과 PR 정보를 바탕으로 리뷰어를 선정한다.

    Args:
        author: PR 작성자 GitHub login.
        labels: PR에 붙은 라벨 이름 목록.
        title: PR 제목.
        body: PR 본문.
        files: 변경된 파일 경로 목록.
        reviews: PR에 달린 리뷰 목록(이미 승인한 사람을 제외하기 위해 사용).
        config: YAML에서 로드한 설정 객체.
    """
    role = config.get_role(author)
    team = config.get_team_config(role)

    skip_peer = _has_label(labels, config.skip_peer_label)
    is_devops = _detect_devops(title, body, files, config)

    # 작성자 본인과 이미 승인한 리뷰어는 후보에서 제외.
    approved = _already_approved(reviews, set())

    # Peer 풀이 있고 skip-peer-review 라벨이 없으면 Peer 단계로 진행.
    if team.peer_pool and not skip_peer:
        exclude = {author} | approved
        peers = select_peers(
            team.peer_pool, exclude=exclude, count=config.peer_count
        )

        # Peer 후보가 0명이면 Code Reviewer로 직행.
        if not peers:
            skip_peer = True
        else:
            reason = f"{role} 작성자: Peer {len(peers)}명 지정"
            if len(peers) < config.peer_count:
                reason += f" (후보 부족: 목표 {config.peer_count}명, 가능 {len(peers)}명)"
            return AssignmentResult(
                stage=config.STAGE_PEER,
                reviewers=peers,
                reason=reason,
                skip_peer=skip_peer,
                is_devops=is_devops,
            )

    # Peer 단계가 아닌 경우 Code Reviewer를 직행 선정.
    candidate_weights = dict(team.code_reviewer_weights)

    # DevOps 키워드가 감지되면 han 같은 DevOps 후보를 추가.
    # 이미 가중치 맵에 있으면 기존 가중치를 유지하여 실측 가중치를 존중.
    if is_devops:
        candidate_weights = _merge_devops_candidates(
            candidate_weights, team.devops_candidates
        )

    exclude = {author} | approved
    reviewers = select_code_reviewers(candidate_weights, exclude=exclude, count=1)
    reason = f"{role} 작성자: Code Reviewer 직행"
    if is_devops:
        reason += " (DevOps 키워드 감지)"
    if skip_peer:
        reason += " (skip-peer-review 라벨)"

    return AssignmentResult(
        stage=config.STAGE_CODE_REVIEWER,
        reviewers=reviewers,
        reason=reason,
        skip_peer=skip_peer,
        is_devops=is_devops,
    )


def _merge_devops_candidates(
    weights: dict[str, int], devops_candidates: frozenset[str]
) -> dict[str, int]:
    """DevOps 후보를 Code Reviewer 가중치 맵에 병합한다.

    새로 추가되는 후보는 기본 가중치 1을 부여.
    """
    merged = dict(weights)
    for candidate in devops_candidates:
        if candidate not in merged:
            merged[candidate] = 1
    return merged
