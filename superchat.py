"""Extra clips for host-read superchats.

A superchat on this show is one voice reading the name, the amount, and the
message, then the host answering in his own voice. Whisper writes both as one
transcript, so the cut is a speaker change: the clip opens when the read
starts and closes when the answer does. The five ordinary clips are left
alone. This pass adds at most two, and only when the reply is a real answer.

The read voice is whichever voice sits on the dollar amounts and agrees with
itself. Pitch is not used. If those amounts do not cluster, the pass returns
nothing rather than guessing a cut. Thank-you reads and reads with no answer
are dropped. A reply so short that a 15s clip would swallow the next chat is
dropped instead of padded.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
from typing import Optional

from pydantic import BaseModel

# Timeline hop. Each frame covers WIN seconds of audio starting at t.
HOP = 0.5
WIN = 1.0
# Cosine against the read-voice centroid.
TTS_COSINE = 0.95
SELF_COSINE = 0.85
# A single half-second dip does not end a read. One second of the other voice does.
HOST_END = 1.0
# A later read fences the reply only when it is a real read, not a blip.
FENCE_MIN_RUN = 3.0
FENCE_BEFORE = 1.0
FENCE_AFTER = 15.0
# Farther than this, the next read is a different stretch of the show.
ISOLATED_GAP = 90.0
MIN_HOST_SECONDS = 12.0
MIN_HOST_WORDS = 30
MIN_CLUSTER = 4
CLUSTER_COSINE = 0.93
READ_BACK = 15.0
READ_AHEAD = 45.0
SELF_BACK = 4.0
# How far before an amount the donor's name usually starts. Used when several
# reads are stacked in one uninterrupted TTS stretch.
NAME_LEAD = 2.5
TOP = 2
EMBED_VERSION = "mel32-w1-h0.5-v1"

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_UNIT = {"dollar", "dollars", "buck", "bucks"}
_HUGE = {"million", "billion", "trillion", "thousands", "hundreds"}
_PLUG = {"month", "monthly", "months", "year", "yearly", "annual",
         "annually", "week", "weekly", "subscription"}
_DOLLAR = re.compile(r"^\$(\d+(?:\.\d+)?)$")
_DIGITS = re.compile(r"^(\d+(?:\.\d+)?)$")


def flatten_words(transcript) -> list:
    """Word timings as ``{w, s, e}``, sorted by start."""
    out = []
    for segment in (transcript or {}).get("segments") or []:
        for word in segment.get("words") or []:
            text = word.get("word", word.get("w"))
            if text is None:
                continue
            text = str(text).strip()
            if not text:
                continue
            start = word.get("start", word.get("s"))
            end = word.get("end", word.get("e"))
            try:
                start_f, end_f = float(start), float(end)
            except (TypeError, ValueError):
                continue
            out.append({"w": text, "s": start_f, "e": end_f})
    out.sort(key=lambda item: item["s"])
    return out


def _flat_tokens(words):
    flat = []
    for index, word in enumerate(words):
        raw = str(word["w"]).lower()
        for part in re.split(r"[^a-z0-9$]+", raw):
            if part:
                flat.append((part, index))
    return flat


def _parse_spoken(tokens, index):
    """A number of dollars starting at ``index``.

    Returns ``(value, last_index)``, ``("huge", last_index)`` when the figure
    is a million-style aside, or ``None``.
    """
    current = 0
    seen = False
    j = index
    limit = min(len(tokens), index + 8)
    while j < limit:
        tok = tokens[j][0]
        if tok in ("a", "an") and not seen:
            nxt = tokens[j + 1][0] if j + 1 < len(tokens) else ""
            if nxt == "hundred" or nxt == "thousand":
                j += 1
                continue
            return None
        if tok in ("and", "a", "an") and seen:
            j += 1
            continue
        if tok == "hundred":
            current = max(current, 1) * 100
            seen = True
            j += 1
            continue
        if tok == "thousand":
            current = max(current, 1) * 1000
            seen = True
            j += 1
            continue
        if tok in _TENS:
            current += _TENS[tok]
            seen = True
            j += 1
            continue
        if tok in _ONES:
            current += _ONES[tok]
            seen = True
            j += 1
            continue
        if _DIGITS.match(tok):
            current += float(tok) if "." in tok else int(tok)
            seen = True
            j += 1
            continue
        if tok in _HUGE:
            return "huge", j
        if tok in _UNIT:
            if not seen or current <= 0:
                return None
            return current, j
        return None
    return None


def _is_plug(flat, end_index) -> bool:
    # "a month" / "per month" sits immediately after the figure. A wider window
    # catches the word "month" in the next sentence and drops a real donation.
    after = [flat[k][0] for k in range(end_index + 1, min(len(flat), end_index + 4))]
    return any(tok in _PLUG for tok in after)


def _nearby_huge(flat, start_index, end_index) -> bool:
    lo = max(0, start_index - 3)
    hi = min(len(flat), end_index + 4)
    return any(flat[k][0] in _HUGE for k in range(lo, hi))


def find_amounts(words) -> list:
    """Dollar amounts in ``words``, minus subscribe plugs and million-scale asides.

    The word "sent" is not required. Whisper often hears it as "percent" or
    "cent", and the amount is still there.
    """
    flat = _flat_tokens(words)
    amounts = []
    i = 0
    while i < len(flat):
        tok, word_index = flat[i]
        parsed = None
        match = _DOLLAR.match(tok)
        if match:
            value = float(match.group(1))
            parsed = (value, i) if value > 0 else None
        elif tok == "$" and i + 1 < len(flat) and _DIGITS.match(flat[i + 1][0]):
            value = float(flat[i + 1][0])
            parsed = (value, i + 1) if value > 0 else None
        else:
            spoken = _parse_spoken(flat, i)
            if spoken is not None:
                parsed = spoken
        if parsed is None:
            i += 1
            continue
        value, end = parsed
        end_word = flat[end][1]
        if value == "huge" or _nearby_huge(flat, i, end) or _is_plug(flat, end):
            i = end + 1
            while i < len(flat) and flat[i][1] <= end_word:
                i += 1
            continue
        amounts.append({
            "start": words[word_index]["s"],
            "end": words[end_word]["e"],
            "dollars": float(value),
            "word_index": word_index,
        })
        i = end + 1
        while i < len(flat) and flat[i][1] <= end_word:
            i += 1
    return amounts


def _cosine(a, b) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _mean_unit(vectors):
    dim = len(vectors[0])
    mean = [0.0] * dim
    for vector in vectors:
        for i, value in enumerate(vector):
            mean[i] += value
    scale = 1.0 / len(vectors)
    mean = [value * scale for value in mean]
    norm = math.sqrt(sum(value * value for value in mean))
    if norm <= 0.0:
        return None
    return [value / norm for value in mean]


def cluster_members(vectors, min_cosine=CLUSTER_COSINE, min_members=MIN_CLUSTER):
    """Keep the vectors that agree with their own mean.

    Returns ``(indices, centroid)``. Fewer than ``min_members`` survivors
    yields ``([], None)``: the two voices could not be told apart.
    """
    current = [(i, list(vector)) for i, vector in enumerate(vectors) if vector]
    if len(current) < min_members:
        return [], None
    for _ in range(8):
        centroid = _mean_unit([vector for _, vector in current])
        if centroid is None:
            return [], None
        kept = [(i, vector) for i, vector in current if _cosine(vector, centroid) >= min_cosine]
        if len(kept) < min_members:
            return [], None
        if [i for i, _ in kept] == [i for i, _ in current]:
            return [i for i, _ in kept], centroid
        current = kept
    centroid = _mean_unit([vector for _, vector in current])
    if centroid is None:
        return [], None
    return [i for i, _ in current], centroid


def _closest(frames, t) -> int:
    # Frame t is the window start; the center is half a window later.
    target = t - WIN / 2.0
    best = 0
    best_d = abs(frames[0]["t"] - target)
    for i in range(1, len(frames)):
        dist = abs(frames[i]["t"] - target)
        if dist < best_d:
            best = i
            best_d = dist
        elif frames[i]["t"] > target and dist > best_d:
            break
    return best


def tts_runs(frames, t_from, t_to):
    """Runs of the read voice. A dip shorter than a second does not split one."""
    runs = []
    i = 0
    n = len(frames)
    while i < n:
        frame = frames[i]
        if frame["t"] < t_from:
            i += 1
            continue
        if frame["t"] >= t_to:
            break
        if (not frame["speech"]) or frame["cosine"] < TTS_COSINE:
            i += 1
            continue
        last_tts = i
        first_host = None
        host_time = 0.0
        closed_host = None
        j = i + 1
        while j < n and frames[j]["t"] < t_to:
            nxt = frames[j]
            if not nxt["speech"]:
                j += 1
                continue
            if nxt["cosine"] >= TTS_COSINE:
                last_tts = j
                first_host = None
                host_time = 0.0
                j += 1
                continue
            if first_host is None:
                first_host = j
            host_time += HOP
            if host_time + 1e-6 >= HOST_END:
                closed_host = first_host
                break
            j += 1
        start_t = frames[i]["t"]
        end_t = frames[last_tts]["t"] + HOP
        runs.append({
            "start": start_t,
            "end": end_t,
            "duration": end_t - start_t,
            "first_host": frames[closed_host]["t"] if closed_host is not None else None,
        })
        i = j + 1 if j > i else i + 1
    return runs


def _mode_at(frames, index) -> str:
    frame = frames[index]
    cos = frame["cosine"]
    speech = frame["speech"]
    if speech and cos >= TTS_COSINE:
        return "tts"
    if speech and cos < SELF_COSINE:
        return "self"
    earlier = _closest(frames, frame["t"] + WIN / 2.0 - 1.0)
    prev = frames[earlier]
    if earlier != index and prev["speech"] and prev["cosine"] >= TTS_COSINE:
        return "tts"
    if earlier != index and prev["speech"] and prev["cosine"] < SELF_COSINE:
        return "self"
    return "uncertain"


def _row(onset, cosine, mode, reason, clip_start=None, reply_start=None, fence=None):
    return {
        "onset": onset["start"],
        "dollars": onset.get("dollars"),
        "cosine": round(cosine, 3) if cosine is not None else None,
        "mode": mode,
        "clip_start": clip_start,
        "reply_start": reply_start,
        "fence": fence,
        "reason": reason,
    }


def _fence_after(runs, amounts, onset, reply_start):
    for run in runs:
        if run["start"] <= reply_start + 0.2:
            continue
        if run["duration"] < FENCE_MIN_RUN:
            continue
        if run["start"] - reply_start > ISOLATED_GAP:
            return None
        for amount in amounts:
            if abs(amount["start"] - onset) < 2.0:
                continue
            if run["start"] - FENCE_BEFORE <= amount["start"] <= run["start"] + FENCE_AFTER:
                return run["start"]
    return None


def bound_exchange(frames, onset, amounts):
    """Where one donation sits, given a similarity timeline.

    ``frames`` are ``{t, cosine, speech}`` on a ``HOP`` grid. ``cosine`` is
    already the similarity to the read voice.
    """
    if not frames:
        return _row(onset, None, "uncertain", "no-audio")
    index = _closest(frames, onset["start"])
    cosine = frames[index]["cosine"]
    mode = _mode_at(frames, index)
    if mode == "uncertain":
        return _row(onset, cosine, mode, "uncertain")
    if mode == "self":
        return _bound_self(frames, index, onset, amounts, cosine)
    return _bound_tts(frames, onset, amounts, cosine)


def _adjacent(amounts, onset_t):
    prev_a = None
    next_a = None
    for amount in amounts:
        if amount["start"] < onset_t - 0.5:
            prev_a = amount
        elif amount["start"] > onset_t + 0.5 and next_a is None:
            next_a = amount
    return prev_a, next_a


def _bound_tts(frames, onset, amounts, cosine):
    window_from = onset["start"] - READ_BACK
    window_to = onset["start"] + READ_AHEAD
    runs = tts_runs(frames, window_from, window_to)
    covering = [run for run in runs
                if run["start"] - HOP <= onset["start"] <= run["end"] + HOP]
    if not covering:
        return _row(onset, cosine, "tts", "no-handoff")
    run = min(covering, key=lambda item: abs(item["start"] - onset["start"]))
    prev_a, next_a = _adjacent(amounts, onset["start"])
    clip_start = run["start"]
    # Several donations read back to back stay one TTS run. Open this clip on
    # this donor's name, not on the first name in the stack.
    if prev_a and run["start"] - 0.5 <= prev_a["start"] <= run["end"] + 0.5:
        clip_start = max(clip_start, onset["start"] - NAME_LEAD, prev_a["start"] + 0.3)
        clip_start = min(clip_start, onset["start"])
    host = run["first_host"]
    # He never came in before the next donation started. There is no reply to keep.
    if next_a and (host is None or host > next_a["start"] - 1.0):
        return _row(onset, cosine, "tts", "stacked", clip_start=clip_start)
    if host is None:
        return _row(onset, cosine, "tts", "no-handoff", clip_start=clip_start)
    later = tts_runs(frames, host, host + ISOLATED_GAP + FENCE_AFTER)
    fence = _fence_after(later, amounts, onset["start"], host)
    return _row(onset, cosine, "tts", None,
                clip_start=clip_start, reply_start=host, fence=fence)


def _bound_self(frames, index, onset, amounts, cosine):
    """He read the amount himself. The next amount is the fence."""
    start_t = frames[index]["t"]
    limit = start_t - SELF_BACK
    i = index
    while i > 0 and frames[i - 1]["t"] >= limit:
        prev = frames[i - 1]
        if not prev["speech"] or prev["cosine"] >= TTS_COSINE:
            break
        i -= 1
    clip_start = frames[i]["t"]
    reply_start = clip_start
    fence = None
    for amount in amounts:
        if amount["start"] <= onset["start"] + 2.0:
            continue
        if amount["start"] - onset["start"] > ISOLATED_GAP:
            break
        fence = amount["start"]
        break
    return _row(onset, cosine, "self", None,
                clip_start=clip_start, reply_start=reply_start, fence=fence)


def _words_between(words, t0, t1):
    return [word for word in words if t0 - 0.05 <= word["s"] < t1]


def gate_exchange(bounds, words, min_seconds, max_seconds):
    """Drop a reply that cannot fill a clip without the next chat."""
    if bounds.get("reason"):
        return bounds
    clip_start = bounds["clip_start"]
    reply_start = bounds["reply_start"]
    fence = bounds["fence"]
    latest = clip_start + max_seconds
    if fence is not None:
        latest = min(latest, fence)
    if latest - clip_start < min_seconds - 0.05:
        return {**bounds, "reason": "short-window"}
    if fence is not None:
        host_secs = fence - reply_start
        host_words = _words_between(words, reply_start, fence)
        if host_secs < MIN_HOST_SECONDS and len(host_words) < MIN_HOST_WORDS:
            return {**bounds, "reason": "short-reply"}
    reply_words = _words_between(words, reply_start, latest)
    read_words = _words_between(words, clip_start, reply_start)
    if len(reply_words) < 8 and (fence is not None or len(reply_words) < MIN_HOST_WORDS):
        return {**bounds, "reason": "short-reply"}
    return {
        **bounds,
        "latest": latest,
        "read_words": read_words[:80],
        "reply_words": reply_words[:400],
    }


def _snap_start(t, words):
    candidates = [word for word in words if t - 0.3 <= word["s"] <= t + 1.0]
    if not candidates:
        return round(max(0.0, t), 3)
    word = min(candidates, key=lambda item: abs(item["s"] - t))
    prev = [item["e"] for item in words if item["e"] <= word["s"] + 1e-3]
    if prev:
        gap = max(0.0, word["s"] - max(prev))
        lead = min(0.35, gap / 2.0)
    else:
        lead = 0.35
    return round(max(0.0, word["s"] - lead, t - 0.45), 3)


def _snap_end(t, words, latest):
    cap = min(latest, t + 0.6)
    candidates = [word for word in words if t - 1.2 <= word["e"] <= cap]
    if not candidates:
        return round(min(t, latest), 3)
    word = min(candidates, key=lambda item: abs(item["e"] - t))
    nxt = [item["s"] for item in words if item["s"] >= word["e"] - 1e-3]
    if nxt:
        gap = max(0.0, min(nxt) - word["e"])
        tail = min(0.45, gap / 2.0)
    else:
        tail = 0.3
    return round(min(word["e"] + tail, latest), 3)


def _clip_from_verdict(candidate, verdict, words, min_seconds, max_seconds):
    if not verdict or not verdict.get("keep"):
        return {**_public_row(candidate), "reason": "thanks"}
    try:
        end = float(verdict.get("end") or 0)
        raw_score = verdict.get("score")
        score = 0 if raw_score is None else int(round(float(raw_score)))
    except (TypeError, ValueError):
        return {**_public_row(candidate), "reason": "thanks"}
    latest = candidate["latest"]
    reply_start = candidate["reply_start"]
    # A missing end is not permission to run out to the cap.
    if end < reply_start + 1.0:
        return {**_public_row(candidate), "reason": "short-answer"}
    end = min(end, latest)
    start = _snap_start(candidate["clip_start"], words)
    end = _snap_end(end, words, latest)
    if end <= start or end - start < min_seconds - 0.05:
        return {**_public_row(candidate), "reason": "short-answer"}
    if end - start > max_seconds:
        end = _snap_end(start + max_seconds, words, start + max_seconds)
    title = str(verdict.get("video_title_for_youtube_short") or "").strip()[:100]
    hook = str(verdict.get("viral_hook_text") or "").strip()
    hook = " ".join(hook.split()[:10])
    if not title:
        title = "Superchat reply"
    return {
        **_public_row(candidate),
        "reason": None,
        "keep": True,
        "score": max(0, min(100, score)),
        "start": start,
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "video_title_for_youtube_short": title,
        "viral_hook_text": hook,
        "video_description_for_tiktok": str(verdict.get("video_description_for_tiktok") or "")[:500],
        "video_description_for_instagram": str(verdict.get("video_description_for_instagram") or "")[:500],
        "why": str(verdict.get("why") or "")[:240],
    }


def _public_row(candidate):
    """The row that is safe to log: times and the decision, no transcript."""
    return {
        "onset": candidate.get("onset"),
        "dollars": candidate.get("dollars"),
        "cosine": candidate.get("cosine"),
        "mode": candidate.get("mode"),
        "clip_start": candidate.get("clip_start"),
        "reply_start": candidate.get("reply_start"),
        "fence": candidate.get("fence"),
        "reason": candidate.get("reason"),
    }


def _as_clip(row):
    return {
        "start": row["start"],
        "end": row["end"],
        "source_window_id": "superchat",
        "predicted_score": int(row["score"]),
        "video_description_for_tiktok": row.get("video_description_for_tiktok") or "",
        "video_description_for_instagram": row.get("video_description_for_instagram") or "",
        "video_title_for_youtube_short": row["video_title_for_youtube_short"],
        "viral_hook_text": row.get("viral_hook_text") or "",
        "why": row.get("why") or "",
        "superchat": True,
    }


def take_best(rows, top=TOP):
    kept = [row for row in rows if row.get("keep")]
    kept.sort(key=lambda row: (-row.get("score", 0), -row.get("duration", 0)))
    chosen = kept[:top]
    chosen_ids = {id(row) for row in chosen}
    for row in kept:
        if id(row) not in chosen_ids:
            row["keep"] = False
            row["reason"] = "rank"
    chosen.sort(key=lambda row: row["start"])
    return chosen


def _overlap_ratio(a0, a1, b0, b1) -> float:
    overlap = min(a1, b1) - max(a0, b0)
    if overlap <= 0:
        return 0.0
    shorter = min(a1 - a0, b1 - b0)
    return overlap / max(shorter, 1e-6)


def place_superchats(shorts, extras, max_seconds, ratio=0.5, earlier=2.0):
    """Append extras, or widen a viral clip that started late on the same answer.

    Returns ``(added, widened)``. An extra that overlaps a clip it does not
    meaningfully precede is skipped: that moment is already in the five.
    """
    added = 0
    widened = 0
    accepted = []
    ordered = sorted(extras, key=lambda clip: -float(clip.get("predicted_score") or 0))
    for extra in ordered:
        es, ee = float(extra["start"]), float(extra["end"])
        widened_here = False
        blocked = False
        for clip in list(shorts) + accepted:
            cs, ce = float(clip["start"]), float(clip["end"])
            if _overlap_ratio(es, ee, cs, ce) < ratio:
                continue
            if es <= cs - earlier and clip in shorts and not clip.get("superchat"):
                new_start = es
                new_end = max(ee, ce)
                if new_end - new_start > max_seconds:
                    new_end = ee
                clip["start"] = round(new_start, 3)
                clip["end"] = round(new_end, 3)
                clip["superchat"] = True
                for key in ("video_title_for_youtube_short", "viral_hook_text",
                            "video_description_for_tiktok", "video_description_for_instagram",
                            "why"):
                    if extra.get(key):
                        clip[key] = extra[key]
                if extra.get("predicted_score") is not None:
                    clip["predicted_score"] = extra["predicted_score"]
                widened += 1
                widened_here = True
            else:
                blocked = True
            break
        if widened_here or blocked:
            continue
        accepted.append(extra)
        added += 1
    accepted.sort(key=lambda clip: float(clip["start"]))
    shorts.extend(accepted)
    return added, widened


def decide(words, amounts, frames, judge, min_seconds, max_seconds, top=TOP):
    """Bound every amount, drop the short ones, and let ``judge`` rank the rest.

    ``judge(candidates)`` returns verdict dicts keyed by ``index``. A missing
    or failed verdict drops that exchange.
    """
    rows = []
    open_ones = []
    claimed_until = -1.0
    for amount in amounts:
        if amount["start"] < claimed_until:
            continue
        bounds = bound_exchange(frames, amount, amounts)
        gated = gate_exchange(bounds, words, min_seconds, max_seconds)
        if gated.get("reason"):
            rows.append(_public_row(gated))
            continue
        gated["index"] = len(open_ones)
        open_ones.append(gated)
        # The next donation's amount is past the fence; claim only the read
        # itself so a second number inside the message is not its own clip.
        claimed_until = gated["reply_start"]
    verdicts = {}
    if open_ones and judge is not None:
        print(f"   Superchat judging {len(open_ones)} reply(s).", flush=True)
        try:
            for verdict in judge(open_ones):
                if verdict is None or "index" not in verdict:
                    continue
                verdicts[int(verdict["index"])] = verdict
        except Exception as exc:
            for candidate in open_ones:
                rows.append({**_public_row(candidate), "reason": "judge-failed"})
            rows.append({"reason": "judge-failed", "error": str(exc)[:200]})
            return {"rows": rows, "clips": [], "ranked_out": []}
    finished = []
    for candidate in open_ones:
        verdict = verdicts.get(candidate["index"])
        if verdict is None:
            rows.append({**_public_row(candidate), "reason": "judge-failed"})
            continue
        done = _clip_from_verdict(candidate, verdict, words, min_seconds, max_seconds)
        finished.append(done)
        rows.append({key: done.get(key) for key in (
            "onset", "dollars", "cosine", "mode", "clip_start", "reply_start",
            "fence", "reason", "keep", "score", "start", "end", "duration",
            "video_title_for_youtube_short")})
    chosen = take_best(finished, top=top)
    chosen_ids = {id(row) for row in chosen}
    ranked_out = [row for row in finished if row.get("reason") == "rank"]
    # take_best mutates reason on the ranked-out rows; refresh those log rows.
    by_onset = {}
    for row in rows:
        if row.get("onset") is not None and row.get("keep"):
            by_onset[row["onset"]] = row
    for row in ranked_out:
        logged = by_onset.get(row.get("onset"))
        if logged is not None:
            logged["reason"] = "rank"
            logged["keep"] = False
    clips = [_as_clip(row) for row in chosen if id(row) in chosen_ids or row in chosen]
    ranked_clips = [_as_clip(row) for row in ranked_out]
    return {"rows": rows, "clips": clips, "ranked_out": ranked_clips}


class _Verdict(BaseModel):
    index: int
    keep: bool
    score: float = 0
    end: float = 0
    video_title_for_youtube_short: str = ""
    viral_hook_text: str = ""
    video_description_for_tiktok: str = ""
    video_description_for_instagram: str = ""
    why: str = ""


class _Batch(BaseModel):
    clips: list[_Verdict]


def _stamp(words) -> str:
    return " ".join(f"{word['w'].strip()}@{word['e']:.2f}" for word in words)


def _judge_prompt(candidates) -> str:
    blocks = []
    for candidate in candidates:
        blocks.append(
            f"INDEX {candidate['index']}\n"
            f"clip_start={candidate['clip_start']:.2f} reply_start={candidate['reply_start']:.2f} "
            f"latest_end={candidate['latest']:.2f}\n"
            f"READ: {_stamp(candidate['read_words'])}\n"
            f"REPLY: {_stamp(candidate['reply_words'])}"
        )
    return (
        "Each block is one superchat. A different voice read the donation "
        "(READ). The host then replied (REPLY). Whisper garbles donor names. "
        "Judge the reply, not the name.\n"
        "keep=true only when the host answers, argues, jokes, or tells something "
        "about that message. keep=false for a thanks-only reply, a read with no "
        "message, and a reply that is just him going back to the episode. "
        "A thank-you that leads straight into the answer still counts. "
        "Thanks followed by a different subject does not: keep=false, and do not "
        "treat the rest of the show as the reply. "
        "A rude, blunt, or harsh opinion is still an answer. Do not drop it for tone.\n"
        "end is the end timestamp of the LAST word of the answer. It must be one "
        "of the @ times in REPLY, greater than reply_start and at most latest_end. "
        "Stop before he drifts off the message and before the next donation. "
        "Do not pad.\n"
        "video_title_for_youtube_short (max 100 chars) and viral_hook_text "
        "(max 10 words) describe what HE says, not the donor name and not the "
        "dollar amount. Descriptions are one or two sentences plus a few hashtags. "
        "score is an integer 0-100. Use the whole range, do not give every answer "
        "the same number. 90-100 is a complete story, argument, or joke that "
        "stands alone. 70-85 is a clear specific answer. 40-60 is mild. "
        "0 with keep=false is thanks-only or a subject change. "
        "why is one short sentence.\n"
        "Return JSON {\"clips\": [one object per index]}.\n\n"
        + "\n\n".join(blocks)
    )


def judge_with_llm(candidates, batch_size=1):
    """Ask the configured local model, one reply at a time.

    json_object mode, not json_schema: a batch against the schema came back
    with every score at 0 or with a broken string. One reply returns a clean
    object. A failed call drops only that reply.
    """
    import llm_backend
    import gemini_worker

    del batch_size  # one reply per call; the argument stays so tests can pass it
    verdicts = []
    url = f"{llm_backend.base_url()}/chat/completions"
    model = llm_backend.model_name()
    headers = llm_backend._headers()
    with llm_backend._client() as client:
        for cand in candidates:
            body = {
                "model": model,
                "messages": [
                    {"role": "system",
                     "content": "You answer with a single JSON object and nothing else."},
                    {"role": "user", "content": _judge_prompt([cand])},
                ],
                "temperature": 0.2,
                "stream": False,
                "max_tokens": 700,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object"},
            }
            try:
                resp = client.post(url, json=body, headers=headers)
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:180]}")
                data = resp.json()
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                text = msg.get("content") or ""
                if isinstance(text, list):
                    text = "".join(
                        part.get("text", "") for part in text if isinstance(part, dict))
                parsed = gemini_worker._parse_json_response_text(text)
                clips = parsed.get("clips") or []
                if len(clips) == 1:
                    clips[0]["index"] = cand["index"]
                validated = _Batch.model_validate(parsed).model_dump()
            except Exception as exc:
                print(f"   Superchat judge {cand.get('onset', 0):.0f} failed ({str(exc)[:180]}).")
                continue
            verdicts.extend(validated.get("clips") or [])
            if len(verdicts) % 5 == 0:
                print(f"   Superchat judged {len(verdicts)}/{len(candidates)}", flush=True)
    return verdicts


def _silence_threshold(rms):
    import numpy as np

    if len(rms) == 0:
        return 0.01
    loud = rms[rms >= np.percentile(rms, 50)]
    med = float(np.median(loud)) if len(loud) else 0.02
    return max(0.006, med * 0.25)


def load_audio(path, sr=16000):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:300]
        raise RuntimeError(f"audio decode failed: {err}")
    import numpy as np
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def embed_timeline(samples, sr=16000):
    """One L2-normalized 32-dim log-mel per ``HOP``, over a ``WIN`` window."""
    import numpy as np

    n_fft = 512
    stft_hop = 160
    n_mels = 32
    win_n = int(WIN * sr)
    hop_n = int(HOP * sr)
    window = np.hanning(n_fft).astype(np.float32)
    bank = _mel_bank(sr, n_fft, n_mels)
    n = len(samples)
    if n < win_n:
        empty = np.zeros((0, n_mels), np.float32)
        return np.zeros(0), empty, np.zeros(0)
    starts = np.arange(0, n - win_n + 1, hop_n)
    embs = np.empty((len(starts), n_mels), np.float32)
    rms = np.empty(len(starts), np.float32)
    stride = samples.strides[0]
    total = len(starts)
    for i, sample_at in enumerate(starts):
        chunk = samples[sample_at:sample_at + win_n]
        rms[i] = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
        n_frames = 1 + (win_n - n_fft) // stft_hop
        framed = np.lib.stride_tricks.as_strided(
            chunk, shape=(n_frames, n_fft),
            strides=(stride * stft_hop, stride), writeable=False)
        spec = np.fft.rfft(framed * window, axis=1)
        power = spec.real.astype(np.float32) ** 2 + spec.imag.astype(np.float32) ** 2
        mel = np.log(power @ bank.T + 1e-6)
        vec = mel.mean(axis=0)
        vec -= vec.mean()
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        embs[i] = vec
        if total > 2000 and i and i % 2000 == 0:
            print(f"   Superchat voice pass {i}/{total}", flush=True)
    return starts.astype(np.float64) / sr, embs, rms


def _mel_bank(sr, n_fft, n_mels, fmin=80.0):
    import numpy as np

    n_bins = n_fft // 2 + 1
    fmax = sr / 2.0

    def hz_mel(hz):
        return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)

    def mel_hz(mel):
        return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)

    points = np.linspace(hz_mel(fmin), hz_mel(fmax), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel_hz(points) / sr).astype(int)
    bank = np.zeros((n_mels, n_bins), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = int(bins[i]), int(bins[i + 1]), int(bins[i + 2])
        if center <= left:
            center = left + 1
        if right <= center:
            right = center + 1
        for j in range(left, min(center, n_bins)):
            if j >= 0:
                bank[i, j] = (j - left) / float(center - left)
        for j in range(center, min(right, n_bins)):
            if j >= 0:
                bank[i, j] = (right - j) / float(right - center)
    return bank


def _onset_vectors(times, embs, amounts):
    import numpy as np

    centers = times + WIN / 2.0
    vectors = []
    for amount in amounts:
        mask = (centers >= amount["start"] - 0.75) & (centers <= amount["start"] + 0.75)
        if int(mask.sum()) < 1:
            vectors.append(None)
            continue
        vec = embs[mask].mean(axis=0)
        norm = float(np.linalg.norm(vec))
        vectors.append((vec / norm).tolist() if norm > 0 else None)
    return vectors


def _frames_from_audio(times, embs, rms, centroid, silence):
    import numpy as np

    centroid = np.asarray(centroid, dtype=np.float32)
    cosine = embs @ centroid
    frames = []
    for i in range(len(times)):
        frames.append({
            "t": round(float(times[i]), 3),
            "cosine": float(cosine[i]),
            "speech": bool(rms[i] >= silence),
        })
    return frames


def _log_lines(result, cluster_size, onset_count):
    lines = [f"   Superchat amounts={onset_count} read-voice cluster={cluster_size}"]
    drops = {}
    for row in result["rows"]:
        if row.get("error"):
            lines.append(f"   Superchat judge failed ({row['error']})")
            continue
        reason = row.get("reason") or "keep"
        if reason not in ("keep", "rank"):
            drops[reason] = drops.get(reason, 0) + 1
            continue
        bits = [f"{row.get('onset', 0):.1f}", reason]
        if row.get("start") is not None:
            bits.append(f"{row['start']:.1f}-{row['end']:.1f}")
        if row.get("duration"):
            bits.append(f"{row['duration']:.0f}s")
        if row.get("score") is not None:
            bits.append(f"score {row['score']}")
        title = row.get("video_title_for_youtube_short")
        if title:
            bits.append(title)
        lines.append("   Superchat " + " | ".join(bits))
    if drops:
        summary = ", ".join(f"{name} {count}" for name, count in sorted(drops.items()))
        lines.append(f"   Superchat dropped {sum(drops.values())} ({summary}).")
    return lines


def collect(transcript, video_path, min_seconds, max_seconds, top=TOP,
            cache_path=None, judge=None):
    """Run the pass over one episode. ``judge`` defaults to the local LLM."""
    import numpy as np

    words = flatten_words(transcript)
    amounts = find_amounts(words)
    times, embs, rms = _load_or_embed(video_path, cache_path)
    vectors = _onset_vectors(times, embs, amounts)
    kept, centroid = cluster_members(vectors)
    if centroid is None:
        return {
            "rows": [],
            "clips": [],
            "ranked_out": [],
            "log": [f"   Superchat skipped: {len(kept) or 0} of {len(amounts)} "
                    f"amounts agreed on a read voice (need {MIN_CLUSTER})."],
        }
    silence = _silence_threshold(rms)
    frames = _frames_from_audio(times, embs, rms, centroid, silence)
    # Stamp each onset with the cosine of the frame on the amount itself.
    for amount, vector in zip(amounts, vectors):
        if vector is None:
            continue
        amount_cos = _cosine(vector, centroid)
        amount["cosine"] = amount_cos
    # The timeline cosine is what bound_exchange reads. The member cosine is
    # only a diagnostic; overwrite nothing on the frames.
    if judge is None:
        judge = judge_with_llm
    result = decide(words, amounts, frames, judge, min_seconds, max_seconds, top=top)
    speech_fraction = float(np.mean([1.0 if frame["speech"] else 0.0 for frame in frames])) if frames else 0.0
    result["log"] = _log_lines(result, len(kept), len(amounts))
    result["log"].insert(1, f"   Superchat silence_rms={silence:.4f} speech={speech_fraction:.2f}")
    result["cluster_size"] = len(kept)
    return result


def _load_or_embed(video_path, cache_path):
    import numpy as np

    if cache_path and os.path.isfile(cache_path):
        cached = np.load(cache_path)
        if str(cached.get("version", "")) == EMBED_VERSION:
            return cached["times"], cached["embs"], cached["rms"]
    samples = load_audio(video_path)
    times, embs, rms = embed_timeline(samples, 16000)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        np.savez(cache_path, version=np.array(EMBED_VERSION), times=times, embs=embs, rms=rms)
    return times, embs, rms


def append_to_job(shorts, transcript, video_path, video_duration, top=TOP):
    """Add up to ``top`` superchat clips. Fail-open: the caller still has the five.

    Returns how many clips were appended (a widened viral clip counts as zero).
    """
    del video_duration  # the word timings and the band carry the limits
    from clip_selection import clip_duration_bounds

    lo, hi = clip_duration_bounds()
    try:
        result = collect(transcript, video_path, min_seconds=lo, max_seconds=hi, top=top)
    except Exception as exc:
        print(f"   Superchat pass skipped ({str(exc)[:200]}).")
        return 0
    for line in result.get("log") or []:
        print(line)
    added, widened = place_superchats(shorts, result.get("clips") or [], max_seconds=hi)
    print(f"   Superchat pass added {added}, widened {widened}.")
    return added


def cut_preview(src, dst, start, end):
    """A small accurate preview. Not the vertical render."""
    lead = 1.0 if start >= 1.0 else 0.0
    duration = max(0.5, end - start)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-v", "error", "-threads", "2",
        "-ss", f"{max(0.0, start - lead):.3f}", "-i", src,
        "-ss", f"{lead:.3f}", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart", dst,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:300]
        raise RuntimeError(err)


def _cli():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Try the superchat pass on one episode.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--min-seconds", type=float, default=15.0)
    parser.add_argument("--top", type=int, default=TOP)
    parser.add_argument("--cut", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    with open(args.metadata) as handle:
        metadata = json.load(handle)
    transcript = metadata.get("transcript") or metadata
    os.makedirs(args.out, exist_ok=True)
    cache = os.path.join(args.out, "embed_v1.npz")
    result = collect(
        transcript, args.video, args.min_seconds, args.max_seconds,
        top=args.top, cache_path=cache)
    for line in result.get("log") or []:
        print(line, flush=True)
    report = {
        "cluster_size": result.get("cluster_size"),
        "clips": result.get("clips"),
        "ranked_out": result.get("ranked_out"),
        "rows": result.get("rows"),
    }
    with open(os.path.join(args.out, "report.json"), "w") as handle:
        json.dump(report, handle, indent=2)
    if args.cut:
        for rank, clip in enumerate(result.get("clips") or [], start=1):
            name = f"{rank:02d}_{clip['start']:.0f}.mp4"
            cut_preview(args.video, os.path.join(args.out, name), clip["start"], clip["end"])
            print(f"   preview {name}", flush=True)
    print(f"   wrote {args.out}/report.json", flush=True)


if __name__ == "__main__":
    _cli()
