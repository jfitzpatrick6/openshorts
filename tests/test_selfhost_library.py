"""The jobs list and the kept-clip inbox stay inside their own directories."""
import os

import pytest

from local_media import LocalMediaError
from selfhost_library import (
    clip_scores, list_retained, retained_file, served_landscape_name, sort_jobs,
    summarize_job,
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
    assert row["scores"] == [None]


def test_summary_keeps_virality_scores_aligned_with_clips(tmp_path):
    row = summarize_job("abc12345-rest", {
        "status": "completed",
        "result": {"clips": [
            {"predicted_score": 84, "video_title_for_youtube_short": "First"},
            {"predicted_score": 71.6},
            {},
            {"predicted_score": "nope"},
            {"predicted_score": "79"},
            {"predicted_score": True},
        ]},
    }, str(tmp_path), 1.0)
    assert row["scores"] == [84, 72, None, None, 79, None]
    assert clip_scores("nope") == []


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


def _stick(root, episode, name, data=b"mp4"):
    run = root / episode / name
    run.mkdir(parents=True)
    (run / "stick.mp4").write_bytes(data)


def test_sticks_list_keeps_valid_rows_and_drops_escapes(tmp_path):
    import json
    from selfhost_library import list_sticks
    _stick(tmp_path, "show", "subtitled_1_show_clip_2", b"x" * 10)
    outside = tmp_path.parent / "elsewhere"
    (outside / "run").mkdir(parents=True, exist_ok=True)
    (outside / "run" / "stick.mp4").write_bytes(b"y")
    (tmp_path / "ep").mkdir()
    os.symlink(outside / "run", tmp_path / "ep" / "link")
    rows = [
        {"episode": "show", "name": "subtitled_1_show_clip_2", "source": "subtitled_1_show_clip_2.mp4", "status": "ok",
         "social": {"title": "A title", "tiktok": 7, "evil": "<x>", "instagram": "ig text"}},
        {"episode": "..", "name": "run", "status": "ok"},
        {"episode": "ep", "name": "link", "status": "ok"},
        {"episode": "show", "name": "missing", "status": "ok"},
        "junk",
    ]
    (tmp_path / "index.json").write_text(json.dumps({"sticks": rows}))
    out = list_sticks(str(tmp_path))
    assert out["enabled"] is True
    assert [s["name"] for s in out["sticks"]] == ["subtitled_1_show_clip_2"]
    assert out["sticks"][0]["bytes"] == 10
    assert out["sticks"][0]["label"] == "clip 2 · 9:16"
    assert out["sticks"][0]["url"] == "/api/sticks/show/subtitled_1_show_clip_2"
    assert out["sticks"][0]["social"] == {"title": "A title", "instagram": "ig text"}


def test_sticks_now_reports_fresh_progress_only(tmp_path):
    import json
    import time
    from selfhost_library import list_sticks
    now = {"episode": "show", "source": "subtitled_1_show_clip_3.mp4", "phase": "posing", "done": 40, "total": 200,
           "updated": time.time()}
    (tmp_path / "now.json").write_text(json.dumps(now))
    got = list_sticks(str(tmp_path))["now"]
    assert got["label"] == "clip 3 · 9:16" and got["done"] == 40 and got["total"] == 200
    (tmp_path / "now.json").write_text(json.dumps(dict(now, updated=time.time() - 3600)))
    assert list_sticks(str(tmp_path))["now"] is None


def test_sticks_list_is_off_without_a_root_and_empty_without_an_index(tmp_path):
    from selfhost_library import list_sticks
    assert list_sticks("")["enabled"] is False
    assert list_sticks(str(tmp_path)) == {"enabled": True, "now": None, "sticks": []}


def test_stick_file_rejects_bad_segments(tmp_path):
    from selfhost_library import stick_file
    _stick(tmp_path, "show", "run")
    assert stick_file(str(tmp_path), "show", "run").endswith("stick.mp4")
    for episode, name in (("..", "run"), ("show", "../run"), (".hidden", "run"), ("show", "")):
        with pytest.raises(LocalMediaError):
            stick_file(str(tmp_path), episode, name)


def test_sticks_list_adds_the_story_version_when_present(tmp_path):
    import json
    from selfhost_library import list_sticks, stick_file
    run = _stick(tmp_path, "show", "subtitled_1_show_clip_2")
    rows = [{"episode": "show", "name": "subtitled_1_show_clip_2", "source": "subtitled_1_show_clip_2.mp4"}]
    (tmp_path / "index.json").write_text(json.dumps({"sticks": rows}))
    assert "story_url" not in list_sticks(str(tmp_path))["sticks"][0]
    (tmp_path / "show" / "subtitled_1_show_clip_2" / "story").mkdir()
    (tmp_path / "show" / "subtitled_1_show_clip_2" / "story" / "story.mp4").write_bytes(b"s" * 7)
    got = list_sticks(str(tmp_path))["sticks"][0]
    assert got["story_url"] == "/api/sticks/show/subtitled_1_show_clip_2/story" and got["story_bytes"] == 7
    assert stick_file(str(tmp_path), "show", "subtitled_1_show_clip_2", "story").endswith("story.mp4")
    import pytest
    from local_media import LocalMediaError
    with pytest.raises(LocalMediaError):
        stick_file(str(tmp_path), "show", "subtitled_1_show_clip_2", "../x")
