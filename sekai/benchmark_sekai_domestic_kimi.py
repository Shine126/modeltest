#!/usr/bin/env python3
"""
Sekai 场景基准测试 — Kimi (Moonshot) 模型
==========================================
基于 benchmark_sekai.py 适配 Kimi API。

测试场景: 5 类 Sekai 真实场景（代码生成/Quiz/游戏/Remix/工具）
模型: kimi-k2.6, kimi-k2.5
矩阵: 2 models × 5 prompts × 2 thinking × 2 langs × N rounds

API 文档: https://platform.kimi.ai/docs/api/chat.md

用法:
  export MOONSHOT_API_KEY="your-key"
  python benchmark_sekai_kimi.py
  python benchmark_sekai_kimi.py --models kimi-k2.6 --rounds 3
"""

import json, os, sys, time, urllib.request, urllib.error, ssl, argparse, statistics, re
from pathlib import Path
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────

API_URL = "https://api.moonshot.cn/v1/chat/completions"
API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
OUTPUT_DIR = Path(__file__).parent / "results" / "domestic" / "kimi"

MODELS = ["kimi-k2.6", "kimi-k2.5"]
THINKING_MODES = ["enabled", "disabled"]
LANGUAGES = ["zh", "en"]
PROMPT_TYPES = ["code_gen", "quiz", "game", "remix", "tool"]

DEFAULT_ROUNDS = 2
DEFAULT_MAX_TOKENS = 16384

# ── Remix 基础代码 ───────────────────────────────────

SNAKE_CODE = """<!DOCTYPE html>
<html><head><title>Snake</title><style>
body{margin:0;display:flex;justify-content:center;align-items:center;height:100vh;background:#1a1a2e}
canvas{border:2px solid #e94560}</style></head>
<body><canvas id="c" width="400" height="400"></canvas><script>
const c=document.getElementById('c'),ctx=c.getContext('2d'),s=20,cols=c.width/s;
let snake=[{x:10,y:10}],food=spawn(),dx=1,dy=0,score=0,over=false;
function spawn(){return{x:Math.floor(Math.random()*cols),y:Math.floor(Math.random()*cols)}}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowUp'&&dy===0){dx=0;dy=-1}
  if(e.key==='ArrowDown'&&dy===0){dx=0;dy=1}
  if(e.key==='ArrowLeft'&&dx===0){dx=-1;dy=0}
  if(e.key==='ArrowRight'&&dx===0){dx=1;dy=0}
});
function update(){
  if(over)return;
  const h={x:snake[0].x+dx,y:snake[0].y+dy};
  if(h.x<0||h.x>=cols||h.y<0||h.y>=cols||snake.some(s=>s.x===h.x&&s.y===h.y)){over=true;return}
  snake.unshift(h);
  if(h.x===food.x&&h.y===food.y){score++;food=spawn()}else snake.pop()
}
function draw(){
  ctx.fillStyle='#1a1a2e';ctx.fillRect(0,0,c.width,c.height);
  ctx.fillStyle='#0f3460';snake.forEach(s=>ctx.fillRect(s.x*s,s.y*s,s-1,s-1));
  ctx.fillStyle='#e94560';ctx.fillRect(food.x*s,food.y*s,s-1,s-1);
  ctx.fillStyle='#fff';ctx.font='16px monospace';ctx.fillText('Score: '+score,10,20);
  if(over){ctx.fillStyle='#e94560';ctx.font='24px monospace';ctx.fillText('Game Over',130,200)}
}
setInterval(()=>{update();draw()},100)
</script></body></html>"""

# ── Prompt 定义 ───────────────────────────────────────

PROMPTS = {
    "code_gen": {
        "en": """Create a memory card matching game as a single HTML file. Requirements:
- 8 pairs of animal emojis (16 cards total) on a 4x4 grid
- Click to flip cards, match pairs to remove them
- Score tracking (moves counter, time elapsed)
- Flip animation using CSS transitions
- Win screen showing moves and time when all pairs matched
- Responsive design, clean modern UI with a color scheme
Write complete, runnable HTML/CSS/JavaScript code.""",

        "zh": """创建一个记忆翻牌配对游戏，输出为单个HTML文件。要求：
- 8对动物emoji（共16张牌），4x4网格布局
- 点击翻牌，配对成功消除
- 计分系统（步数计数、计时器）
- CSS过渡翻牌动画
- 全部配对成功后显示胜利画面（步数和用时）
- 响应式设计，简洁现代UI配色
输出完整可运行的HTML/CSS/JavaScript代码。""",
    },

    "quiz": {
        "en": """Create a personality quiz "What kind of creator are you?" as a single HTML file. Requirements:
- 10 multiple-choice questions about creative preferences
- 4 options per question, each mapped to a creator type
- 5 result types: Visual Artist, Storyteller, Game Designer, Music Maker, Code Wizard
- Scoring algorithm that tallies option frequencies
- Result page with type description, traits, and a progress-bar visualization
- Beautiful UI with card-based question layout, smooth transitions
- Restart button on result page
Write complete, runnable HTML/CSS/JavaScript code.""",

        "zh": """创建一个"你是哪种创作者？"人格测试，输出为单个HTML文件。要求：
- 10道关于创作偏好的选择题
- 每题4个选项，映射到不同创作者类型
- 5种结果类型：视觉艺术家、故事讲述者、游戏设计师、音乐人、代码巫师
- 评分算法统计选项频率
- 结果页包含类型描述、特征、进度条可视化
- 卡片式问题布局，平滑过渡动画
- 结果页有重新测试按钮
输出完整可运行的HTML/CSS/JavaScript代码。""",
    },

    "game": {
        "en": """Create a text-based adventure game "Escape the Haunted House" as a single HTML file. Requirements:
- At least 8 rooms: Entrance Hall, Library, Kitchen, Basement, Attic, Garden, Secret Passage, Exit
- Each room has a description, choices (2-3 options), and possible items to find
- Inventory system: player can collect and use items (keys, flashlight, map, potion)
- Multiple endings (at least 3): escape, trapped, discover secret treasure
- Health/sanity meter that changes based on choices
- Atmospheric dark theme with room illustrations using ASCII art or emoji
- Save game state to localStorage
Write complete, runnable HTML/CSS/JavaScript code.""",

        "zh": """创建一个"逃离鬼屋"文字冒险游戏，输出为单个HTML文件。要求：
- 至少8个房间：大厅、图书馆、厨房、地下室、阁楼、花园、密道、出口
- 每个房间有描述、2-3个选择、可发现道具
- 道具系统：收集和使用道具（钥匙、手电筒、地图、药水）
- 多结局（至少3种）：逃脱、被困、发现宝藏
- 生命值/理智值根据选择变化
- 暗黑主题氛围，房间用ASCII art或emoji装饰
- 游戏状态保存到localStorage
输出完整可运行的HTML/CSS/JavaScript代码。""",
    },

    "remix": {
        "en": f"""Here is a simple Snake game:

```html
{SNAKE_CODE}
```

Convert this into a two-player Snake battle game. Requirements:
- Player 1: Arrow keys (blue snake), Player 2: WASD keys (green snake)
- Both snakes move simultaneously on the same board
- Power-ups spawn randomly: Speed Boost (blue icon, 2x speed for 3s), Freeze Enemy (red icon, freeze opponent for 2s), Wall Pass (green icon, pass through walls for 5s)
- Score display for both players
- Collision detection: hitting yourself, opponent, or wall = death
- Game over screen showing winner
Keep the same visual style and dark theme. Output the complete HTML file.""",

        "zh": f"""这是一个简单的贪吃蛇游戏：

```html
{SNAKE_CODE}
```

把它改写成双人贪吃蛇对战游戏。要求：
- 玩家1：方向键控制（蓝色蛇），玩家2：WASD控制（绿色蛇）
- 两条蛇同时在同一棋盘移动
- 随机道具：加速（蓝色图标，2倍速3秒）、冰冻对手（红色图标，冻结对手2秒）、穿墙（绿色图标，穿墙5秒）
- 双方分数显示
- 碰撞检测：撞自己、对手或墙壁即死
- 游戏结束显示胜者
保持原有视觉风格和暗黑主题。输出完整HTML文件。""",
    },

    "tool": {
        "en": """Create a Pomodoro Timer app as a single HTML file. Requirements:
- Customizable work duration (default 25min) and break duration (default 5min)
- Visual circular progress ring showing time remaining
- Task list: add tasks, mark complete, estimated pomodoros per task
- Session counter: how many pomodoros completed today
- Sound notification (use Web Audio API beep) when timer ends
- Auto-switch between work and break modes
- Statistics panel: total focus time, tasks completed, pomodoro streak
- Clean, minimal UI with light/dark mode toggle
Write complete, runnable HTML/CSS/JavaScript code.""",

        "zh": """创建一个番茄钟应用，输出为单个HTML文件。要求：
- 可自定义工作时长（默认25分钟）和休息时长（默认5分钟）
- 圆形进度环显示剩余时间
- 任务列表：添加任务、标记完成、预估番茄数
- 计数器：今日完成番茄数
- 计时结束时声音提醒（使用Web Audio API蜂鸣）
- 自动切换工作和休息模式
- 统计面板：总专注时长、已完成任务、连续番茄记录
- 简洁UI，支持亮/暗模式切换
输出完整可运行的HTML/CSS/JavaScript代码。""",
    },
}


# ── 代码质量检测 ─────────────────────────────────────

def check_code_quality(content: str) -> dict:
    if not content:
        return {"has_html": False, "has_script": False, "has_css": False, "has_function": False, "has_event": False, "quality_score": 0}
    checks = {
        "has_html": bool(re.search(r"<html|<!DOCTYPE", content, re.I)),
        "has_script": bool(re.search(r"<script", content, re.I)),
        "has_css": bool(re.search(r"<style|\.style\b", content, re.I)),
        "has_function": bool(re.search(r"function\s|=>\s|addEventListener", content)),
        "has_event": bool(re.search(r"addEventListener|onclick|onkeydown|on\w+\s*=", content, re.I)),
    }
    checks["quality_score"] = sum(1 for v in checks.values() if v)
    return checks


# ── API 调用 ──────────────────────────────────────────

def call_kimi_streaming(model: str, thinking_type: str, prompt_type: str, lang: str, max_tokens: int, timeout: int = 600) -> dict:
    prompt = PROMPTS[prompt_type][lang]

    # Kimi 硬性要求：thinking=enabled 时 temperature=1，disabled 时 temperature=0.6
    temp = 1.0 if thinking_type == "enabled" else 0.6

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": temp,
    }

    if thinking_type:
        payload["thinking"] = {"type": thinking_type}

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )

    ctx = ssl.create_default_context()
    metrics = {
        "model": model, "thinking_type": thinking_type, "prompt_type": prompt_type,
        "lang": lang, "max_tokens": max_tokens,
        "ttft": None, "first_content_token_time": None,
        "thinking_tokens": 0, "content_tokens": 0,
        "thinking_time_s": 0, "decode_time_s": 0, "e2e_s": 0,
        "finish_reason": None, "usage": None, "error": None,
        "content_sample": "", "code_quality": {},
    }

    t_start = time.monotonic()
    full_content = []
    thinking_done = False
    t_first_token = None
    t_first_content = None
    t_thinking_end = None

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:

            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                now = time.monotonic()
                if t_first_token is None:
                    t_first_token = now

                choices = chunk.get("choices", [])
                if not choices:
                    # usage-only chunk (final)
                    if chunk.get("usage"):
                        metrics["usage"] = chunk["usage"]
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    metrics["finish_reason"] = finish_reason

                # Kimi streaming: reasoning_content for thinking, content for output
                reasoning = delta.get("reasoning_content", "")
                if reasoning:
                    metrics["thinking_tokens"] += 1
                    if not thinking_done:
                        t_thinking_end = now

                content = delta.get("content", "")
                if content:
                    metrics["content_tokens"] += 1
                    full_content.append(content)
                    if not thinking_done and metrics["thinking_tokens"] > 0:
                        thinking_done = True
                        t_thinking_end = t_thinking_end or now
                    if t_first_content is None:
                        t_first_content = now

                # usage 可能在最后一个有 choices 的 chunk 里
                if chunk.get("usage"):
                    metrics["usage"] = chunk["usage"]

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
        except json.JSONDecodeError:
            err_data = {"error": raw}
        metrics["error"] = {"http_status": exc.code, "detail": err_data}
    except Exception as exc:
        metrics["error"] = {"type": type(exc).__name__, "message": str(exc)}

    t_end = time.monotonic()
    metrics["e2e_s"] = round(t_end - t_start, 2)

    if t_first_token:
        metrics["ttft"] = round(t_first_token - t_start, 2)

    if thinking_done and t_thinking_end:
        metrics["thinking_time_s"] = round(t_thinking_end - t_start, 2)
        metrics["decode_time_s"] = round(t_end - t_thinking_end, 2)
    elif t_first_content:
        metrics["thinking_time_s"] = 0
        metrics["decode_time_s"] = round(t_end - t_first_content, 2)

    # 使用 usage 中的精确 token 计数
    if metrics["usage"]:
        u = metrics["usage"]
        metrics["content_tokens"] = u.get("completion_tokens", metrics["content_tokens"])

    if metrics["decode_time_s"] > 0 and metrics["content_tokens"] > 0:
        metrics["decode_toks"] = round(metrics["content_tokens"] / metrics["decode_time_s"], 1)
    else:
        metrics["decode_toks"] = 0

    if metrics["thinking_time_s"] > 0 and metrics["thinking_tokens"] > 0:
        metrics["thinking_toks"] = round(metrics["thinking_tokens"] / metrics["thinking_time_s"], 1)
    else:
        metrics["thinking_toks"] = 0

    content_text = "".join(full_content)
    metrics["content_sample"] = content_text[:500]
    metrics["code_quality"] = check_code_quality(content_text)

    return metrics


# ── 汇总统计 ──────────────────────────────────────────

def percentile(data: list, p: float) -> float:
    if not data:
        return 0
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_d):
        return round(sorted_d[f], 2)
    return round(sorted_d[f] + (k - f) * (sorted_d[c] - sorted_d[f]), 2)


def summarize(results: list) -> dict:
    valid = [r for r in results if not r["error"]]
    e2e = [r["e2e_s"] for r in valid if r["e2e_s"]]
    ttft = [r["ttft"] for r in valid if r.get("ttft")]
    decode_tps = [r["decode_toks"] for r in valid if r.get("decode_toks")]
    thinking_s = [r["thinking_time_s"] for r in valid if r.get("thinking_time_s")]
    thinking_toks = [r["thinking_tokens"] for r in valid]
    content_toks = [r["content_tokens"] for r in valid]
    quality_scores = [r["code_quality"].get("quality_score", 0) for r in valid]

    return {
        "rounds_valid": len(valid),
        "rounds_error": len([r for r in results if r["error"]]),
        "e2e_s": {"p50": percentile(e2e, 50), "p95": percentile(e2e, 95), "min": min(e2e) if e2e else 0, "max": max(e2e) if e2e else 0},
        "ttft_s": {"p50": percentile(ttft, 50), "p95": percentile(ttft, 95)},
        "decode_tps": {"p50": percentile(decode_tps, 50), "p95": percentile(decode_tps, 95), "min": min(decode_tps) if decode_tps else 0, "max": max(decode_tps) if decode_tps else 0},
        "thinking_time_s": {"p50": percentile(thinking_s, 50), "avg": round(statistics.mean(thinking_s), 2) if thinking_s else 0},
        "thinking_tokens": {"avg": round(statistics.mean(thinking_toks)) if thinking_toks else 0},
        "content_tokens": {"avg": round(statistics.mean(content_toks)) if content_toks else 0},
        "code_quality_avg": round(statistics.mean(quality_scores), 1) if quality_scores else 0,
    }


# ── 主流程 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sekai 场景基准测试 — Kimi (Moonshot)")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--output-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--models", nargs="+", default=MODELS)
    parser.add_argument("--thinking", nargs="+", default=THINKING_MODES)
    parser.add_argument("--langs", nargs="+", default=LANGUAGES)
    parser.add_argument("--prompts", nargs="+", default=PROMPT_TYPES)
    args = parser.parse_args()

    if not API_KEY:
        print("Error: set MOONSHOT_API_KEY env var", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(exist_ok=True)

    all_results = {}
    combos = [(m, p, t, l) for m in args.models for p in args.prompts for t in args.thinking for l in args.langs]
    total = len(combos)

    print(f"\n{'='*70}")
    print(f"Sekai 场景基准测试 (Kimi) — {total} 组合 × {args.rounds} 轮 = {total * args.rounds} 次调用")
    print(f"模型: {args.models}  场景: {args.prompts}  max_tokens: {args.output_tokens}")
    print(f"API: {API_URL}")
    print(f"{'='*70}")

    for idx, (model, prompt_type, thinking, lang) in enumerate(combos, 1):
        combo_key = f"{model}__{prompt_type}__think_{thinking}__lang_{lang}"
        print(f"\n{'='*70}")
        print(f"[{idx}/{total}] {model} | {prompt_type} | think={thinking} | lang={lang} | x{args.rounds}")
        print(f"{'='*70}")

        combo_results = []
        for rnd in range(1, args.rounds + 1):
            print(f"  Round {rnd}/{args.rounds} ... ", end="", flush=True)
            # 重试逻辑：网络错误最多重试 3 次，间隔递增
            r = None
            for attempt in range(1, 4):
                r = call_kimi_streaming(model, thinking, prompt_type, lang, args.output_tokens)
                if not r["error"]:
                    break
                if attempt < 3:
                    wait = attempt * 5
                    print(f"RETRY {attempt}/3 (wait {wait}s) ", end="", flush=True)
                    time.sleep(wait)
            combo_results.append(r)

            if r["error"]:
                print(f"ERROR: {r['error']}")
            else:
                parts = [f"E2E={r['e2e_s']}s"]
                if r["thinking_time_s"]:
                    parts.append(f"think={r['thinking_time_s']}s ({r['thinking_tokens']}tok)")
                parts.append(f"decode={r['decode_time_s']}s ({r['content_tokens']}tok @ {r['decode_toks']}tok/s)")
                parts.append(f"quality={r['code_quality'].get('quality_score', 0)}/5")
                print(" | ".join(parts))
            # 请求间延迟 2 秒，避免触发限流
            time.sleep(2)

        summary = summarize(combo_results)
        all_results[combo_key] = {
            "config": {"model": model, "prompt_type": prompt_type, "thinking": thinking, "lang": lang, "max_tokens": args.output_tokens, "rounds": args.rounds},
            "summary": summary,
            "rounds": combo_results,
        }

    # ── 保存 ──────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_file = OUTPUT_DIR / f"kimi_benchmark_{ts}.json"
    save_data = json.loads(json.dumps(all_results))
    for key in save_data:
        for rnd in save_data[key]["rounds"]:
            rnd.pop("content_sample", None)
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    # ── 汇总表 ────────────────────────────────────────
    print(f"\n\n{'='*130}")
    print("汇总报告")
    print(f"{'='*130}")
    print(f"{'模型':<14} {'场景':<10} {'Think':<9} {'Lang':<5} {'E2E p50':>8} {'E2E p95':>8} {'Dec p50':>8} {'Dec p95':>8} {'TTFT':>6} {'ContT':>7} {'质量':>4}")
    print("-" * 130)

    for key, data in all_results.items():
        s = data["summary"]
        c = data["config"]
        if s["rounds_valid"] == 0:
            print(f"{c['model']:<14} {c['prompt_type']:<10} {c['thinking']:<9} {c['lang']:<5} {'ERROR':>8}")
            continue
        print(
            f"{c['model']:<14} {c['prompt_type']:<10} {c['thinking']:<9} {c['lang']:<5} "
            f"{s['e2e_s']['p50']:>6.1f}s  {s['e2e_s']['p95']:>6.1f}s  "
            f"{s['decode_tps']['p50']:>6.1f}   {s['decode_tps']['p95']:>6.1f}   "
            f"{s['ttft_s']['p50']:>4.1f}s  "
            f"{s['content_tokens']['avg']:>7} "
            f"{s['code_quality_avg']:>4.1f}/5"
        )

    print(f"\n详细结果: {result_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
