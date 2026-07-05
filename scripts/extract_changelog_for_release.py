from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"


def normalise_version(value: str) -> str:
    version = value.strip()
    if version.startswith("refs/tags/"):
        version = version.removeprefix("refs/tags/")
    if version.startswith("v"):
        version = version[1:]
    return version


def extract_entry(text: str, version: str) -> tuple[str, str, str]:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\] - (?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"CHANGELOG.md does not contain an entry for version {version}.")

    start = match.end()
    next_match = re.search(r"^## \[", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    body = text[start:end].strip()
    if not body:
        raise SystemExit(f"CHANGELOG.md entry for version {version} is empty.")
    return version, match.group("date"), body


def build_release_notes(version: str, date: str, body: str) -> str:
    return (
        f"# InSAR Studio {version}\n\n"
        "本项目不替代 SARscape、ISCE、MintPy、SNAP 或 ASF Vertex。"
        "它的定位是“处理前的数据准备助手”，帮助新手把下载、检查、目录组织和辅助数据准备流程做得更清楚。\n\n"
        "## 更新日志（中文）\n\n"
        f"[{version}] - {date}\n\n"
        f"{body}\n\n"
        "## 下载说明\n\n"
        "- `InSAR-Studio-*.exe`：全量单文件版，直接双击运行，本次不发布 setup 安装包。\n"
        "- DEM/GDAL 高程基准能力随发行版主程序内置；拆分组件模式仅用于内部测试。\n"
        "- `SHA256SUMS.txt`：发行资产校验值。\n\n"
        "## 注意事项\n\n"
        "- 发行包不包含账号、Token、下载历史、缓存、本机测试目录或私有数据。\n"
        "- 首次使用下载功能前，请在软件设置中校验必要凭据。\n"
        "- 当前在线更新以发现新版本和下载更新包为主；真正静默覆盖更新仍属于后续安装版更新器计划。\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a Chinese GitHub Release body from CHANGELOG.md."
    )
    parser.add_argument("--version", required=True, help="Version or tag, for example v2.1.4.")
    parser.add_argument(
        "--changelog",
        default=str(CHANGELOG),
        help="Path to CHANGELOG.md.",
    )
    parser.add_argument("--output", required=True, help="Release notes output path.")
    args = parser.parse_args()

    version = normalise_version(args.version)
    changelog = Path(args.changelog)
    output = Path(args.output)
    text = changelog.read_text(encoding="utf-8")
    release_version, date, body = extract_entry(text, version)
    notes = build_release_notes(release_version, date, body)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
