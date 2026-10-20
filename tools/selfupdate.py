# -*- coding: utf-8 -*-
"""selfupdate.py — 모듈 자체 업데이트 (표준 라이브러리만 사용).

흐름:  모듈 실행 → 공개 배포 레포의 manifests/<모듈>.json 조회 → 새 버전이면 알림
       → 사용자가 «예» → 소스 zip 내려받기 → sha256 대조 → 덮어쓰기 → 재시작

두 가지 방식이 있다 (update.json 의 "mode").
  release(기본)  공개 배포 레포의 소스 zip 을 받는다. 토큰 불필요 → 다른 PC 의 사용자용.
  git           private 레포를 인증된 git 으로 갱신한다(fetch → pull --ff-only).
                소스에 내부 정보가 많아 공개할 수 없는 모듈용. 이 PC 에 레포 접근 권한(GCM 로그인)이 있어야 한다.

같은 폴더에 두 파일이 있어야 한다.
    VERSION       현재 버전 한 줄 (예: 1.0.0)   ← 이 값을 올리고 push 하면 배포된다
    update.json   {"module": "...", "manifest_url": "https://raw.githubusercontent.com/...",
                   "preserve": ["keywords.txt", ...]}

설계 메모
  · zip 에는 git 에 추적되는 파일만 들어 있다(git archive). 그래서 data/, output/, .venv/, .env 같은
    사용자 데이터는 애초에 zip 에 없어 덮어써질 수 없다.
  · 사용자가 직접 고쳐 쓰는 추적 파일(키워드 목록 등)은 update.json 의 preserve 에 적는다.
    이미 존재하면 건드리지 않는다.
  · 덮어쓰기 전에 원본을 .update_backup/<버전>/ 에 복사해 둔다.
  · 오프라인·차단 등 어떤 실패도 모듈 실행을 막지 않는다 (자동 확인은 조용히 실패한다).
  · 자동으로 갈아치우지 않는다. 항상 사용자가 «예»를 눌러야 설치한다.
  · 삭제된 파일은 지우지 않는다(남아 있어도 무해하고, 잘못 지우는 사고를 피한다).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE_FILE = ".update_state.json"
BACKUP_DIR = ".update_backup"
TIMEOUT = 5          # 초. 자동 확인이 모듈 실행을 붙잡지 않게 짧게.


# ── 출력 ───────────────────────────────────────────────────────────
def _say(text: str, stream=None) -> None:
    """콘솔 인코딩(cp949 등)이 못 쓰는 글자가 있어도 죽지 않는다.
    업데이트 알림 때문에 본 모듈이 죽는 일은 있어서는 안 된다."""
    stream = stream or sys.stdout
    line = text + "\n"
    try:
        stream.write(line)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        try:
            stream.write(line.encode(enc, "replace").decode(enc, "replace"))
        except Exception:
            pass
    except Exception:
        pass


# ── 설정·버전 ───────────────────────────────────────────────────────
def _config(base: Path) -> dict:
    try:
        return json.loads((base / "update.json").read_text("utf-8-sig"))
    except Exception:
        return {}


def current_version(base: Path = BASE) -> str:
    try:
        return (base / "VERSION").read_text("utf-8-sig").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _key(v: str) -> list[int]:
    return [int(x) if x.isdigit() else 0 for x in str(v).strip().lstrip("vV").split(".")]


def is_newer(latest: str, current: str) -> bool:
    a, b = _key(latest), _key(current)
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


# ── 네트워크 ────────────────────────────────────────────────────────
def _ssl_context() -> ssl.SSLContext:
    # 사내망이 TLS 를 재서명한다. truststore 가 있으면 Windows 인증서 저장소를 신뢰한다.
    try:
        import truststore                                  # type: ignore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def _get(url: str, timeout: float = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "archive-selfupdate"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read()


# ── 상태(알림 빈도 제한) ─────────────────────────────────────────────
def _load_state(base: Path) -> dict:
    try:
        return json.loads((base / STATE_FILE).read_text("utf-8"))
    except Exception:
        return {}


def _save_state(base: Path, **kw) -> None:
    try:
        st = _load_state(base)
        st.update(kw)
        (base / STATE_FILE).write_text(json.dumps(st), "utf-8")
    except Exception:
        pass



# ── git 모드 ────────────────────────────────────────────────────────
def _git(base: Path, *args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")   # 자동 확인이 로그인 창을 띄우지 않게
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["git", "-C", str(base), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env, creationflags=flags)


def _check_git(base: Path) -> dict | None:
    if not (base / ".git").exists():
        raise RuntimeError("git 모드인데 이 폴더가 git 저장소가 아닙니다.")
    r = _git(base, "fetch", "--quiet", "origin", "main")
    if r.returncode:
        raise RuntimeError("원격을 읽지 못했습니다: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    remote = _git(base, "show", "origin/main:VERSION")
    latest = remote.stdout.strip() if remote.returncode == 0 else ""
    if not latest or not is_newer(latest, current_version(base)):
        return None
    msg = _git(base, "log", "-1", "--format=%s", "origin/main").stdout.strip()
    return {"version": latest, "notice": msg, "mode": "git"}


def _apply_git(info: dict, base: Path, log) -> list[str]:
    dirty = _git(base, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    r = _git(base, "pull", "--ff-only", "origin", "main", timeout=120)
    if r.returncode:
        hint = "수정 중인 파일이 있어 합칠 수 없습니다. 커밋하거나 되돌린 뒤 다시 시도하세요." if dirty else ""
        msg = (r.stderr.strip() or r.stdout.strip())[-400:]
        raise RuntimeError(msg + ("\n" + hint if hint else ""))
    changed = [l for l in _git(base, "diff", "--name-only", "HEAD@{1}", "HEAD").stdout.splitlines() if l]
    log(f"업데이트 완료: v{info['version']} ({len(changed)}개 파일 변경)")
    return changed


# ── 확인 ───────────────────────────────────────────────────────────
def check(base: Path = BASE, *, min_interval_hours: float = 0, quiet: bool = True) -> dict | None:
    """새 버전이 있으면 {version, notice, url, sha256, min_size}, 없으면 None.

    min_interval_hours > 0 이면 마지막 확인 후 그 시간 안에는 네트워크를 타지 않는다.
    quiet=False 이면 실패를 예외로 올린다(사용자가 «업데이트 확인»을 누른 경우).
    """
    cfg = _config(base)
    git_mode = cfg.get("mode") == "git"
    url = cfg.get("manifest_url", "")
    if not url and not git_mode:
        if quiet:
            return None
        raise RuntimeError("update.json 에 manifest_url 이 없습니다.")
    if min_interval_hours:
        last = _load_state(base).get("last_check", 0)
        if time.time() - float(last or 0) < min_interval_hours * 3600:
            return None
    try:
        if git_mode:
            info = _check_git(base)
            _save_state(base, last_check=time.time())
            return info
        man = json.loads(_get(url).decode("utf-8-sig"))
        _save_state(base, last_check=time.time())
    except Exception:
        if quiet:
            return None
        raise
    latest = str(man.get("latestVersion", "")).strip()
    if not latest or not is_newer(latest, current_version(base)):
        return None
    return {"version": latest, "notice": str(man.get("notice", "")).strip(),
            "url": str(man.get("downloadUrl", "")).strip(),
            "sha256": str(man.get("sha256", "")).strip().lower(),
            "min_size": int(man.get("minSize") or 0)}


# ── 설치 ───────────────────────────────────────────────────────────
def _safe_target(base: Path, name: str) -> Path | None:
    p = (base / name).resolve()
    try:
        p.relative_to(base.resolve())
    except ValueError:
        return None                      # zip 경로 탈출(..) 방어
    return p


def apply(info: dict, base: Path = BASE, log=_say) -> list[str]:
    """info 의 zip 을 받아 base 에 덮어쓴다. 바뀐 파일 이름 목록을 돌려준다."""
    if info.get("mode") == "git":
        return _apply_git(info, base, log)
    if not info.get("url"):
        raise ValueError("배포 주소(downloadUrl)가 비어 있습니다.")
    data = _get(info["url"], timeout=60)
    if len(data) < max(info.get("min_size") or 0, 1):
        raise ValueError(f"받은 파일이 너무 작습니다({len(data):,}바이트).")
    if info.get("sha256"):
        got = hashlib.sha256(data).hexdigest()
        if got != info["sha256"]:
            raise ValueError(f"체크섬이 다릅니다. 설치하지 않았습니다.\n"
                             f"  기대 {info['sha256'][:16]}…\n  실제 {got[:16]}…")
    else:
        log("경고: 배포 정보에 sha256 이 없어 체크섬을 대조하지 못했습니다.")

    preserve = {str(x).replace("\\", "/") for x in _config(base).get("preserve", [])}
    backup = base / BACKUP_DIR / current_version(base)
    req_before = _hash(base / "requirements.txt")
    changed: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        zp = Path(td) / "update.zip"
        zp.write_bytes(data)
        with zipfile.ZipFile(zp) as z:
            # 전부 검증한 뒤에 쓴다 — 중간에 깨진 zip 이 일부만 덮어쓰는 사고를 막는다.
            bad = z.testzip()
            if bad:
                raise ValueError(f"zip 이 손상되었습니다: {bad}")
            for m in z.infolist():
                if m.is_dir():
                    continue
                name = m.filename.replace("\\", "/")
                dst = _safe_target(base, name)
                if dst is None:
                    raise ValueError(f"허용되지 않는 경로: {name}")
                if name in preserve and dst.exists():
                    continue
                if dst.exists():
                    if dst.read_bytes() == z.read(m):
                        continue                         # 내용이 같으면 건드리지 않는다
                    b = backup / name
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, b)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(m))
                changed.append(name)

    (base / "VERSION").write_text(info["version"] + "\n", "utf-8")
    log(f"업데이트 완료: v{info['version']} ({len(changed)}개 파일 변경)")
    if _hash(base / "requirements.txt") != req_before:
        log("requirements.txt 가 바뀌었습니다 — 다음을 실행하세요:\n"
            f"  \"{sys.executable}\" -m pip install -r requirements.txt")
    return changed


def _hash(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return ""


# ── 진입점별 알림 ───────────────────────────────────────────────────
def _title(base: Path) -> str:
    return _config(base).get("title") or _config(base).get("module") or "모듈"


def notify_cli(base: Path = BASE, *, min_interval_hours: float = 24, stream=None) -> dict | None:
    """콘솔 도구용: 새 버전이 있으면 한 줄 안내만 찍는다. 설치는 `update` 명령으로.
    어떤 오류도 호출한 도구로 번지지 않는다."""
    try:
        info = check(base, min_interval_hours=min_interval_hours)
        if info:
            _say(f"[업데이트] {_title(base)} 새 버전 v{info['version']} (현재 v{current_version(base)})"
                 + (f" - {info['notice']}" if info["notice"] else "")
                 + "  -> `update` 명령으로 설치", stream or sys.stderr)
        return info
    except Exception:
        return None


def notify_gui(base: Path = BASE, *, min_interval_hours: float = 12, relaunch: bool = True) -> bool:
    """GUI 도구용: 시작 시 한 번 묻는다. 설치했으면 True(재시작 후 종료됨)."""
    info = check(base, min_interval_hours=min_interval_hours)
    if not info:
        return False
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        msg = (f"{_title(base)} 새 버전 v{info['version']}이 나왔습니다 (현재 v{current_version(base)}).\n"
               + (f"\n{info['notice']}\n" if info["notice"] else "")
               + "\n지금 업데이트할까요?")
        yes = messagebox.askyesno("업데이트", msg, parent=root)
        if not yes:
            root.destroy()
            return False
        try:
            apply(info, base, log=lambda *_: None)
        except Exception as e:                                # noqa: BLE001
            messagebox.showerror("업데이트 실패", f"업데이트하지 못했습니다. 기존 버전으로 계속합니다.\n\n{e}", parent=root)
            root.destroy()
            return False
        root.destroy()
        if relaunch:
            subprocess.Popen([sys.executable, *sys.argv], cwd=str(base))
            os._exit(0)
        return True
    except Exception:
        return False


# ── CLI ────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    base = BASE
    _say(f"{_title(base)} 현재 v{current_version(base)}")
    try:
        info = check(base, quiet=False)
    except Exception as e:                                    # noqa: BLE001
        _say(f"확인하지 못했습니다: {e}")
        return 2
    if not info:
        _say("최신 버전입니다.")
        return 0
    _say(f"새 버전 v{info['version']}" + (f" — {info['notice']}" if info["notice"] else ""))
    if "--check" in argv:
        return 0
    if "--yes" not in argv and input("설치할까요? [y/N] ").strip().lower() not in ("y", "yes"):
        return 0
    try:
        apply(info, base)
    except Exception as e:                                    # noqa: BLE001
        _say(f"실패: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
