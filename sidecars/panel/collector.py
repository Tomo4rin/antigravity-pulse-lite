#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Antigravity 本机 language_server 只读指标采集器（纯 Python 标准库）。"""

import sys

sys.dont_write_bytecode = True

import json
import os
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

SERVICE = "/exa.language_server_pb.LanguageServerService/"

MODEL_ALIASES = {
    "model_placeholder_m318": "Gemini 3.8 Flash (High)",
    "model_placeholder_m319": "Gemini 3.8 Flash (Medium)",
    "model_placeholder_m320": "Gemini 3.8 Flash (Low)",
    "model_placeholder_m35": "Claude Sonnet 4.6 (Thinking)",
    "model_placeholder_m26": "Claude Opus 4.6 (Thinking)",
    "model_openai_gpt_oss_120b_medium": "GPT-OSS 120B (Medium)",
}


def parse_seconds(value):
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    if isinstance(value, str):
        m = re.match(r"^(\d+(?:\.\d+)?)s$", value.strip())
        if m:
            return float(m.group(1))
    if isinstance(value, dict) and ("seconds" in value or "nanos" in value):
        try:
            sec = int(value.get("seconds", 0))
            nanos = int(value.get("nanos", 0))
            if sec >= 0 and 0 <= nanos < 1_000_000_000:
                return sec + nanos / 1e9
        except (TypeError, ValueError):
            return None
    return None


def parse_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def parse_iso_ms(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return int(datetime.fromisoformat(s).timestamp() * 1000)
    except Exception:
        return None


def format_model_name(raw):
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name:
        return None
    return MODEL_ALIASES.get(name.lower(), name)


def union_seconds(intervals):
    valid = sorted((a, b) for a, b in intervals if a is not None and b is not None and b >= a)
    if not valid:
        return 0.0
    total = 0
    cur_a, cur_b = valid[0]
    for a, b in valid[1:]:
        if a <= cur_b:
            cur_b = max(cur_b, b)
        else:
            total += cur_b - cur_a
            cur_a, cur_b = a, b
    total += cur_b - cur_a
    return total / 1000.0


def rpc_post(port, csrf, method, body=None, timeout=6.0):
    payload = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{SERVICE}{method}",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            "x-codeium-csrf-token": csrf,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def parse_env_endpoint():
    addr = (os.environ.get("ANTIGRAVITY_LS_ADDRESS") or "").strip()
    csrf = (os.environ.get("ANTIGRAVITY_CSRF_TOKEN") or "").strip()
    if not addr or not csrf:
        return None
    if "://" not in addr:
        addr = "http://" + addr
    try:
        parsed = urlparse(addr)
        if parsed.hostname in ("127.0.0.1", "localhost", "::1") and parsed.port:
            return {"port": parsed.port, "csrf": csrf, "source": "env"}
    except Exception:
        return None
    return None


def discover_windows_server():
    """在 Windows 上发现 standalone language_server 的本地 HTTP 端口与 CSRF Token。"""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'language_server%'\" | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=6,
        ).strip()
    except Exception:
        return None
    if not out:
        return None
    try:
        rows = json.loads(out)
    except Exception:
        return None
    if isinstance(rows, dict):
        rows = [rows]

    candidates = []
    for row in rows:
        cmd = str(row.get("CommandLine") or "")
        pid = row.get("ProcessId")
        if not pid or "--standalone" not in cmd:
            continue
        m = re.search(r'--csrf_token(?:=|\s+)"?([^\s"]+)', cmd)
        if m:
            candidates.append((int(pid), m.group(1)))

    if not candidates:
        return None

    try:
        net = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )
    except Exception:
        return None

    pid_ports = {}
    for line in net.splitlines():
        cols = line.split()
        if len(cols) >= 5 and cols[0].upper() == "TCP" and cols[3].upper() in ("LISTENING", "LISTEN", "侦听", "监听"):
            addr, pid_s = cols[1], cols[4]
            if pid_s.isdigit() and (addr.startswith("127.0.0.1:") or addr.startswith("[::1]:") or addr.startswith("0.0.0.0:")):
                port_s = addr.rsplit(":", 1)[-1]
                if port_s.isdigit():
                    pid_ports.setdefault(int(pid_s), []).append(int(port_s))

    for pid, csrf in candidates:
        for port in pid_ports.get(pid, []):
            try:
                rpc_post(port, csrf, "GetUserStatus", {}, timeout=1.5)
                return {"port": port, "csrf": csrf, "pid": pid, "source": "process"}
            except Exception:
                continue
    return None


def parse_quota(response, now_ms):
    root = response.get("response") if isinstance(response.get("response"), dict) else response
    if not isinstance(root, dict):
        return []
    groups = [g for g in (root.get("groups") or []) if isinstance(g, dict)]
    if not groups and isinstance(root.get("buckets"), list):
        families = {}
        for idx, b in enumerate(root["buckets"]):
            if not isinstance(b, dict):
                continue
            bid = str(b.get("bucketId") or "")
            fam = re.sub(r"-(5h|weekly)$", "", bid) or f"group-{idx}"
            families.setdefault(fam, {"displayName": str(b.get("displayName") or fam), "buckets": []})
            families[fam]["buckets"].append(b)
        groups = list(families.values())

    def cadence(bucket):
        if "window" in bucket and bucket["window"] in ("5h", "weekly"):
            return bucket["window"]
        m = re.search(r"-(5h|weekly)$", str(bucket.get("bucketId") or ""))
        return m.group(1) if m else None

    def get_fraction(bucket):
        val = bucket.get("remainingFraction")
        if val is None and isinstance(bucket.get("remaining"), dict):
            val = bucket["remaining"].get("remainingFraction")
        try:
            f = float(val)
            if 0.0 <= f <= 1.0:
                return f
        except (TypeError, ValueError):
            pass
        return None

    result = []
    for idx, grp in enumerate(groups):
        buckets = [b for b in (grp.get("buckets") or []) if isinstance(b, dict)]
        gid = None
        for b in buckets:
            fam = re.sub(r"-(5h|weekly)$", "", str(b.get("bucketId") or ""))
            if fam:
                gid = fam
                break
        windows = {}
        for win in ("5h", "weekly"):
            b = next((x for x in buckets if cadence(x) == win), None)
            if not b:
                windows[win] = {"available": False}
                continue
            rem = get_fraction(b)
            reset_ms = parse_iso_ms(b.get("resetTime"))
            reset_at = (
                datetime.fromtimestamp(reset_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                if reset_ms is not None
                else None
            )
            windows[win] = {
                "available": True,
                "remaining": rem,
                "resetAt": reset_at,
                "resetMs": reset_ms,
                "disabled": b.get("disabled") is True,
                "forecast": compute_forecast(rem, reset_ms, win, now_ms),
            }
        result.append(
            {
                "id": gid or f"group-{idx}",
                "name": str(grp.get("displayName") or f"额度组 {idx + 1}"),
                "windows": windows,
            }
        )
    return result


def compute_forecast(remaining, reset_ms, window_kind, now_ms):
    """按当前周期已过时间与已消耗比例估算重置前余额或预计耗尽时间。"""
    if remaining is None or reset_ms is None:
        return None
    window_ms = 5 * 3600 * 1000 if window_kind == "5h" else 7 * 24 * 3600 * 1000
    time_left_ms = reset_ms - now_ms
    if time_left_ms <= 0 or time_left_ms > window_ms:
        return None
    elapsed_ms = window_ms - time_left_ms
    used = max(0.0, min(1.0, 1.0 - remaining))
    if elapsed_ms < window_ms * 0.03 or used < 0.01:
        return {"warmingUp": True, "used": used, "willExhaust": False, "projectedRemaining": remaining}

    burn_rate_per_ms = used / elapsed_ms
    projected_more = burn_rate_per_ms * time_left_ms
    projected_remaining = max(0.0, remaining - projected_more)
    if burn_rate_per_ms > 0 and remaining / burn_rate_per_ms < time_left_ms:
        exhaust_in_ms = int(remaining / burn_rate_per_ms)
        return {
            "warmingUp": False,
            "willExhaust": True,
            "exhaustInMs": exhaust_in_ms,
            "earlyByMs": int(time_left_ms - exhaust_in_ms),
            "projectedRemaining": 0.0,
        }
    return {
        "warmingUp": False,
        "willExhaust": False,
        "projectedRemaining": projected_remaining,
    }


def parse_trajectory_metrics(generators, steps=None, step_count=None, cascade_id=None):
    steps = steps or []
    seen_ids = set()
    samples = []

    uncached_in = 0
    cache_read = 0
    cache_write = 0
    output_total = 0
    response_out = 0
    thinking_out = 0

    ttft_sum = 0.0
    ttft_cnt = 0
    model_sec = 0.0
    last_chat = None

    for idx, gen in enumerate(generators or []):
        chat = gen.get("chatModel") if isinstance(gen, dict) else None
        if not isinstance(chat, dict):
            continue
        last_chat = chat
        usage = chat.get("usage")
        if not isinstance(usage, dict):
            continue

        rid = usage.get("responseId") or usage.get("messageId") or f"idx:{idx}"
        if rid in seen_ids:
            continue
        seen_ids.add(rid)

        in_tok = parse_int(usage.get("inputTokens"))
        cr_tok = parse_int(usage.get("cacheReadTokens")) or 0
        cw_tok = parse_int(usage.get("cacheWriteTokens")) or 0
        out_tok = parse_int(usage.get("outputTokens"))
        vis_tok = parse_int(usage.get("responseOutputTokens"))
        thk_tok = parse_int(usage.get("thinkingOutputTokens"))

        if in_tok is not None:
            uncached_in += in_tok
            cache_read += cr_tok
            cache_write += cw_tok
        if out_tok is not None:
            output_total += out_tok
        if vis_tok is not None:
            response_out += vis_tok
        if thk_tok is not None:
            thinking_out += thk_tok

        resp_tokens = vis_tok if vis_tok is not None else (
            max(0, out_tok - thk_tok) if (out_tok is not None and thk_tok is not None) else out_tok
        )
        dur = parse_seconds(chat.get("streamingDuration"))
        ttft = parse_seconds(chat.get("timeToFirstToken"))
        if ttft is not None:
            ttft_sum += ttft
            ttft_cnt += 1
        model_sec += (ttft or 0.0) + (dur or 0.0)

        tps = (resp_tokens / dur) if (resp_tokens is not None and dur and dur > 0) else None
        samples.append(
            {
                "tokens": resp_tokens,
                "duration": dur,
                "ttft": ttft,
                "tps": tps,
                "model": format_model_name(
                    chat.get("modelDisplayName") or chat.get("responseModel") or str(chat.get("model") or usage.get("model") or "")
                ),
            }
        )

    # 稳健异常值剔除：过滤极端短流式毛刺（MAD 离群基线 + 短流式高 TTFT 异常）
    long_rates = [s["tps"] for s in samples if s["tps"] is not None and (s["duration"] or 0) >= 1.0]
    med = statistics.median(long_rates) if len(long_rates) >= 5 else None
    mad = statistics.median([abs(x - med) for x in long_rates]) if med is not None else None
    upper_bound = max(med * 4.0, med + mad * 6.0) if (med is not None and mad is not None) else None
    accepted = []
    for s in samples:
        if s["tps"] is None:
            continue
        dur = s["duration"] or 0.0
        ttft = s["ttft"] or 0.0
        if dur < 1.0 and ttft >= 2.0 and ttft >= dur * 20.0:
            continue
        if upper_bound is not None and dur < 1.0 and s["tps"] > upper_bound:
            continue
        accepted.append(s)

    stream_sec = sum(s["duration"] for s in accepted)
    sampled_tok = sum(s["tokens"] for s in accepted)
    avg_tps = (sampled_tok / stream_sec) if stream_sec > 0 else None
    peak_tps = max((s["tps"] for s in accepted), default=None)
    latest_tps = accepted[-1]["tps"] if accepted else None
    recent_tps = [round(s["tps"], 1) for s in accepted[-16:]]

    tool_intervals = []
    for st in steps:
        if not isinstance(st, dict):
            continue
        stype = str(st.get("type") or "")
        meta = st.get("metadata") if isinstance(st.get("metadata"), dict) else {}
        if meta.get("toolCall") or re.search(r"COMMAND|READ|WRITE|EDIT|TOOL|MCP|SEARCH|BROWSE|VIEW|GREP", stype, re.I):
            a = parse_iso_ms(meta.get("startedAt") or meta.get("createdAt"))
            b = parse_iso_ms(meta.get("completedAt"))
            if a is not None and b is not None:
                tool_intervals.append((a, b))
    tool_sec = union_seconds(tool_intervals)

    total_input = uncached_in + cache_read + cache_write
    total_tokens = total_input + output_total
    hit_rate = (cache_read / total_input) if total_input > 0 else None

    ctx_info = None
    if isinstance(last_chat, dict):
        start_meta = last_chat.get("chatStartMetadata") if isinstance(last_chat.get("chatStartMetadata"), dict) else {}
        ctx_raw = start_meta.get("contextWindowMetadata") if isinstance(start_meta.get("contextWindowMetadata"), dict) else None
        if ctx_raw:
            used_tok = parse_int(ctx_raw.get("estimatedTokensUsed"))
            max_tok = parse_int(ctx_raw.get("maxContextTokens"))
            if used_tok is not None:
                ctx_info = {
                    "usedTokens": used_tok,
                    "maxTokens": max_tok if (max_tok and max_tok > 0) else None,
                    "usedFraction": (used_tok / max_tok) if (max_tok and max_tok > 0) else None,
                    "model": format_model_name(
                        last_chat.get("modelDisplayName") or last_chat.get("responseModel") or str(last_chat.get("model") or "")
                    ),
                }

    latest_model = (ctx_info or {}).get("model") or (samples[-1]["model"] if samples else None)
    return {
        "conversationId": cascade_id,
        "steps": step_count if step_count is not None else len(steps),
        "requests": len(seen_ids),
        "measuredRequests": len(accepted),
        "model": latest_model,
        "tps": round(avg_tps, 1) if avg_tps is not None else None,
        "latestTps": round(latest_tps, 1) if latest_tps is not None else None,
        "peakTps": round(peak_tps, 1) if peak_tps is not None else None,
        "recentTps": recent_tps,
        "ttftSeconds": round(ttft_sum / ttft_cnt, 2) if ttft_cnt else None,
        "modelSeconds": round(model_sec, 1),
        "toolSeconds": round(tool_sec, 1),
        "cache": {
            "totalTokens": total_tokens,
            "inputTokens": total_input,
            "cachedTokens": cache_read,
            "uncachedTokens": uncached_in,
            "cacheWriteTokens": cache_write,
            "outputTokens": output_total,
            "responseOutputTokens": response_out,
            "thinkingOutputTokens": thinking_out,
            "hitRate": hit_rate,
        },
        "context": ctx_info,
    }


class PulseCollector:
    def __init__(self):
        self.server = None
        self.discovered_at = 0.0
        self.quota_cache = []
        self.quota_at = 0.0
        self.last_error = None

    def ensure_server(self, force=False):
        now = time.monotonic()
        if not force and self.server and now - self.discovered_at < 20.0:
            return self.server
        env_ep = parse_env_endpoint()
        if env_ep:
            try:
                rpc_post(env_ep["port"], env_ep["csrf"], "GetUserStatus", {}, timeout=1.5)
                self.server = env_ep
                self.discovered_at = now
                return self.server
            except Exception:
                pass
        found = discover_windows_server()
        if found:
            self.server = found
            self.discovered_at = now
            return self.server
        self.server = None
        return None

    def snapshot(self, force_quota=False, conversation_id=None):
        now_ms = int(time.time() * 1000)
        srv = self.ensure_server(force=force_quota)
        if not srv:
            return {
                "connection": "offline",
                "serverTimeMs": now_ms,
                "error": "未检测到运行中的 Antigravity 本地服务",
                "groups": self.quota_cache,
                "conversations": [],
                "speed": None,
            }
        try:
            # 1. 额度（每 60 秒或强制刷新）
            if force_quota or not self.quota_cache or (time.monotonic() - self.quota_at >= 60.0):
                q_resp = rpc_post(
                    srv["port"],
                    srv["csrf"],
                    "RetrieveUserQuotaSummary",
                    {"forceRefresh": True} if force_quota else {},
                    timeout=5.0,
                )
                self.quota_cache = parse_quota(q_resp, now_ms)
                self.quota_at = time.monotonic()

            # 2. 对话列表与目标对话生成统计
            all_resp = rpc_post(srv["port"], srv["csrf"], "GetAllCascadeTrajectories", {"excludeSubtrajectories": False}, timeout=5.0)
            summaries = all_resp.get("trajectorySummaries") or {}
            ordered = []
            for cid, info in summaries.items():
                if not isinstance(info, dict):
                    continue
                ts = parse_iso_ms(info.get("lastModifiedTime")) or 0
                ordered.append((ts, cid, info))
            ordered.sort(key=lambda x: x[0], reverse=True)

            conversations = [
                {
                    "id": cid,
                    "title": (str(info.get("summary") or "未命名对话").strip() or "未命名对话")[:36],
                    "steps": parse_int(info.get("stepCount")) or 0,
                }
                for _, cid, info in ordered[:15]
            ]

            target_id = None
            target_meta = None
            if conversation_id and conversation_id in summaries and isinstance(summaries[conversation_id], dict):
                target_id = conversation_id
                target_meta = summaries[conversation_id]
            elif ordered:
                _, target_id, target_meta = ordered[0]

            speed = None
            if target_id:
                gen_resp = rpc_post(
                    srv["port"],
                    srv["csrf"],
                    "GetCascadeTrajectoryGeneratorMetadata",
                    {"cascadeId": target_id, "includeMessages": False},
                    timeout=6.0,
                )
                generators = gen_resp.get("generatorMetadata") or (gen_resp.get("trajectory") or {}).get("generatorMetadata") or []
                step_count = parse_int((target_meta or {}).get("stepCount"))
                steps = []
                # 仅在步数适中时顺带拉取步数计时用于计算工具用时，避免超大长对话卡顿
                if step_count is not None and step_count <= 1200:
                    try:
                        st_resp = rpc_post(
                            srv["port"],
                            srv["csrf"],
                            "GetCascadeTrajectorySteps",
                            {"cascadeId": target_id, "stepOffset": 0},
                            timeout=5.0,
                        )
                        steps = st_resp.get("steps") or (st_resp.get("trajectory") or {}).get("steps") or []
                    except Exception:
                        steps = []
                speed = parse_trajectory_metrics(generators, steps=steps, step_count=step_count, cascade_id=target_id)
                if target_meta and target_meta.get("summary"):
                    speed["title"] = str(target_meta["summary"])

            self.last_error = None
            return {
                "connection": "live",
                "serverTimeMs": now_ms,
                "error": None,
                "groups": self.quota_cache,
                "conversations": conversations,
                "speed": speed,
            }
        except Exception as exc:
            self.server = None
            self.last_error = str(exc)
            return {
                "connection": "stale",
                "serverTimeMs": now_ms,
                "error": f"采集异常：{exc}",
                "groups": self.quota_cache,
                "conversations": [],
                "speed": None,
            }


if __name__ == "__main__":
    c = PulseCollector()
    snap = c.snapshot(force_quota=True)
    print(json.dumps(snap, ensure_ascii=False, indent=2))
