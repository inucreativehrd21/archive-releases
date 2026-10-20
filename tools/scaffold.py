# -*- coding: utf-8 -*-
"""모듈 폴더에 업데이트 기능 공통 파일을 심는다.

  python scaffold.py <폴더> <모듈이름> "<표시이름>" [--mode release|git] [--preserve a.txt ...]
                     [--exclude 경로 ...] [--deny 문자열 ...] [--version 1.0.0]

mode
  release(기본)  push → Actions 가 소스 zip 을 공개 배포 레포(archive-releases)에 발행 → 사용자 PC 가 토큰 없이 확인·설치
  git           소스를 공개할 수 없는 모듈. Actions 는 구문 검사만, 사용자 PC 는 private 레포를 git pull 로 갱신

만드는 것: VERSION, update.json, selfupdate.py, .gitattributes, .github/workflows/(release|ci).yml
이미 있는 VERSION 은 건드리지 않는다. 나머지는 항상 최신 템플릿으로 덮어쓴다.
"""
import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWNER = "inucreativehrd21"
MANIFEST = f"https://raw.githubusercontent.com/{OWNER}/archive-releases/main/manifests/{{module}}.json"

WORKFLOW = """\
name: release

# main 에 push 될 때, VERSION 파일의 버전이 아직 배포되지 않았으면 배포한다.
# 같은 버전은 두 번 배포되지 않는다. 배포하려면 VERSION 을 올리고 push 한다.
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 버전 읽기
        id: v
        run: echo "version=$(tr -d '[:space:]' < VERSION)" >> "$GITHUB_OUTPUT"

      - name: 소스 zip 만들기 (git 추적 파일만, 공개 제외 목록 적용)
        run: git archive --format=zip -o "${{{{ runner.temp }}}}/{module}-${{{{ steps.v.outputs.version }}}}.zip" HEAD -- . ':(exclude).release-denylist'{excludes}

      - name: 공개 유출 점검
        run: python .github/scripts/leakcheck.py "${{{{ runner.temp }}}}/{module}-${{{{ steps.v.outputs.version }}}}.zip"

      - name: 공개 배포 레포로 발행
        uses: {owner}/archive-releases/.github/actions/publish@main
        with:
          module: {module}
          version: ${{{{ steps.v.outputs.version }}}}
          file: ${{{{ runner.temp }}}}/{module}-${{{{ steps.v.outputs.version }}}}.zip
          notice: ${{{{ github.event.head_commit.message }}}}
          token: ${{{{ secrets.RELEASES_TOKEN }}}}
"""

CI_WORKFLOW = """\
name: ci

# 소스를 공개하지 않는 모듈: 배포(release)는 없다. push 마다 구문 검사만 한다.
# 사용자 PC 의 {module} 은 `update` 로 이 private 레포를 git pull 하고, 실행할 때 새 버전(VERSION)을 알려 준다.
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: VERSION 형식
        run: |
          python - <<'PY'
          v = open('VERSION').read().strip()
          assert all(p.isdigit() for p in v.split('.')), 'VERSION format error: ' + v
          PY
      - name: 구문 검사
        run: python -m compileall -q .
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("module")
    ap.add_argument("title")
    ap.add_argument("--preserve", nargs="*", default=[])
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--no-workflow", action="store_true")
    ap.add_argument("--mode", choices=["release", "git"], default="release")
    ap.add_argument("--exclude", nargs="*", default=[], help="공개 배포 zip 에서 뺄 경로(사이트 고유 설정 등)")
    ap.add_argument("--deny", nargs="*", default=[], help="공개 산출물에 들어가면 안 되는 문자열")
    a = ap.parse_args()
    d = Path(a.folder)
    d.mkdir(parents=True, exist_ok=True)

    v = d / "VERSION"
    if not v.exists():
        v.write_text(a.version + "\n", "utf-8")
    cfg = {"module": a.module, "title": a.title, "mode": a.mode}
    if a.mode == "release":
        cfg["manifest_url"] = MANIFEST.format(module=a.module)
        cfg["preserve"] = a.preserve
    (d / "update.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", "utf-8")
    shutil.copy(HERE / "selfupdate.py", d / "selfupdate.py")
    (d / ".gitattributes").write_text(
        "# 배포 zip(git archive)에서 제외\n.github export-ignore\n.gitattributes export-ignore\n"
        "* text=auto\n*.bat text eol=crlf\n*.cmd text eol=crlf\n*.ps1 text eol=crlf\n", "utf-8")

    if not a.no_workflow:
        w = d / ".github" / "workflows"
        w.mkdir(parents=True, exist_ok=True)
        if a.mode == "git":
            (w / "ci.yml").write_text(CI_WORKFLOW.format(module=a.module), "utf-8")
            (w / "release.yml").unlink(missing_ok=True)
        else:
            ex = "".join(f" ':(exclude){e}'" for e in a.exclude)
            (w / "release.yml").write_text(WORKFLOW.format(module=a.module, owner=OWNER, excludes=ex), "utf-8")
            s = d / ".github" / "scripts"
            s.mkdir(parents=True, exist_ok=True)
            shutil.copy(HERE / "leakcheck.py", s / "leakcheck.py")
            if a.deny:
                head = "# 공개 배포 산출물에 들어가면 안 되는 문자열 (한 줄에 하나). 이 파일 자체는 배포에서 제외된다."
                (d / ".release-denylist").write_text("\n".join([head, *a.deny]) + "\n", "utf-8")
    print(f"scaffolded {d} ({a.module}, {a.mode})")


if __name__ == "__main__":
    main()
