# archive-releases

모듈 배포 전용 **공개** 레포입니다. 소스코드는 없습니다(각 모듈의 private 레포에 있음).
사용자 PC의 모듈이 실행될 때 여기의 `manifests/<모듈>.json` 을 읽어 새 버전을 알려 줍니다.

```
private 모듈 레포 ── push(VERSION 올림) ──▶ GitHub Actions ──▶ 이 레포 Release + manifests/<모듈>.json
                                                                        ▲
사용자 PC에서 모듈 실행 ── 새 버전 있나? ──────────────────────────────┘ (토큰 불필요)
```

## 모듈 목록

| 모듈 | 매니페스트 | 형태 |
|---|---|---|
| hrd-suite (올인원 아카이브 인턴 업무 도우미) | `manifests/hrd-suite.json` | EXE |
| graph-rag (공유폴더 지식그래프·RAG) | `manifests/graph-rag.json` | 소스 zip |
| kdc-analysis | `manifests/kdc-analysis.json` | 소스 zip |
| dailynews | `manifests/dailynews.json` | 소스 zip |
| data-validation-tool | `manifests/data-validation-tool.json` | 소스 zip |
| misc-tools | `manifests/misc-tools.json` | 소스 zip |
| nudge-sheet (학습독려 시트 Apps Script) | `manifests/nudge-sheet.json` | nudge.gs |

## 배포하는 법 (개발자)

1. 모듈의 `VERSION` 파일(hrd-suite는 `src/hrdsuite/__init__.py`의 `__version__`)을 올린다.
2. `main` 에 push 한다.
3. 모듈 레포의 Actions 가 빌드해서 이 레포에 Release 를 올리고 매니페스트를 갱신한다.
   같은 버전을 다시 push 해도 중복 배포되지 않는다. **버전을 올리지 않으면 배포되지 않는다.**

## 최초 1회 설정

모듈 레포의 Actions 가 이 레포에 쓰려면 토큰이 필요하다(`RELEASES_TOKEN` 시크릿).

1. GitHub → Settings → Developer settings → Fine-grained tokens → 새 토큰
   - Repository access: **Only select repositories → archive-releases**
   - Permissions: **Contents: Read and write**
2. 모듈 레포마다 `RELEASES_TOKEN` 시크릿으로 등록(자동화 스크립트: 작업 폴더의 `tools/set_release_secret.py`).

토큰이 없으면 Actions 는 실패하지 않고 "배포를 건너뜁니다" 경고만 남긴다.

## 주의

- 이 레포는 공개라 **누구나 산출물을 받을 수 있다.** 내부 자료(기관 명단·수치, 키, 개인정보)가
  들어간 산출물은 올리지 말 것. hrd-suite 의 CI 빌드는 기관 마스터 시드를 제외한다.
