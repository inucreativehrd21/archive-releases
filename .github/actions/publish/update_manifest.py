"""manifests/<module>.json 갱신. 이미 같거나 더 새 버전이 적혀 있으면 건드리지 않는다."""
import datetime
import json
import pathlib
import sys

module, version, notice, url, sha, size = sys.argv[1:7]
p = pathlib.Path("manifests") / f"{module}.json"
p.parent.mkdir(exist_ok=True)


def key(v):
    return [int(x) if x.isdigit() else 0 for x in v.split(".")]


old = json.loads(p.read_text("utf-8")) if p.exists() else {}
if old.get("latestVersion") and key(old["latestVersion"]) >= key(version):
    print("manifest 가 더 최신이라 갱신하지 않음")
    sys.exit(0)

p.write_text(json.dumps({
    "module": module,
    "latestVersion": version,
    "notice": notice,
    "downloadUrl": url,
    "sha256": sha,
    "minSize": int(size) // 2,
    "publishedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}, ensure_ascii=False, indent=2) + "\n", "utf-8")
