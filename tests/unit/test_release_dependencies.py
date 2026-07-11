from __future__ import annotations

import tomllib
from pathlib import Path


def test_full_desktop_selftest_dependencies_are_declared_in_convert_extra() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    convert_deps = {
        dep.split(";", 1)[0]
        .split("[", 1)[0]
        .split(">", 1)[0]
        .split("<", 1)[0]
        .split("=", 1)[0]
        .strip()
        .lower()
        for dep in project["project"]["optional-dependencies"]["convert"]
    }

    assert {"numpy", "pyproj", "rasterio"} <= convert_deps


def test_desktop_brand_assets_use_contour_orbit_svg() -> None:
    mark_path = Path("ui/public/app-icon.svg")
    lockup_path = Path("ui/public/app-logo.svg")
    workbench_path = Path("ui/src/pages/Workbench.tsx")

    assert mark_path.is_file()
    assert lockup_path.is_file()

    mark = mark_path.read_text(encoding="utf-8")
    lockup = lockup_path.read_text(encoding="utf-8")
    workbench = workbench_path.read_text(encoding="utf-8")

    for asset in (mark, lockup):
        assert "topographic interference contours" in asset.lower()
        assert "orbit-navy" in asset
        assert "orbit-teal" in asset
        assert "prefers-color-scheme" not in asset

    assert 'src={dark ? "/app-logo.svg#dark" : "/app-logo.svg"}' in workbench
    assert 'src="/app-logo.png"' not in workbench


def test_community_dialog_keeps_github_repository_link() -> None:
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")

    assert 'communityGithub: "https://github.com/hhanmj/insar_studio"' in workbench
    assert 'src="/github-mark.svg"' in workbench
    assert ">GitHub Stars</span>" in workbench
    assert "<Star className=\"h-3.5 w-3.5 fill-current\" />" in workbench
    assert "<ExternalLink className=\"h-3 w-3\" />" in workbench
    assert "mask-image:url('/github-mark.svg')" not in workbench
    assert Path("ui/public/github-mark.svg").is_file()
    assert "void openUrl(LINKS.communityGithub)" in workbench
    assert 'title="打开 InSAR Studio GitHub 仓库"' in workbench


def test_update_prompt_checks_once_per_startup_and_dismisses_one_version() -> None:
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")
    assert 'UPDATE_PROMPT_DISMISSED_KEY = "insar.updatePrompt.dismissedVersion"' in workbench
    assert "window.setInterval" not in workbench.split("async function checkUpdate()", 1)[1].split("}, [", 1)[0]
    assert "updatePromptAlreadyDismissed(res.latest_version)" in workbench
    assert "dismissUpdatePromptVersion(updateInfo.latest_version)" in workbench
    assert "不再提示此版本" in workbench


def test_windows_icon_contains_all_supported_sizes() -> None:
    data = Path("packaging/app_icon.ico").read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"
    count = int.from_bytes(data[4:6], "little")
    sizes: set[tuple[int, int]] = set()
    for index in range(count):
        offset = 6 + index * 16
        width = data[offset] or 256
        height = data[offset + 1] or 256
        sizes.add((width, height))

    assert sizes == {
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    }


def test_desktop_build_can_explicitly_skip_rust_core() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "build_windows_desktop_exe.ps1"
    script = script_path.read_text(encoding="utf-8")

    assert "[switch]$SkipRustCore" in script
    assert "if (-not $SkipRustCore)" in script


def test_frontend_fallback_version_matches_project_version() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    bridge = Path("ui/src/lib/bridge.ts").read_text(encoding="utf-8")
    version = project["project"]["version"]

    assert f'version: "{version}"' in bridge
    assert f'current_version: "{version}"' in bridge
    assert 'version: "2.1.8"' not in bridge


def test_workbench_keeps_search_batch_and_download_task_state_isolated() -> None:
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")

    assert "sceneSearchBatchId" in workbench
    assert "sceneSearchAoiName" in workbench
    assert "snapshot.batchId === sceneSearchBatchId" in workbench
    assert 'const snapshotAoiName = existingSnapshot?.aoiName || sceneSearchAoiName' in workbench
    assert 'sceneWorkspaceScope === "task" && sceneWorkspaceDownloadActive' in workbench
    assert "sceneWorkspaceTaskIds.has(status.task_id" in workbench

    bridge = Path("ui/src/lib/bridge.ts").read_text(encoding="utf-8")
    assert "useProductSubdirs, aoiName" in bridge
    assert "useOrbitSubdir, aoiName" in bridge


def test_task_snapshot_controls_share_task_pause_state() -> None:
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")

    assert "const sceneWorkspaceTaskPaused" in workbench
    assert "onPauseAsfScenes(selectedPausableSceneIds, sceneWorkspaceActionTaskId)" in workbench
    assert "onResumeAsfScenes(selectedPausedSceneIds, sceneWorkspaceActionTaskId)" in workbench
    assert "pauseAsfDownload(taskId)" in workbench
    assert "resumeAsfDownload(taskId)" in workbench
    assert "sceneWorkspaceEffectiveActiveDownloads" in workbench
    assert "sceneWorkspaceEffectivePausedSceneIds" in workbench
    assert 'sceneWorkspaceScope === "task" && (' in workbench
    overlay = workbench.split("function renderSceneWorkspaceOverlay()", 1)[1]
    assert 'sceneWorkspaceScope === "task" && (' in overlay
    assert "暂停所选" in overlay
    assert "继续所选" in overlay


def test_archived_task_snapshot_restores_from_frozen_archive() -> None:
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")

    assert "task.snapshot ?? []" in workbench
    assert "openArchivedSceneSnapshot(task)" in workbench
    assert "startAsfDownloadSnapshot(" in workbench
    assert "task.scene_ids ??" in workbench


def test_orbit_subdirectory_includes_product_type() -> None:
    api = Path("src/insar_prep/desktop/api.py").read_text(encoding="utf-8")
    workbench = Path("ui/src/pages/Workbench.tsx").read_text(encoding="utf-8")

    assert 'Path(out) / "Sentinel_Orbit" / "AUX_POEORB"' in api
    assert "所选目录\\Sentinel_Orbit\\AUX_POEORB" in workbench
