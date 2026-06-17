# auto-assigner-poc

개인 repo에서 `aiderx-corp/a2-adm`용 Auto Assigner workflow와 엔진을 dry-run 검증하기 위한 POC 저장소입니다.

## 목적

- GitHub Actions workflow 실제 동작 검증
- Claude 봇 리뷰 코멘트(Critical Issues) 해결
- dry-run 모드로 운영 시뮬레이션

## 구성

- `.github/workflows/auto-assign-reviewers.yml` — Claude LGTM 시 Peer 리뷰어 자동 지정
- `.github/workflows/auto-assign-code-reviewer.yml` — Peer 승인 시 Code Reviewer 자동 지정
- `.github/auto-assigner-config.yaml` — a2-adm용 리뷰어 설정
- `tools/auto-assigner/` — Python 기반 Auto Assigner 엔진

## 검증

```bash
cd tools/auto-assigner
python3 -m pytest tests/
```

## 주의

- 본 repo는 POC용입니다. 실제 운영은 `aiderx-corp/a2-adm`에서 진행됩니다.
- workflow는 GitHub-hosted runner(`ubuntu-latest`)를 사용합니다.
