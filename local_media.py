"""Use a video that is already on disk instead of copying it into uploads.

``LOCAL_MEDIA_ROOT`` is the only directory a caller may name. ``realpath``
resolves symlinks first, so a link inside the root that points outside is
rejected along with any other path outside the root.
"""
from __future__ import annotations

import os


class LocalMediaError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def resolve_local_media(raw: str, root: str) -> str:
    """Absolute path of a regular file inside ``root``.

    Raises ``LocalMediaError`` for an empty root, a path outside it, or a
    path that is not a file. The returned path is what the pipeline should
    open. Nothing is copied.
    """
    root = (root or "").strip()
    if not root:
        raise LocalMediaError(400, "local_path needs LOCAL_MEDIA_ROOT")
    root_real = os.path.realpath(root)
    if not os.path.isdir(root_real):
        raise LocalMediaError(400, "LOCAL_MEDIA_ROOT is not a directory")
    text = str(raw or "").strip()
    if not text:
        raise LocalMediaError(400, "local_path is empty")
    candidate = os.path.realpath(os.path.expanduser(text))
    try:
        inside = os.path.commonpath([root_real, candidate]) == root_real
    except ValueError:
        inside = False
    if not inside:
        raise LocalMediaError(400, "local_path is outside LOCAL_MEDIA_ROOT")
    if not os.path.isfile(candidate):
        raise LocalMediaError(404, "local_path is not a file")
    return candidate
