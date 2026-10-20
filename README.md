# archive-releases

모듈 배포 전용 **공개** 레포입니다. 소스코드는 없습니다(각 모듈의 private 레포에 있음).
사용자 PC의 모듈이 실행될 때 여기의 `manifests/<모듈>.json` 을 읽어 새 버전을 알려 줍니다.

```
private 모듈 레포 ── push(VERSION 올림) ──▶ GitHub Actions ──▶ 이 레포 Release + manifests/<모듈>.json
                                                                        ▲
사용자 PC에서 모듈 실행 ── 새 버전 있나? ──────────────────────────────┘ (토큰 불필요)
```

## 모듈 목록

공개 채널로 배포하는 모듈 (소스 zip 또는 EXE — 누구나 받을 수 있으므로 내부 정보가 없는 것만):

| 모듈 | 매니페스트 | 형태 |
|---|---|---|
| hrd-suite (올인원 아카이브 인턴 업무 도우미) | `manifests/hrd-suite.json` | EXE (기관 시드 제외) |
| dailynews | `manifests/dailynews.json` | 소스 zip |
| data-validation-tool | `manifests/data-validation-tool.json` | 소스 zip |
| nudge-sheet (학습독려 시트 Apps Script) | `manifests/nudge-sheet.json` | nudge.gs (인턴 명단 제외) |

공개 채널을 쓰지 않는 모듈 (소스에 사내 서버·고객사·후기 데이터가 있음 → `git` 모드: private 레포를 인증된 `git pull` 로 갱신):
graph-rag, kdc-analysis, misc-tools.  `hrd-legacy-tools` 는 보관용이라 업데이트가 없다.

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
2. `python tools/set_release_secret.py` 를 실행하고 토큰을 붙여 넣으면 대상 모듈 레포 4곳에 시크릿으로 한 번에 등록한다
   (먼저 토큰이 archive-releases 에 쓸 수 있는지 검사한다. `pip install pynacl` 필요).

토큰이 없으면 Actions 는 실패하지 않고 "배포를 건너뜁니다" 경고만 남긴다.

## 주의

- 이 레포는 공개라 **누구나 산출물을 받을 수 있다.** 내부 자료(기관 명단·수치, 키, 개인정보)가
  들어간 산출물은 올리지 말 것. hrd-suite 의 CI 빌드는 기관 마스터 시드를 제외한다.

## 새 모듈에 업데이트 기능 붙이기

```
python tools/scaffold.py <폴더> <모듈이름> "<표시이름>" [--mode release|git] [--preserve 사용자가_고치는_파일 ...]
                         [--exclude 공개하면_안_되는_파일 ...] [--deny 공개_산출물에_있으면_안_되는_문자열 ...]
```

`VERSION`, `update.json`, `selfupdate.py`, 워크플로를 심는다. 진입점에서 `selfupdate.notify_cli()`(콘솔) 또는 `selfupdate.notify_gui()`(창)을 부르면
실행할 때 새 버전을 알려 주고, 사용자가 «예»를 눌러야만 설치한다. 배포 직전 `leakcheck.py` 가 산출물에 `--deny` 문자열·토큰·개인키가 있으면 막는다.
