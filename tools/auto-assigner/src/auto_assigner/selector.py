"""리뷰어 선정 유틸리티.

Peer 선정은 단순 무작위 셔플로 진행하며,
Code Reviewer 선정은 실측 데이터 기반 가중치를 반영한 weighted random 방식을 사용합니다.
"""

from __future__ import annotations

import random


def select_peers(peer_pool: frozenset[str], exclude: set[str], count: int) -> list[str]:
    """Peer 풀에서 제외 대상을 뺀 뒤 count명을 무작위로 선정한다.

    Args:
        peer_pool: 전체 Peer 후보 집합.
        exclude: 선정에서 제외할 로그인 집합(작성자, 이미 승인자 등).
        count: 선정할 인원 수.

    Raises:
        ValueError: 후보가 count명보다 적을 때 발생.
    """
    candidates = list(peer_pool - exclude)
    if len(candidates) < count:
        raise ValueError(
            f"후보 부족: 필요 {count}명, 가능 {len(candidates)}명 "
            f"(pool={peer_pool}, exclude={exclude})"
        )
    # 복원 추출 없이 한 번에 셔플 후 상위 count명을 반환.
    random.shuffle(candidates)
    return candidates[:count]


def select_code_reviewers(
    weights: dict[str, int], exclude: set[str], count: int
) -> list[str]:
    """가중치 기반으로 Code Reviewer를 선정한다.

    Args:
        weights: {github_login: 가중치} 맵. 가중치가 클수록 선정 확률 높음.
        exclude: 선정에서 제외할 로그인 집합.
        count: 선정할 인원 수.

    Raises:
        ValueError: 후보가 부족하거나 가중치 합이 0 이하일 때 발생.
    """
    # 제외 대상과 가중치 0인 후보는 제거.
    pool = {k: v for k, v in weights.items() if k not in exclude and v > 0}
    if len(pool) < count:
        raise ValueError(
            f"후보 부족: 필요 {count}명, 가능 {len(pool)}명 "
            f"(weights={weights}, exclude={exclude})"
        )

    result: list[str] = []
    remaining = dict(pool)
    for _ in range(count):
        total = sum(remaining.values())
        if total <= 0:
            raise ValueError("가중치 합이 0 이하입니다.")
        # 복원 추출을 방지하기 위해 선정된 후보는 remaining에서 즉시 제거.
        picked = random.choices(
            list(remaining.keys()), weights=list(remaining.values()), k=1
        )[0]
        result.append(picked)
        del remaining[picked]

    return result
