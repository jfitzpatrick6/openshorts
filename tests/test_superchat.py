"""Superchat cuts: amounts, the read-voice handoff, and which replies are kept."""
import superchat


def _words(*pairs):
    out = []
    for text, start in pairs:
        out.append({"w": text, "s": start, "e": start + 0.25})
    return out


def _grid(start, end, spans, default_cos=0.70):
    frames = []
    t = start
    while t < end - 1e-6:
        cos, speech = default_cos, True
        for a, b, c, spoken in spans:
            if a <= t < b:
                cos, speech = c, spoken
                break
        frames.append({"t": round(t, 3), "cosine": cos, "speech": speech})
        t = round(t + superchat.HOP, 3)
    return frames


def test_amounts_keep_reads_and_drop_plugs_and_asides():
    words = _words(
        ("Groy", 0.0), ("percent", 0.4), ("$20.", 0.8),
        ("subscribe", 10.0), ("$15", 10.4), ("a", 10.8), ("month", 11.1),
        ("our", 12.0), ("100", 12.3), ("bucks", 12.6), ("a", 13.0), ("month", 13.3),
        ("a", 20.0), ("hundred", 20.4), ("million", 20.8), ("dollars", 21.2),
        ("thousands", 22.0), ("of", 22.3), ("dollars", 22.6),
        ("said", 30.0), ("one", 30.4), ("hundred", 30.8), ("dollars", 31.2),
        ("twenty", 40.0), ("dollars", 40.4),
        ("sent", 50.0), ("20", 50.4), ("dollars", 50.8),
        ("two", 60.0), ("hundred", 60.4), ("dollars", 60.8),
        ("said", 70.0), ("they", 70.3), ("found", 70.6),
    )
    found = [(round(item["start"], 1), item["dollars"]) for item in superchat.find_amounts(words)]
    assert found == [
        (0.8, 20.0),
        (30.4, 100.0),
        (40.0, 20.0),
        (50.4, 20.0),
        (60.0, 200.0),
    ]


def test_cluster_keeps_the_agreeing_voice_only():
    read = [1.0, 0.0]
    host = [0.0, 1.0]
    mixed = [0.7, 0.7]
    kept, centroid = superchat.cluster_members([read] * 5 + [host, mixed])
    assert kept == [0, 1, 2, 3, 4]
    assert centroid is not None
    assert superchat._cosine(centroid, read) > 0.99

    too_few, nothing = superchat.cluster_members([read] * 3 + [host])
    assert too_few == []
    assert nothing is None


def test_handoff_ignores_a_blip_and_fences_on_the_next_read():
    # The shape measured on the fiancée answer: a read, his voice, a short
    # false blip, then the next donation's read a bit later.
    frames = _grid(5840, 5900, [
        (5841.5, 5848.5, 0.98, True),
        (5854.0, 5856.0, 0.98, True),
        (5882.0, 5888.0, 0.98, True),
    ])
    amounts = [{"start": 5845.0, "dollars": 100}, {"start": 5895.0, "dollars": 20}]
    bounds = superchat.bound_exchange(frames, amounts[0], amounts)
    assert bounds["reason"] is None
    assert bounds["mode"] == "tts"
    assert 5841.0 <= bounds["clip_start"] <= 5842.5
    assert 5848.0 <= bounds["reply_start"] <= 5849.5
    assert bounds["fence"] == 5882.0


def test_stacked_reads_keep_only_the_one_he_answers():
    frames = _grid(0, 40, [(0.0, 20.0, 0.98, True)])
    first = {"start": 2.0, "dollars": 20}
    second = {"start": 10.0, "dollars": 200}
    early = superchat.bound_exchange(frames, first, [first, second])
    late = superchat.bound_exchange(frames, second, [first, second])
    assert early["reason"] == "stacked"
    assert late["reason"] is None
    assert 7.0 <= late["clip_start"] <= 8.0
    assert late["reply_start"] == 20.0


def test_isolated_answer_has_no_fence():
    frames = _grid(0, 220, [
        (0.0, 5.0, 0.98, True),
        (200.0, 206.0, 0.98, True),
    ])
    amounts = [{"start": 2.0, "dollars": 20}, {"start": 203.0, "dollars": 20}]
    bounds = superchat.bound_exchange(frames, amounts[0], amounts)
    assert bounds["reason"] is None
    assert bounds["fence"] is None
    assert bounds["reply_start"] == 5.0


def test_short_reply_and_short_window_never_reach_the_judge():
    words = _words(("thanks", 6.0), ("man", 6.4))
    short_window = superchat.gate_exchange({
        "onset": 1.0, "dollars": 20, "cosine": 0.98, "mode": "tts",
        "clip_start": 0.0, "reply_start": 4.0, "fence": 10.0, "reason": None,
    }, words, 15, 120)
    assert short_window["reason"] == "short-window"

    words = _words(*[(f"w{i}", 6.0 + i * 0.4) for i in range(8)])
    short_reply = superchat.gate_exchange({
        "onset": 1.0, "dollars": 20, "cosine": 0.98, "mode": "tts",
        "clip_start": 0.0, "reply_start": 6.0, "fence": 16.0, "reason": None,
    }, words, 15, 120)
    assert short_reply["reason"] == "short-reply"


def test_self_read_fences_on_the_next_amount():
    frames = _grid(0, 50, [])
    amounts = [{"start": 10.0, "dollars": 20}, {"start": 40.0, "dollars": 20}]
    bounds = superchat.bound_exchange(frames, amounts[0], amounts)
    assert bounds["mode"] == "self"
    assert bounds["reason"] is None
    assert bounds["fence"] == 40.0
    assert bounds["clip_start"] <= 10.0


def test_no_host_between_reads_is_not_a_reply():
    # Half a second of him between two reads is a dip, not an answer.
    frames = _grid(0, 30, [(0.0, 8.5, 0.98, True), (9.0, 14.0, 0.98, True)])
    amounts = [{"start": 2.0, "dollars": 20}, {"start": 11.0, "dollars": 20}]
    bounds = superchat.bound_exchange(frames, amounts[0], amounts)
    assert bounds["reason"] == "stacked"


def test_judge_keeps_two_and_ranks_the_rest_out():
    words = []
    t = 0.0
    while t < 400:
        words.append({"w": "word", "s": t, "e": t + 0.2})
        t += 0.4
    frames = _grid(0, 400, [
        (10.0, 16.0, 0.98, True),
        (70.0, 76.0, 0.98, True),
        (130.0, 136.0, 0.98, True),
        (200.0, 206.0, 0.98, True),
    ])
    amounts = [
        {"start": 12.0, "dollars": 20},
        {"start": 72.0, "dollars": 20},
        {"start": 132.0, "dollars": 100},
        {"start": 202.0, "dollars": 20},
    ]

    def judge(candidates):
        out = []
        for candidate in candidates:
            out.append({
                "index": candidate["index"],
                "keep": True,
                "score": {12.0: 40, 72.0: 95, 132.0: 80, 202.0: 60}.get(candidate["onset"], 10),
                "end": candidate["latest"] - 1,
                "video_title_for_youtube_short": f"answer {candidate['onset']:.0f}",
                "viral_hook_text": "he answers",
                "video_description_for_tiktok": "",
                "video_description_for_instagram": "",
                "why": "answers",
            })
        return out

    result = superchat.decide(words, amounts, frames, judge, 15, 120, top=2)
    titles = [clip["video_title_for_youtube_short"] for clip in result["clips"]]
    assert titles == ["answer 72", "answer 132"]
    assert [clip["video_title_for_youtube_short"] for clip in result["ranked_out"]] == [
        "answer 12", "answer 202",
    ]
    assert all(clip["superchat"] is True for clip in result["clips"])
    assert all(clip["end"] - clip["start"] <= 120 for clip in result["clips"])


def test_thanks_and_a_missing_end_are_dropped():
    words = _words(*[(f"w{i}", 10.0 + i * 0.4) for i in range(80)])
    frames = _grid(0, 80, [(5.0, 10.0, 0.98, True)])
    amounts = [{"start": 6.0, "dollars": 20}]

    def judge(candidates):
        return [{"index": 0, "keep": False, "score": 0, "end": 0,
                 "video_title_for_youtube_short": "", "viral_hook_text": "",
                 "video_description_for_tiktok": "", "video_description_for_instagram": "",
                 "why": "thanks"}]

    result = superchat.decide(words, amounts, frames, judge, 15, 120)
    assert result["clips"] == []
    assert result["rows"][-1]["reason"] == "thanks"

    def missing_end(candidates):
        return [{"index": 0, "keep": True, "score": 80, "end": 0,
                 "video_title_for_youtube_short": "no end", "viral_hook_text": "",
                 "video_description_for_tiktok": "", "video_description_for_instagram": "",
                 "why": ""}]

    result = superchat.decide(words, amounts, frames, missing_end, 15, 120)
    assert result["clips"] == []
    assert result["rows"][-1]["reason"] == "short-answer"


def test_place_widens_a_late_viral_clip_and_skips_a_covered_one():
    shorts = [
        {"start": 20.0, "end": 55.0, "video_title_for_youtube_short": "viral"},
        {"start": 100.0, "end": 140.0, "video_title_for_youtube_short": "other"},
    ]
    extras = [
        {"start": 12.0, "end": 50.0, "predicted_score": 80,
         "video_title_for_youtube_short": "the answer", "viral_hook_text": "hook",
         "video_description_for_tiktok": "t", "video_description_for_instagram": "i",
         "why": "because"},
        {"start": 105.0, "end": 145.0, "predicted_score": 70,
         "video_title_for_youtube_short": "already covered", "viral_hook_text": ""},
        {"start": 200.0, "end": 240.0, "predicted_score": 60,
         "video_title_for_youtube_short": "extra", "viral_hook_text": ""},
    ]
    added, widened = superchat.place_superchats(shorts, extras, max_seconds=120)
    assert widened == 1
    assert added == 1
    assert shorts[0]["start"] == 12.0
    assert shorts[0]["end"] == 55.0
    assert shorts[0]["superchat"] is True
    assert shorts[0]["video_title_for_youtube_short"] == "the answer"
    assert shorts[1]["video_title_for_youtube_short"] == "other"
    assert shorts[2]["video_title_for_youtube_short"] == "extra"


def test_place_does_not_let_a_widen_run_past_the_cap():
    shorts = [{"start": 10.0, "end": 130.0, "video_title_for_youtube_short": "long"}]
    extras = [{"start": 0.0, "end": 110.0, "predicted_score": 50,
               "video_title_for_youtube_short": "capped", "viral_hook_text": ""}]
    added, widened = superchat.place_superchats(shorts, extras, max_seconds=120)
    assert added == 0
    assert widened == 1
    assert shorts[0]["end"] - shorts[0]["start"] <= 120
    assert shorts[0]["end"] == 110.0
