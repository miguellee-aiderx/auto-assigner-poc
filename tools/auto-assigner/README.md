# Auto Assigner

GitHub PR 리뷰어 자동 지정 도구입니다.

`claude` 봇이 PR에 LGTM을 남기면, 작성자 역할에 따라 Peer 리뷰어 또는 Code Reviewer를 자동으로 지정하고, 필요한 경우 Ready for Review로 전환합니다.
인턴 PR은 Peer 승인 완료 후 Code Reviewer를 자동으로 지정하는 staged 모드도 지원합니다.

## 지원 repo

- `aiderx-corp/a2-adm` (PoC 대상)

## 개발 환경

```bash
cd /home/miguel/workspace/auto-assigner
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 테스트

```bash
pytest
ruff check src tests
mypy src
```

## 로컬 dry-run

```bash
DRY_RUN=true \
EVENT_FILE=tests/fixtures/backend_intern_lgtm.json \
python -m auto_assigner
```

주의: `DRY_RUN=true`는 **GitHub 쓰기 작업만 막습니다.**
PR 메타데이터(작성자, 라벨, 변경 파일, 리뷰 상태)를 조회하기 위한
`gh pr view` 읽기 API는 정상 호출됩니다.

## 환경 변수

| 변수 | 설명 | 기본값 |
| --- | --- | --- |
| `DRY_RUN` | GitHub 쓰기 작업만 막고, 읽기/Slack 알림은 정상 동작 | `true` |
| `STAGED_MODE` | `true`면 Peer 승인 후 Code Reviewer 지정 모드 | `false` |
| `EVENT_FILE` | GitHub webhook payload JSON 경로 | - |
| `GITHUB_TOKEN` | GitHub API 토큰. 없으면 `gh` CLI의 기본 인증 사용 | - |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | - |
| `AUTO_ASSIGNER_CONFIG` | 설정 YAML 파일 경로 | `config/config.yaml` |

## 배포 구조

```text
aiderx-corp/auto-assigner/        # 본 엔진 repo
  src/auto_assigner/
  tests/
  pyproject.toml
  README.md
  config/config.yaml              # 예시/기본 설정

aiderx-corp/a2-adm-auto-assigner/ # a2-adm 배포 템플릿 repo (엔진 repo와 분리)
  .github/
    workflows/
      auto-assign-reviewers.yml       # 초기 라우팅 (Claude LGTM)
      auto-assign-code-reviewer.yml   # staged 라우팅 (Peer 승인 → CR)
    auto-assigner-config.yaml       # a2-adm 전용 설정

aiderx-corp/a2-adm/               # 실제 a2-adm repo
  .github/
    workflows/
      auto-assign-reviewers.yml       # 템플릿에서 복사
      auto-assign-code-reviewer.yml   # 템플릿에서 복사
    auto-assigner-config.yaml       # a2-adm 전용 설정 (템플릿에서 복사)
```

`a2-adm`의 workflow는 `aiderx-corp/auto-assigner`를 별도 checkout 받아 실행하고,
`AUTO_ASSIGNER_CONFIG` 환경 변수로 `.github/auto-assigner-config.yaml`을 지정합니다.

`a2-adm-auto-assigner`는 a2-adm용 workflow/config 템플릿을 관리하는 repo입니다.
실제 운영 시에는 이 템플릿을 `aiderx-corp/a2-adm`의 `.github/` 아래로 복사/동기화하여 사용합니다.

## 설정 파일 (`config/config.yaml`)

```yaml
peer_pools:
  backend_intern:
    - junokim-aiderx
    - bendo-aiderx
    - sophiepark-aiderx
  frontend:
    - tonychoi-aiderx
    - zoekim-aiderx
    - wannykim-aiderx

code_reviewers:
  lucaskim-aiderx: 5
  tedcho-aiderx: 4
  hanmh-aiderx: 1

author_roles:
  junokim-aiderx: backend_intern
  ...

labels:
  auto_routed: auto-routed
  skip_peer: skip-peer-review

peer_count: 2
```

## GitHub Actions 설정

`a2-adm` repo에 아래 secret/variable을 추가합니다.

| 이름 | 종류 | 설명 |
| --- | --- | --- |
| `AUTO_ASSIGNER_SLACK_WEBHOOK_URL` | Repository secret | Slack 알림용 incoming webhook URL |
| `AUTO_ASSIGNER_DRY_RUN` | Repository variable | `true`: Slack 출력만, `false`: GitHub 쓰기 실행 |

workflow의 `permissions`에 `pull-requests: write`, `issues: write`가 필요합니다.

## Dry-run → Production 전환

1. **6/17~6/19**: `AUTO_ASSIGNER_DRY_RUN=true`로 Slack 출력만, 오탐 빈도 측정
2. **6/20~6/25**: `AUTO_ASSIGNER_DRY_RUN=false`로 실제 Review Request + Ready for Review 자동화
3. **6/26~6/30**: KPI 측정, 안정화
