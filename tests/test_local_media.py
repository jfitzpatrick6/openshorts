"""local_path must name a real file inside LOCAL_MEDIA_ROOT and nothing else."""
import os

import pytest

from local_media import LocalMediaError, resolve_local_media


def test_a_file_inside_the_root_is_the_same_file(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    video = root / "episode.mp4"
    video.write_bytes(b"video-bytes")

    found = resolve_local_media(str(video), str(root))

    assert found == os.path.realpath(video)
    assert os.stat(found).st_ino == video.stat().st_ino


def test_a_sibling_prefix_is_outside(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    evil = tmp_path / "raw-evil"
    evil.mkdir()
    video = evil / "episode.mp4"
    video.write_bytes(b"x")

    with pytest.raises(LocalMediaError) as exc:
        resolve_local_media(str(video), str(root))
    assert exc.value.status == 400


def test_a_symlink_out_of_the_root_is_rejected(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"secret")
    link = root / "looks-local.mp4"
    link.symlink_to(outside)

    with pytest.raises(LocalMediaError) as exc:
        resolve_local_media(str(link), str(root))
    assert exc.value.status == 400


def test_missing_file_and_empty_root(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    with pytest.raises(LocalMediaError) as missing:
        resolve_local_media(str(root / "nope.mp4"), str(root))
    assert missing.value.status == 404
    with pytest.raises(LocalMediaError) as disabled:
        resolve_local_media(str(root / "nope.mp4"), "")
    assert disabled.value.status == 400
