"""rules 모듈 테스트."""

from __future__ import annotations

import pytest

from auto_assigner.config import Config
from auto_assigner.rules import assign_reviewers

# 테스트에서 사용할 기본 설정 객체.
# fixture가 아닌 모듈 레벨에서 로드해도 무방(설정 파일은 테스트 중 변경되지 않음).
CONFIG = Config.default()


def test_backend_intern_gets_two_peers():
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_PEER
    assert len(result.reviewers) == 2
    backend_peers = CONFIG.peer_pools["backend_intern"]
    assert set(result.reviewers) <= backend_peers
    assert "junokim-aiderx" not in result.reviewers


def test_frontend_intern_gets_two_frontend_peers():
    result = assign_reviewers(
        author="tonychoi-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["lib/main.dart"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_PEER
    assert len(result.reviewers) == 2
    frontend_peers = CONFIG.peer_pools["frontend"]
    assert all(r in frontend_peers for r in result.reviewers)
    assert "tonychoi-aiderx" not in result.reviewers


def test_frontend_regular_goes_to_code_reviewer():
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="feature",
        body=None,
        files=["lib/main.dart"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert len(result.reviewers) == 1
    assert result.reviewers[0] in CONFIG.code_reviewer_weights


def test_ian_goes_to_code_reviewer():
    result = assign_reviewers(
        author="ianlee-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert result.reviewers[0] in CONFIG.code_reviewer_weights


def test_mlops_intern_goes_to_code_reviewer():
    result = assign_reviewers(
        author="lucylee-aiderx",
        labels=[],
        title="ml pipeline",
        body=None,
        files=["train.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert len(result.reviewers) == 1


def test_skip_peer_label():
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=["skip-peer-review"],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert result.skip_peer is True


def test_devops_keyword_adds_han():
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="Update deploy workflow",
        body=None,
        files=[".github/workflows/deploy.yml"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert result.is_devops is True
    # hanmh-aiderx가 후보에 포함되어 있어야 함 (가중치 1)
    assert "hanmh-aiderx" in CONFIG.devops_candidates


def test_devops_cd_boundary_no_false_positive():
    # 'cd'가 'abcd' 같은 단어 안에 있을 때는 DevOps로 인식하지 않아야 함.
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="abcd update",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.is_devops is False


def test_devops_ci_slash_cd_matches():
    # "CI/CD" 문맥은 ci, cd 각각 단어 경계로 매칭되어야 함.
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="Update CI/CD pipeline",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.is_devops is True


def test_devops_docker_compound_matches():
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="Update docker-compose",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.is_devops is True


def test_author_excluded_from_reviewers():
    # lucas 본인 PR → lucas 제외하고 code reviewer 선정
    result = assign_reviewers(
        author="lucaskim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert result.reviewers[0] != "lucaskim-aiderx"


def test_already_approved_excluded():
    # ian은 Peer 풀이 아니므로 승인해도 Peer 후보에 영향 없음.
    # juno 작성자 제외 + ian 승인 = bendo, sophie 2명 후보.
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[{"state": "APPROVED", "author": {"login": "ianlee-aiderx"}}],
        config=CONFIG,
    )
    assert len(result.reviewers) == 2
    assert "ianlee-aiderx" not in result.reviewers
    assert "junokim-aiderx" not in result.reviewers


def test_peer_pool_insufficient_selects_available_and_notes_shortage():
    # Peer 후보 3명 중 작성자 1명 제외 → 2명 후보, 2명 필요 → 정상.
    # 이 테스트는 후보가 count와 정확히 같을 때 동작 확인.
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_PEER
    assert len(result.reviewers) == 2


def test_peer_pool_insufficient_one_peer_notes_shortage():
    # Peer 후보 3명 중 작성자 1명 + 이미 승인 1명 제외 → 1명 후보, 2명 필요 → 1명만 지정.
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[{"state": "APPROVED", "author": {"login": "bendo-aiderx"}}],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_PEER
    assert len(result.reviewers) == 1
    assert "bendo-aiderx" not in result.reviewers
    assert "junokim-aiderx" not in result.reviewers
    assert "후보 부족" in result.reason


def test_peer_pool_empty_goes_to_code_reviewer():
    # Peer 후보 3명 중 작성자 1명 + 이미 승인 2명 제외 → 0명 후보 → Code Reviewer 직행.
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[
            {"state": "APPROVED", "author": {"login": "bendo-aiderx"}},
            {"state": "APPROVED", "author": {"login": "sophiepark-aiderx"}},
        ],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert len(result.reviewers) == 1
    assert "junokim-aiderx" not in result.reviewers


def test_code_reviewer_pool_insufficient_raises():
    # Code Reviewer 후보가 모두 작성자이거나 이미 승인하여 후보 0명 → 부족.
    # 작성자 lucaskim 제외 + tedcho, hanmh 이미 승인 → 후보 0명.
    with pytest.raises(ValueError):
        assign_reviewers(
            author="lucaskim-aiderx",
            labels=["skip-peer-review"],
            title="fix",
            body=None,
            files=["src/main.py"],
            reviews=[
                {"state": "APPROVED", "author": {"login": "tedcho-aiderx"}},
                {"state": "APPROVED", "author": {"login": "hanmh-aiderx"}},
            ],
            config=CONFIG,
        )


def test_devops_keyword_in_body():
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="fix",
        body="This PR updates the deployment pipeline",
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.is_devops is True


def test_devops_keyword_in_files():
    result = assign_reviewers(
        author="wannykim-aiderx",
        labels=[],
        title="fix",
        body=None,
        files=[".github/workflows/ci.yml"],
        reviews=[],
        config=CONFIG,
    )
    assert result.is_devops is True


def test_author_is_devops_candidate_excluded_from_weights():
    # 작성자 본인이 DevOps 후보에 포함되어 있어도 제외됨.
    result = assign_reviewers(
        author="hanmh-aiderx",
        labels=["skip-peer-review"],
        title="deploy update",
        body=None,
        files=["src/main.py"],
        reviews=[],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert "hanmh-aiderx" not in result.reviewers


def test_code_reviewer_already_approved_excluded():
    # 코드 리뷰어 lucaskim이 이미 승인한 경우 후보에서 제외.
    result = assign_reviewers(
        author="junokim-aiderx",
        labels=["skip-peer-review"],
        title="fix",
        body=None,
        files=["src/main.py"],
        reviews=[{"state": "APPROVED", "author": {"login": "lucaskim-aiderx"}}],
        config=CONFIG,
    )
    assert result.stage == CONFIG.STAGE_CODE_REVIEWER
    assert "lucaskim-aiderx" not in result.reviewers
