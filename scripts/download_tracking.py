"""Fetch LFS objects into the ignored cache, verifying the repository's SHA256."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def download(pointer):
    target = ROOT / ".cache" / "tracking" / pointer.name
    target.parent.mkdir(parents=True, exist_ok=True)
    spec = pointer.read_text().splitlines()
    digest = next(s.split("sha256:")[1] for s in spec if s.startswith("oid "))
    size = int(next(s.split()[1] for s in spec if s.startswith("size ")))
    if target.exists() and target.stat().st_size == size:
        if hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            return f"{pointer.parent.name}: verified cache"
    url = (
        "https://media.githubusercontent.com/media/SkillCorner/opendata-basketball/main/"
        + pointer.relative_to(ROOT).as_posix()
    )
    temporary = target.with_suffix(".part")
    try:
        with (
            urllib.request.urlopen(url, timeout=120) as response,
            temporary.open("wb") as out,
        ):
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        if (
            temporary.stat().st_size != size
            or hashlib.sha256(temporary.read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"Integrity check failed: {pointer.name}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return f"{pointer.parent.name}: downloaded and SHA256 verified"


if __name__ == "__main__":
    pointers = sorted((ROOT / "data/matches").glob("*/*_tracking_data.jsonl.gz"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(download, pointers):
            print(result, flush=True)
