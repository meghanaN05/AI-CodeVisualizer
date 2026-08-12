"""Render Manim scenes and produce MP4 videos."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "outputs"
VIDEOS_DIR = OUTPUT_DIR / "videos"
SCENES_DIR = OUTPUT_DIR / "scenes"
MEDIA_DIR = OUTPUT_DIR / "media"


def _ensure_dirs() -> None:
    for directory in (VIDEOS_DIR, SCENES_DIR, MEDIA_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def render_video(manim_code: str) -> str:
    _ensure_dirs()

    scene_id = uuid.uuid4().hex[:10]
    scene_file = SCENES_DIR / f"scene_{scene_id}.py"
    scene_file.write_text(manim_code, encoding="utf-8")

    video_path = _run_manim(scene_file, scene_id)
    return f"/videos/{video_path.name}"


def _run_manim(scene_file: Path, scene_id: str) -> Path:
    manim_exe = shutil.which("manim")
    if manim_exe:
        command = [
            manim_exe,
            "-ql",
            "--disable_caching",
            f"--media_dir={MEDIA_DIR}",
            str(scene_file),
            "CodeVisualization",
        ]
    else:
        import sys

        command = [
            sys.executable,
            "-m",
            "manim",
            "-ql",
            "--disable_caching",
            f"--media_dir={MEDIA_DIR}",
            str(scene_file),
            "CodeVisualization",
        ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(SCENES_DIR),
    )

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "Unknown Manim error"
        raise RuntimeError(f"Manim rendering failed: {error[-2000:]}")

    generated = _find_generated_video(scene_id)
    if generated is None:
        raise RuntimeError("Manim finished but no MP4 file was produced")

    final_path = VIDEOS_DIR / f"{scene_id}.mp4"
    shutil.copy2(generated, final_path)
    return final_path


def _find_generated_video(scene_id: str) -> Path | None:
    scene_stem = f"scene_{scene_id}"
    candidates = sorted(
        MEDIA_DIR.rglob("CodeVisualization.mp4"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if scene_stem in str(candidate):
            return candidate

    if candidates:
        return candidates[0]
    return None
