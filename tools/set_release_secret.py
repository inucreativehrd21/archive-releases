# -*- coding: utf-8 -*-
"""모듈 레포들에 RELEASES_TOKEN 시크릿을 한 번에 등록한다.

  python set_release_secret.py

1) GitHub 에서 fine-grained 토큰을 만든다 (https://github.com/settings/personal-access-tokens/new)
     Repository access : Only select repositories → archive-releases
     Permissions       : Contents → Read and write
2) 이 스크립트를 실행하고, 물어보면 토큰을 붙여 넣는다 (화면에 표시되지 않고 어디에도 저장되지 않는다).

토큰이 archive-releases 에 실제로 쓸 수 있는지 먼저 확인한 뒤, 아래 레포의 Actions 시크릿으로 암호화해 올린다.
git 모드 모듈(graph-rag, kdc-analysis, misc-tools)은 공개 배포를 하지 않으므로 대상이 아니다.
"""
import base64
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.request

OWNER = "inucreativehrd21"
RELEASES = "archive-releases"
TARGETS = ["2026HRDArchive_INTERN_HELPER", "dailynews", "data-validation-tool", "nudge-sheet"]
SECRET = "RELEASES_TOKEN"


def gcm_token() -> str:
    out = subprocess.run(["git", "credential-manager", "get"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)["password"]


def call(token, method, path, body=None):
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "set-release-secret"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def main(argv):
    try:
        from nacl import encoding, public
    except ImportError:
        print("PyNaCl 이 필요합니다:  python -m pip install pynacl")
        return 2

    value = argv[0] if argv else getpass.getpass("RELEASES_TOKEN (fine-grained PAT) 붙여 넣기: ").strip()
    if not value:
        print("비어 있습니다.")
        return 2

    # 이 토큰이 정말 archive-releases 에 쓸 수 있는가 — 권한이 모자라면 배포가 조용히 실패한다.
    st, repo = call(value, "GET", f"/repos/{OWNER}/{RELEASES}")
    if st != 200:
        print(f"토큰으로 {RELEASES} 를 읽지 못했습니다 (HTTP {st}). Repository access 에 {RELEASES} 가 포함됐는지 확인하세요.")
        return 1
    if not (repo.get("permissions") or {}).get("push"):
        print(f"토큰에 {RELEASES} 쓰기 권한이 없습니다. Permissions → Contents → Read and write 로 다시 만드세요.")
        return 1
    print(f"토큰 확인: {RELEASES} 쓰기 가능")

    admin = gcm_token()
    failed = 0
    for name in TARGETS:
        st, key = call(admin, "GET", f"/repos/{OWNER}/{name}/actions/secrets/public-key")
        if st != 200:
            print(f"  {name}: 공개키 조회 실패 (HTTP {st})")
            failed += 1
            continue
        box = public.SealedBox(public.PublicKey(key["key"], encoding.Base64Encoder))
        enc = base64.b64encode(box.encrypt(value.encode())).decode()
        st, _ = call(admin, "PUT", f"/repos/{OWNER}/{name}/actions/secrets/{SECRET}",
                     {"encrypted_value": enc, "key_id": key["key_id"]})
        ok = st in (201, 204)
        failed += 0 if ok else 1
        print(f"  {name}: {'등록됨' if ok else f'실패 (HTTP {st})'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
