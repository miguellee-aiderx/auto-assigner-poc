"""selector 모듈 테스트."""

from __future__ import annotations

import pytest

from auto_assigner.config import Config
from auto_assigner.selector import select_code_reviewers, select_peers

CONFIG = Config.default()
BACKEND_PEERS = CONFIG.peer_pools["backend_intern"]
CR_WEIGHTS = CONFIG.code_reviewer_weights


def test_select_peers_count():
    peers = select_peers(BACKEND_PEERS, exclude=set(), count=2)
    assert len(peers) == 2
    assert set(peers) <= BACKEND_PEERS


def test_select_peers_exclude_author():
    peers = select_peers(BACKEND_PEERS, exclude={"junokim-aiderx"}, count=2)
    assert "junokim-aiderx" not in peers
    assert len(peers) == 2


def test_select_peers_insufficient_candidates():
    # 후보가 count보다 적으면 가능한 만큼만 선정한다.
    peers = select_peers(BACKEND_PEERS, exclude={"junokim-aiderx"}, count=3)
    assert len(peers) == 2
    assert set(peers) <= BACKEND_PEERS
    assert "junokim-aiderx" not in peers


def test_select_peers_empty_pool_returns_empty():
    peers = select_peers(frozenset(), exclude=set(), count=2)
    assert peers == []


def test_select_code_reviewers_count():
    reviewers = select_code_reviewers(CR_WEIGHTS, exclude=set(), count=1)
    assert len(reviewers) == 1
    assert reviewers[0] in CR_WEIGHTS


def test_select_code_reviewers_exclude_author():
    reviewers = select_code_reviewers(
        CR_WEIGHTS, exclude={"lucaskim-aiderx", "tedcho-aiderx"}, count=1
    )
    assert reviewers == ["hanmh-aiderx"]


def test_select_code_reviewers_insufficient_candidates():
    with pytest.raises(ValueError):
        select_code_reviewers(CR_WEIGHTS, exclude=set(CR_WEIGHTS), count=1)
