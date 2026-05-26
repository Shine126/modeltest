#!/usr/bin/env python3
"""
GPT-5.x TTFT Benchmark via Z.AI Router
=======================================
Tests gpt-5.2 and gpt-5.4 with thinking ON/OFF.
Measures TTFT (Time To First Token) for each configuration.

Usage:
  python benchmark_ttft_gpt5.py --api-key YOUR_KEY
  ZAI_API_KEY=xxx python benchmark_ttft_gpt5.py --rounds 10 --region na
"""

import json
import time
import urllib.request
import urllib.error
import ssl
import argparse
import statistics
import os
from datetime import datetime

API_URL = "https://router.z.ai/api/v1/chat/completions"

MODELS = ["gpt-5.2", "gpt-5.4"]

TEST_PROMPT = (
    "你是一位资深软件架构师。请分析以下技术选型的利弊并给出建议：\n\n"
    "我们正在为一个中型电商平台选择技术栈，团队有 8 名全栈工程师，"
    "熟悉 Python 和 JavaScript。系统需要支持：\n"
    "- 日活 50 万用户\n- 高峰期 QPS 5000\n- 商品搜索（ES）\n"
    "- 订单管理（事务一致性）\n- 推荐系统（实时计算）\n\n"
    "候选方案：\nA) Django + Celery + PostgreSQL + Redis\n"
    "B) FastAPI + SQLAlchemy + PostgreSQL + Redis\n"
    "C) Next.js API Routes + Prisma + PostgreSQL\n\n"
    "请从开发效率、性能、可维护性三个维度打分（1-10），并推荐最终方案。"
)


def percentile(data: list, p: float) -> float:
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(s):
        return round(s[f], 3)
    return round(s[f] + (k - f) * (s[c] - s[f]), 3)


def measure_ttft(api_key: str, model: str, prompt: str, thinking_on: bool = False) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_completion_tokens": 256,
    }
    if thinking_on:
        payload["reasoning_effort"] = "high"

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    ctx = ssl.create_default_context()
    result = {
        "model": model,
        "thinking_on": thinking_on,
        "ttft_first_data": None,
        "ttft_first_content": None,
        "ttft_first_reasoning": None,
        "ttft": None,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "e2e_s": None,
        "error": None,
    }

    t_start = time.monotonic()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
            t_first_data = None
            t_first_content = None
            t_first_reasoning = None

            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break

                now = time.monotonic()

                if t_first_data is None:
                    t_first_data = now

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    if chunk.get("usage"):
                        _extract_usage(chunk["usage"], result)
                    continue

                delta = choices[0].get("delta", {})

                reasoning = delta.get("reasoning_content", "")
                if reasoning and t_first_reasoning is None:
                    t_first_reasoning = now

                content = delta.get("content", "")
                if content and t_first_content is None:
                    t_first_content = now

                if chunk.get("usage"):
                    _extract_usage(chunk["usage"], result)

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
        except json.JSONDecodeError:
            err_data = {"error": raw}
        result["error"] = {"http_status": exc.code, "detail": err_data}
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}

    t_end = time.monotonic()
    result["e2e_s"] = round(t_end - t_start, 3)

    if t_first_content:
        result["ttft_first_content"] = round(t_first_content - t_start, 3)
        result["ttft"] = result["ttft_first_content"]
    elif t_first_data:
        result["ttft_first_data"] = round(t_first_data - t_start, 3)
        result["ttft"] = result["ttft_first_data"]
    if t_first_data:
        result["ttft_first_data"] = round(t_first_data - t_start, 3)
    if t_first_reasoning:
        result["ttft_first_reasoning"] = round(t_first_reasoning - t_start, 3)

    return result


def _extract_usage(usage: dict, result: dict):
    result["prompt_tokens"] = usage.get("prompt_tokens", 0)
    result["completion_tokens"] = usage.get("completion_tokens", 0)
    result["total_tokens"] = usage.get("total_tokens", 0)
    comp_details = usage.get("completion_tokens_details", {})
    if isinstance(comp_details, dict):
        result["reasoning_tokens"] = comp_details.get("reasoning_tokens", 0)


def main():
    parser = argparse.ArgumentParser(description="GPT-5.x TTFT Benchmark via Z.AI Router")
    parser.add_argument("--api-key", help="Z.AI API Key (or set ZAI_API_KEY env)")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per test (default: 10)")
    parser.add_argument("--region", default="unknown", help="Region label (na/japan)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ZAI_API_KEY")
    if not api_key:
        print("ERROR: No API key. Use --api-key or set ZAI_API_KEY env.")
        return 1

    ip_info = "unknown"
    try:
        with urllib.request.urlopen(urllib.request.Request("https://ipinfo.io/json"), timeout=10) as r:
            ip_data = json.loads(r.read().decode())
            ip_info = f"{ip_data.get('ip', '?')} ({ip_data.get('city', '?')}, {ip_data.get('country', '?')})"
    except Exception:
        pass

    print(f"\n{'='*80}")
    print(f"GPT-5.x TTFT Benchmark via Z.AI Router")
    print(f"Region: {args.region}  |  IP: {ip_info}")
    print(f"Models: {', '.join(MODELS)}  |  Rounds: {args.rounds}")
    print(f"Thinking modes: ON (reasoning_effort=high), OFF (default)")
    print(f"{'='*80}")

    all_results = {}

    for model in MODELS:
        model_results = {}
        for thinking_on in [False, True]:
            mode_label = "thinking_on" if thinking_on else "thinking_off"
            print(f"\n[{model}] {mode_label} — {args.rounds} rounds")
            rounds_data = []

            for rnd in range(1, args.rounds + 1):
                print(f"  Round {rnd}/{args.rounds} ... ", end="", flush=True)
                r = measure_ttft(api_key, model, TEST_PROMPT, thinking_on)
                rounds_data.append(r)

                if r["error"]:
                    print(f"ERROR: {r['error']}")
                else:
                    parts = [f"TTFT={r['ttft']}s"]
                    if r.get("ttft_first_reasoning") is not None:
                        parts.append(f"reasoning_first={r['ttft_first_reasoning']}s")
                    if r.get("ttft_first_content") is not None:
                        parts.append(f"content_first={r['ttft_first_content']}s")
                    parts.append(f"prompt_tok={r['prompt_tokens']}")
                    parts.append(f"e2e={r['e2e_s']}s")
                    print("  ".join(parts))

                if rnd < args.rounds:
                    time.sleep(0.5)

            valid = [r for r in rounds_data if not r["error"]]
            ttfts = [r["ttft"] for r in valid if r.get("ttft") is not None]
            ttfts_reasoning = [r["ttft_first_reasoning"] for r in valid if r.get("ttft_first_reasoning") is not None]
            prompt_toks = [r["prompt_tokens"] for r in valid if r["prompt_tokens"]]
            reasoning_toks = [r["reasoning_tokens"] for r in valid if r["reasoning_tokens"]]

            summary = {
                "model": model,
                "thinking_on": thinking_on,
                "rounds_valid": len(valid),
                "rounds_error": len([r for r in rounds_data if r["error"]]),
                "avg_prompt_tokens": round(statistics.mean(prompt_toks)) if prompt_toks else 0,
                "avg_reasoning_tokens": round(statistics.mean(reasoning_toks)) if reasoning_toks else 0,
                "ttft_s": {
                    "min": min(ttfts) if ttfts else None,
                    "max": max(ttfts) if ttfts else None,
                    "avg": round(statistics.mean(ttfts), 3) if ttfts else None,
                    "p50": percentile(ttfts, 50),
                    "p95": percentile(ttfts, 95),
                } if ttfts else {},
                "ttft_first_reasoning_s": {
                    "avg": round(statistics.mean(ttfts_reasoning), 3) if ttfts_reasoning else None,
                },
                "rounds_detail": rounds_data,
            }
            model_results[mode_label] = summary

            if ttfts:
                t = summary["ttft_s"]
                print(f"  => TTFT avg={t['avg']}s  p50={t['p50']}s  "
                      f"p95={t['p95']}s  min={t['min']}s  max={t['max']}s")

        all_results[model] = model_results

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_dir = f"sekai/results/gpt5-ttft/{args.region}"
    os.makedirs(result_dir, exist_ok=True)
    result_file = f"{result_dir}/gpt5_ttft_{args.region}_{ts}.json"

    output = {
        "timestamp": ts,
        "region": args.region,
        "ip_info": ip_info,
        "rounds": args.rounds,
        "results": all_results,
    }
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n\n{'='*100}")
    print(f"GPT-5.x TTFT Benchmark Summary — Region: {args.region}")
    print(f"{'='*100}")
    print(f"{'Model':<12} {'Mode':<15} {'Valid':>5} {'TTFT avg':>10} {'TTFT p50':>10} "
          f"{'TTFT p95':>10} {'TTFT min':>10} {'TTFT max':>10} {'ReasoningTok':>13}")
    print("-" * 100)

    for model, modes in all_results.items():
        for mode, s in modes.items():
            if not s["rounds_valid"]:
                print(f"{model:<12} {mode:<15} {'ERR':>5}")
                continue
            t = s["ttft_s"]
            print(f"{model:<12} {mode:<15} {s['rounds_valid']:>5} "
                  f"{t['avg']:>9.3f}s {t['p50']:>9.3f}s {t['p95']:>9.3f}s "
                  f"{t['min']:>9.3f}s {t['max']:>9.3f}s "
                  f"{s.get('avg_reasoning_tokens', 0):>13}")

    print(f"\nDetailed data: {result_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
