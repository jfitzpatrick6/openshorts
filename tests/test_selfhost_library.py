"""The jobs list and the kept-clip inbox stay inside their own directories."""
import os

import pytest

from local_media import LocalMediaError
from selfhost_library import (
    list_retained, retained_file, served_landscape_name, sort_jobs, summarize_job,
)


def test_summary_prefers_a_clip_title_and_the_last_log(tmp_path):
    output = tmp_path / "job"
    output.mkdir()
    (output / "source_path.txt").write_text(str(tmp_path / "raw" / "episode.mp4"))
    row = summarize_job("abc12345-rest", {
        "status": "completed",
        "logs": ["starting", "  done  "],
        "result": {"clips": [{
            "viral_hook_text": "hook",
            "video_title_for_youtube_short": "The real title",
        }]},
    }, str(output), 10.0)
    assert row["title"] == "The real title"
    assert row["source"] == "episode.mp4"
    assert row["clip_count"] == 1
    assert row["log"] == "done"
    assert row["status"] == "completed"


def test_working_jobs_sort_ahead_of_newer_finished_ones():
    rows = [
        {"status": "completed", "updated_at": 50},
        {"status": "processing", "updated_at": 1},
        {"status": "queued", "updated_at": 2},
    ]
    ordered = [row["status"] for row in sort_jobs(rows)]
    assert ordered == ["queued", "processing", "completed"]


def test_retained_list_orders_episodes_and_skips_an_escape(tmp_path):
    root = tmp_path / "inbox"
    older = root / "older show"
    newer = root / "newer show"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "show_clip_2.mp4").write_bytes(b"bb")
    first = older / "subtitled_1_show_clip_1.mp4"
    first.write_bytes(b"a")
    os.utime(first, (1_000, 1_000))
    os.utime(older / "show_clip_2.mp4", (2_000, 2_000))
    fresh = newer / "show_clip_1.mp4"
    fresh.write_bytes(b"ccc")
    os.utime(fresh, (5_000, 5_000))
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"nope")
    (root / "newer show" / "leak.mp4").symlink_to(outside)

    payload = list_retained(str(root), 30, now=5_000 + 2 * 86400)
    assert payload["enabled"] is True
    assert [item["name"] for item in payload["episodes"]] == ["newer show", "older show"]
    newer_clips = payload["episodes"][0]["clips"]
    assert [clip["name"] for clip in newer_clips] == ["show_clip_1.mp4"]
    older_clips = payload["episodes"][1]["clips"]
    assert [clip["label"] for clip in older_clips] == ["clip 1 · 9:16", "clip 2 · 9:16"]
    assert [clip["shape"] for clip in older_clips] == ["9:16", "9:16"]
    assert older_clips[0]["days_left"] == 28
    assert " " not in newer_clips[0]["url"]
    assert newer_clips[0]["url"].startswith("/api/retained/")


def test_landscape_twins_sort_after_the_vertical_of_the_same_moment(tmp_path):
    root = tmp_path / "inbox"
    show = root / "show"
    show.mkdir(parents=True)
    (show / "show_clip_1_16x9.mp4").write_bytes(b"w")
    (show / "subtitled_9_show_clip_1.mp4").write_bytes(b"v")
    (show / "subtitled_9_show_clip_2_16x9.mp4").write_bytes(b"ww")
    payload = list_retained(str(root), 30, now=0)
    clips = payload["episodes"][0]["clips"]
    assert [clip["label"] for clip in clips] == [
        "clip 1 · 9:16",
        "clip 1 · 16:9",
        "clip 2 · 16:9",
    ]
    assert [clip["shape"] for clip in clips] == ["9:16", "16:9", "16:9"]


def test_landscape_name_rejects_a_path():
    assert served_landscape_name({"landscape_file": "subtitled_1_ep_clip_1_16x9.mp4"}) == (
        "subtitled_1_ep_clip_1_16x9.mp4"
    )
    assert served_landscape_name({"landscape_file": "../secret.mp4"}) == ""
    assert served_landscape_name({"landscape_file": ".hidden.mp4"}) == ""
    assert served_landscape_name({}) == ""


def test_empty_root_disables_the_list(tmp_path):
    assert list_retained("", 30, now=0)["enabled"] is False
    assert list_retained(str(tmp_path / "missing"), 30, now=0)["enabled"] is False


def test_retained_file_rejects_a_symlink_and_a_non_video(tmp_path):
    root = tmp_path / "inbox"
    episode = root / "show"
    episode.mkdir(parents=True)
    (episode / "notes.txt").write_text("no")
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"x")
    (episode / "looks.mp4").symlink_to(outside)

    with pytest.raises(LocalMediaError) as missing:
        retained_file(str(root), "show", "notes.txt")
    assert missing.value.status == 404
    with pytest.raises(LocalMediaError) as escaped:
        retained_file(str(root), "show", "looks.mp4")
    assert escaped.value.status == 400
    with pytest.raises(LocalMediaError):
        retained_file(str(root), "..", "secret.mp4")
    with pytest.raises(LocalMediaError):
        retained_file(str(root), "show", "../secret.mp4")
