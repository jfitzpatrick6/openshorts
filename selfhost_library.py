"""What a self-host dashboard can list without a cloud account.

Working jobs already live in the OpenShorts output directory. Kept clips are
a separate directory (the 30-day inbox) named by ``RETAINED_CLIPS_ROOT``.
Nothing outside that directory can be listed or streamed.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote

from local_media import LocalMediaError, resolve_local_media

_CLIP_NUM = re.compile(r"_clip_(\d+)\.mp4$", re.IGNORECASE)
_TITLE_KEYS = (
    "video_title_for_youtube_short",
    "title",
    "headline",
    "viral_hook_text",
)


def clip_title(clip: dict) -> str:
    """The shortest human title a clip record carries, or ''."""
    if not isinstance(clip, dict):
        return ""
    for key in _TITLE_KEYS:
        value = clip.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def source_name(output_dir: str) -> str:
    """Basename recorded for a local_path job, or ''."""
    try:
        with open(os.path.join(output_dir, "source_path.txt")) as handle:
            text = handle.read().strip()
    except OSError:
        return ""
    return os.path.basename(text)


def summarize_job(job_id: str, record: dict, output_dir: str, updated_at: float | None) -> dict:
    """One row for the jobs list. ``record`` is the in-memory job dict."""
    result = record.get("result") or {}
    clips = result.get("clips") if isinstance(result, dict) else None
    if not isinstance(clips, list):
        clips = []
    title = ""
    for clip in clips:
        title = clip_title(clip)
        if title:
            break
    source = source_name(output_dir)
    last = ""
    for line in reversed(list(record.get("logs") or [])):
        if isinstance(line, str) and line.strip():
            last = line.strip()
            break
    return {
        "job_id": job_id,
        "status": str(record.get("status") or "unknown"),
        "title": title or source or job_id[:8],
        "source": source,
        "clip_count": len(clips),
        "log": last[:240],
        "updated_at": updated_at,
    }


def sort_jobs(rows: list[dict]) -> list[dict]:
    """Working jobs first, then the most recently touched."""
    def key(row: dict):
        working = row.get("status") in ("processing", "queued")
        stamp = row.get("updated_at") or 0
        return (0 if working else 1, -stamp)

    return sorted(rows, key=key)


def _clip_label(filename: str) -> str:
    match = _CLIP_NUM.search(filename)
    if match:
        return f"clip {int(match.group(1))}"
    return filename


def _inside_dir(root_real: str, path: str) -> bool:
    try:
        return os.path.commonpath([root_real, os.path.realpath(path)]) == root_real
    except ValueError:
        return False


def list_retained(root: str, days: int, now: float) -> dict:
    """Episodes and mp4s inside ``root``.

    An empty or missing root disables the list. A symlink that leaves the
    root is skipped. ``days`` is how long the prune keeps a file, so
    ``days_left`` can hit zero while the file is still on disk.
    """
    root = (root or "").strip()
    payload = {"enabled": False, "days": days, "episodes": []}
    if not root:
        return payload
    root_real = os.path.realpath(root)
    if not os.path.isdir(root_real):
        return payload
    payload["enabled"] = True
    episodes = []
    try:
        names = sorted(os.listdir(root_real))
    except OSError:
        return payload
    for name in names:
        if not name or name.startswith("."):
            continue
        episode_dir = os.path.join(root_real, name)
        if not _inside_dir(root_real, episode_dir) or not os.path.isdir(episode_dir):
            continue
        clips = []
        try:
            files = sorted(os.listdir(episode_dir))
        except OSError:
            continue
        for filename in files:
            if not filename.lower().endswith(".mp4") or filename.startswith("."):
                continue
            try:
                path = retained_file(root_real, name, filename)
            except LocalMediaError:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            age_days = int(max(0, now - st.st_mtime) // 86400)
            clips.append({
                "name": filename,
                "label": _clip_label(filename),
                "bytes": st.st_size,
                "mtime": st.st_mtime,
                "days_left": max(0, days - age_days),
                "url": "/api/retained/" + quote(name, safe="") + "/" + quote(filename, safe=""),
            })
        if not clips:
            continue
        clips.sort(key=lambda item: (_clip_sort(item["name"]), item["name"]))
        episodes.append({
            "name": name,
            "updated_at": max(item["mtime"] for item in clips),
            "clips": clips,
        })
    episodes.sort(key=lambda item: item["updated_at"], reverse=True)
    payload["episodes"] = episodes
    return payload


def _clip_sort(filename: str) -> int:
    match = _CLIP_NUM.search(filename)
    return int(match.group(1)) if match else 10**9


def retained_file(root: str, episode: str, filename: str) -> str:
    """Absolute path of one kept mp4, or raise ``LocalMediaError``.

    Both components have to be a single path segment. The resolved path
    still has to land inside ``root``, so a symlink out of the inbox fails.
    """
    episode = str(episode or "").strip()
    filename = str(filename or "").strip()
    if not episode or not filename:
        raise LocalMediaError(400, "missing clip path")
    if _bad_segment(episode) or _bad_segment(filename):
        raise LocalMediaError(400, "bad clip path")
    if not filename.lower().endswith(".mp4"):
        raise LocalMediaError(404, "not a clip")
    return resolve_local_media(os.path.join(root, episode, filename), root)


def _bad_segment(segment: str) -> bool:
    if segment in (".", "..") or segment.startswith("."):
        return True
    return "/" in segment or "\\" in segment or "\x00" in segment
