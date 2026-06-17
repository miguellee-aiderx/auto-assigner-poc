"""a2-adm 리뷰어 자동 지정 설정 로더.

실제 설정값은 프로젝트 루트의 config/config.yaml에 있습니다.
이 모듈은 YAML을 읽어 런타임에서 사용할 수 있는 형태로 변환합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# 라우팅 단계 상수
STAGE_PEER = "peer"
STAGE_CODE_REVIEWER = "code_reviewer"


@dataclass(frozen=True)
class TeamConfig:
    """역할별 라우팅에 필요한 팀 정보.

    Attributes:
        peer_pool: Peer 리뷰어 후보 집합. 비어 있으면 Peer 단계를 생략.
        code_reviewer_weights: Code Reviewer 가중치 맵. 값이 클수록 선정 확률 높음.
        devops_candidates: DevOps 키워드 매칭 시 추가할 후보 집합.
    """

    peer_pool: frozenset[str]
    code_reviewer_weights: dict[str, int]
    devops_candidates: frozenset[str]


class Config:
    """YAML 설정을 메모리에 로드하고 접근 메서드를 제공한다."""

    # 클래스 상수 형태로 외부에서 쉽게 참조.
    STAGE_PEER = STAGE_PEER
    STAGE_CODE_REVIEWER = STAGE_CODE_REVIEWER

    def __init__(self, data: dict[str, Any]):
        self._data = data

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """YAML 파일에서 설정을 로드한다."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data)

    @classmethod
    def default(cls) -> Config:
        """기본 설정 파일(config/config.yaml)을 로드한다.

        환경 변수 AUTO_ASSIGNER_CONFIG로 경로를 지정할 수 있다.
        """
        # src/auto_assigner/config.py -> project root는 2단계 위.
        default_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
        path = os.environ.get("AUTO_ASSIGNER_CONFIG", str(default_path))
        return cls.from_yaml(path)

    @property
    def peer_pools(self) -> dict[str, frozenset[str]]:
        """peer_pool 이름 -> 후보 집합 맵."""
        return {
            name: frozenset(members)
            for name, members in self._data.get("peer_pools", {}).items()
        }

    @property
    def code_reviewer_weights(self) -> dict[str, int]:
        """Code Reviewer 가중치 맵."""
        return dict(self._data.get("code_reviewers", {}))

    @property
    def author_roles(self) -> dict[str, str]:
        """작성자 login -> 역할 이름 맵."""
        return dict(self._data.get("author_roles", {}))

    @property
    def special_roles(self) -> frozenset[str]:
        """Peer 단계를 생략하고 Code Reviewer로 직행하는 역할 집합."""
        return frozenset(self._data.get("special_roles", []))

    @property
    def devops_keywords(self) -> frozenset[str]:
        """DevOps 키워드 집합."""
        return frozenset(self._data.get("devops_keywords", []))

    @property
    def devops_candidates(self) -> frozenset[str]:
        """DevOps 키워드 매칭 시 추가할 후보 집합."""
        return frozenset(self._data.get("devops_candidates", []))

    @property
    def auto_routed_label(self) -> str:
        """멱등 가드용 라벨 이름."""
        value = self._data.get("labels", {}).get("auto_routed", "auto-routed")
        return str(value)

    @property
    def skip_peer_label(self) -> str:
        """Peer 생략 라벨 이름."""
        value = self._data.get("labels", {}).get("skip_peer", "skip-peer-review")
        return str(value)

    @property
    def peer_count(self) -> int:
        """Peer 리뷰어 지정 인원."""
        return int(self._data.get("peer_count", 2))

    def get_team_config(self, role: str) -> TeamConfig:
        """역할 이름에 해당하는 TeamConfig를 반환한다.

        peer_pool에 해당하는 역할이면 해당 풀을 사용하고,
        special_role이거나 미식별 역할이면 Peer 풀을 비운다.
        """
        peer_pool = self.peer_pools.get(role, frozenset())

        return TeamConfig(
            peer_pool=peer_pool,
            code_reviewer_weights=self.code_reviewer_weights,
            devops_candidates=self.devops_candidates,
        )

    def get_role(self, author: str) -> str:
        """작성자 login에 해당하는 역할을 반환한다."""
        return self.author_roles.get(author, "unknown")


# 기존 상수 인터페이스를 유지하기 위한 alias.
# 모듈 import 시점에는 파일 I/O를 하지 않고, 최초 접근 시 lazy loading.
AUTO_ROUTED_LABEL: str = "auto-routed"
SKIP_PEER_LABEL: str = "skip-peer-review"
PEER_COUNT: int = 2


@lru_cache(maxsize=1)
def _default_config() -> Config:
    """기본 설정을 lazy loading으로 반환한다."""
    return Config.default()


# 하위 호환: 직접 DEFAULT_CONFIG에 접근하는 경우를 위해 property 형태 제공.
class _DefaultConfigProxy:
    """DEFAULT_CONFIG 상수 대체용 프록시."""

    def __getattr__(self, name: str) -> Any:
        config = _default_config()
        return getattr(config, name)


DEFAULT_CONFIG = _DefaultConfigProxy()
