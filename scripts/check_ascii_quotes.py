from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (
    ROOT / ".github" / "workflows",
    ROOT / "scripts",
    ROOT / "packaging",
)
SCAN_SUFFIXES = {".yml", ".yaml", ".ps1", ".iss", ".cmd", ".bat"}
FORBIDDEN = {
    "\u201c": "left double curly quote",
    "\u201d": "right double curly quote",
    "\u2018": "left single curly quote",
    "\u2019": "right single curly quote",
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in SCAN_SUFFIXES:
                files.append(path)
    return sorted(files)


def main() -> int:
    problems: list[str] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for char, label in FORBIDDEN.items():
                if char in line:
                    rel = path.relative_to(ROOT).as_posix()
                    problems.append(f"{rel}:{line_no}: contains {label} ({ord(char):#06x})")
    if problems:
        print("Curly Chinese quotes are not allowed in executable workflow/build scripts.")
        print("Use ASCII quotes in .yml/.ps1/.iss/.cmd/.bat files to avoid parser failures.")
        for problem in problems:
            print(problem)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
