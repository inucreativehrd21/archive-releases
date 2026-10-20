# -*- coding: utf-8 -*-
"""공개 배포 직전 유출 점검.

  python leakcheck.py <산출물.zip>

공개 배포 레포(archive-releases)는 누구나 읽을 수 있다. 이 zip 에 내부 정보가 섞여 나가지 않게 막는다.
  · 모듈 루트의 `.release-denylist` 에 적힌 문자열(한 줄에 하나, # 주석)이 하나라도 들어 있으면 실패
  · 기본 규칙: GitHub/Anthropic 토큰, 개인키 블록
걸리면 어느 파일에서 걸렸는지만 출력한다(문자열 자체는 로그에 남기지 않는다).
"""
import re
import sys
import zipfile
from pathlib import Path

BUILTIN = [
    ("GitHub 토큰", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{30,}")),
    ("개인키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def main(zip_path: str) -> int:
    deny = []
    f = Path(".release-denylist")
    if f.exists():
        deny = [l.strip() for l in f.read_text("utf-8-sig").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    bad = []
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            if m.is_dir() or m.file_size > 20_000_000:
                continue
            text = z.read(m).decode("utf-8", "ignore")
            low = text.lower()
            for i, d in enumerate(deny, 1):
                if d.lower() in low:
                    bad.append((m.filename, f"denylist #{i}"))
            for name, rx in BUILTIN:
                if rx.search(text):
                    bad.append((m.filename, name))
    if bad:
        for fn, why in bad:
            print(f"::error file={fn}::공개 배포 산출물에 내부 정보가 있습니다 ({why})")
        print(f"유출 점검 실패 — {len(bad)}건. 해당 파일을 제외 목록(--exclude)에 넣거나 내용을 고치세요.")
        return 1
    print(f"유출 점검 통과 (denylist {len(deny)}개 + 기본 규칙)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
