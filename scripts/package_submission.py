"""Build and verify the clean SIGNAL submission archive."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "signal-submission-final.zip"
BANNED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".vite", "dist", "build", "coverage",
    "htmlcov", "downloads", "tmp",
}
BANNED_NAMES = {".env", ".DS_Store", ".lock"}
BANNED_SUFFIXES = {".pyc", ".pyo", ".log", ".pid", ".tsbuildinfo", ".pem", ".key", ".zip"}
REQUIRED = {
    "signal/README.md", "signal/ARCHITECTURE.md", "signal/BENCHMARKS.md",
    "signal/EVALUATION.md", "signal/SECURITY.md", "signal/JUDGE_GUIDE.md",
    "signal/ENVIRONMENT.md", "signal/DEPENDENCIES.md", "signal/DEPLOYMENT.md",
    "signal/REQUIREMENTS_TRACEABILITY.md", "signal/JUDGE_ATTACK_REPORT.md",
    "signal/DEMO_SCRIPT.md", "signal/PROCESS_VIDEO_PLAN.md", "signal/SUBMISSION_CHECKLIST.md",
    "signal/data/index/manifest.json",
    "signal/reports/evaluation.json", "signal/reports/evaluations/index.json",
    "signal/reports/chunking_comparison.json", "signal/scripts/benchmark_voice.py",
    "signal/reports/verification.json", "signal/frontend/package-lock.json",
}


def included_files() -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in BANNED_DIRS for part in relative.parts):
            continue
        if path.name in BANNED_NAMES or path.suffix in BANNED_SUFFIXES:
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        files.append((path, Path("signal") / relative))
    return files


def main() -> None:
    files = included_files()
    OUTPUT.unlink(missing_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for source, archived in files:
            archive.write(source, archived.as_posix())

    with ZipFile(OUTPUT) as archive:
        names = archive.namelist()
        assert archive.testzip() is None
        assert len(names) == len(set(names))
        assert all(PurePosixPath(name).parts[0] == "signal" for name in names)
        assert not REQUIRED.difference(names)
        live_key = re.compile(rb"(?:sk|xi)-[A-Za-z0-9_-]{20,}")
        for item in archive.infolist():
            parts = PurePosixPath(item.filename).parts
            assert not any(part in BANNED_DIRS for part in parts)
            assert PurePosixPath(item.filename).name not in BANNED_NAMES
            assert PurePosixPath(item.filename).suffix not in BANNED_SUFFIXES
            if item.file_size <= 2_000_000:
                assert not live_key.search(archive.read(item))
        uncompressed = sum(item.file_size for item in archive.infolist())

    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"archive={OUTPUT}")
    print(f"files={len(files)}")
    print(f"uncompressed_bytes={uncompressed}")
    print(f"compressed_bytes={OUTPUT.stat().st_size}")
    print(f"sha256={digest}")
    print("zip_test=PASS")


if __name__ == "__main__":
    main()
