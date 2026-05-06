#!/usr/bin/env python3
"""
Sekai 海外节点基准测试 — Kimi 模型
====================================
从北美/海外发起测试，测量 Kimi K2.5 / K2.6 的真实链路性能。

用法:
  export KIMI_API_KEY="sk-xxx"
  python3 benchmark_sekai_overseas_kimi.py
  python3 benchmark_sekai_overseas_kimi.py --rounds 1

需要: Python 3.8+, pip install requests
"""

import json, os, sys, time, argparse, statistics, socket
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("需要 requests 库: pip install requests")
    sys.exit(1)

# ── 模型 & 端点配置 ──────────────────────────────────

MODELS_CONFIG = {
    "kimi-k2.6": {
        "api_url": "https://api.moonshot.ai/v1/chat/completions",
        "api_key_env": "KIMI_API_KEY",
        "thinking_field": "thinking",
        "reasoning_field": "reasoning_content",
        "max_tokens_field": "max_tokens",
        "max_tokens": 16384,
        "cache_tokens_field": None,
        "miss_tokens_field": None,
    },
    "kimi-k2.5": {
        "api_url": "https://api.moonshot.ai/v1/chat/completions",
        "api_key_env": "KIMI_API_KEY",
        "thinking_field": "thinking",
        "reasoning_field": "reasoning_content",
        "max_tokens_field": "max_tokens",
        "max_tokens": 16384,
        "cache_tokens_field": None,
        "miss_tokens_field": None,
    },
}

# ── Prompt 定义（与国内测试完全一致）──────────────────

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

# ── 网络延迟预检 ──────────────────────────────────────

def measure_rtt(url):
    from urllib.parse import urlparse
    host = urlparse(url).hostname
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return {"dns_ms": -1, "ip": "resolve_failed"}
    start = time.time()
    try:
        sock = socket.create_connection((ip, 443), timeout=10)
        rtt = (time.time() - start) * 1000
        sock.close()
    except (socket.timeout, OSError):
        rtt = -1
    try:
        resp = requests.get(f"https://{host}/", timeout=10)
        http_time = resp.elapsed.total_seconds() * 1000
    except Exception:
        http_time = -1
    return {"host": host, "ip": ip, "tcp_rtt_ms": round(rtt, 1), "http_ms": round(http_time, 1)}

# ── API 调用 ──────────────────────────────────────────

def call_api(model, prompt_type, thinking, lang, config):
    api_key = os.environ.get(config["api_key_env"], "")
    if not api_key:
        return {"error": f"Missing {config['api_key_env']}"}

    prompt_text = PROMPTS[prompt_type][lang]
    system_msg = "You are an expert front-end developer. Generate clean, working, single-file HTML code." if lang == "en" else "你是一个专业的前端开发者。生成干净、可用的单文件 HTML 代码。"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt_text},
    ]

    body = {
        "model": model,
        "messages": messages,
        config["max_tokens_field"]: config["max_tokens"],
        "temperature": 1 if thinking == "enabled" else 0.6,
        "stream": True,
    }

    if config["thinking_field"] == "thinking":
        body["thinking"] = {"type": thinking}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    metrics = {
        "ttft_s": None, "e2e_s": None, "thinking_time_s": None,
        "thinking_tokens": 0, "content_tokens": 0,
        "content": "", "reasoning": "", "network_ttfb_ms": None,
    }

    t_start = time.time()

    try:
        resp = requests.post(config["api_url"], headers=headers, json=body, stream=True, timeout=600)
        metrics["network_ttfb_ms"] = round(resp.elapsed.total_seconds() * 1000, 1)

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

        t_first_token = None
        thinking_start = None

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            now = time.time()

            if t_first_token is None:
                t_first_token = now
                metrics["ttft_s"] = round(now - t_start, 3)

            rc = delta.get("reasoning_content", "") or ""
            if rc:
                if thinking_start is None:
                    thinking_start = now
                metrics["reasoning"] += rc
                metrics["thinking_tokens"] += 1

            c = delta.get("content", "") or ""
            if c:
                if thinking_start and metrics["thinking_time_s"] is None:
                    metrics["thinking_time_s"] = round(now - thinking_start, 3)
                metrics["content"] += c
                metrics["content_tokens"] += 1

        t_end = time.time()
        metrics["e2e_s"] = round(t_end - t_start, 3)

        if metrics["thinking_time_s"] is None:
            metrics["thinking_time_s"] = 0

        if metrics["content_tokens"] == 0 and metrics["content"]:
            metrics["content_tokens"] = len(metrics["content"]) // 3
        if metrics["thinking_tokens"] == 0 and metrics["reasoning"]:
            metrics["thinking_tokens"] = len(metrics["reasoning"]) // 3

        content_time = metrics["e2e_s"] - (metrics["ttft_s"] or 0)
        if content_time > 0 and metrics["content_tokens"] > 0:
            metrics["decode_tps"] = round(metrics["content_tokens"] / content_time, 1)
        else:
            metrics["decode_tps"] = 0

    except requests.exceptions.Timeout:
        metrics["error"] = "Request timeout (600s)"
    except Exception as e:
        metrics["error"] = str(e)

    return metrics

# ── 代码质量检查 ──────────────────────────────────────

def check_quality(content):
    if not content:
        return 0
    score = 0
    if "<html" in content.lower() or "<!doctype" in content.lower(): score += 1
    if "<script" in content.lower(): score += 1
    if "<style" in content.lower() or "style>" in content.lower(): score += 1
    if "function" in content or "=>" in content: score += 1
    if "event" in content.lower() or "onclick" in content.lower() or "addeventlistener" in content.lower(): score += 1
    return score

# ── 主流程 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sekai 海外基准测试 — Kimi")
    parser.add_argument("--models", nargs="+", default=list(MODELS_CONFIG.keys()))
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--thinking", nargs="+", default=["disabled"], choices=["enabled", "disabled"])
    parser.add_argument("--lang", nargs="+", default=["en"], choices=["zh", "en"])
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    print("=" * 80)
    print("Sekai 海外基准测试 — Kimi")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"模型: {args.models}")
    print(f"场景: code_gen, quiz, game, remix, tool")
    print(f"Thinking: {args.thinking}")
    print(f"语言: {args.lang}")
    print(f"轮数: {args.rounds}")
    print("=" * 80)

    # 网络预检
    print("\n--- 网络延迟预检 ---")
    tested_endpoints = set()
    net_info = {}
    for model in args.models:
        cfg = MODELS_CONFIG[model]
        url = cfg["api_url"]
        if url not in tested_endpoints:
            tested_endpoints.add(url)
            print(f"  测量 {url} ...", end=" ", flush=True)
            rtt = measure_rtt(url)
            net_info[url] = rtt
            print(f"TCP RTT: {rtt['tcp_rtt_ms']}ms, HTTP: {rtt['http_ms']}ms, IP: {rtt['ip']}")

    # 执行测试
    results = {}
    total = len(args.models) * len(PROMPTS) * len(args.thinking) * len(args.lang)
    done = 0

    for model in args.models:
        cfg = MODELS_CONFIG[model]
        if not os.environ.get(cfg["api_key_env"]):
            print(f"\n⚠️  跳过 {model}（缺少 {cfg['api_key_env']}）")
            continue

        for prompt_type in PROMPTS:
            for thinking in args.thinking:
                for lang in args.lang:
                    key = f"{model}__{prompt_type}__think_{thinking}__lang_{lang}"
                    done += 1
                    print(f"\n[{done}/{total}] {key}")

                    rounds_data = []
                    for rnd in range(1, args.rounds + 1):
                        print(f"  Round {rnd}/{args.rounds}...", end=" ", flush=True)
                        m = call_api(model, prompt_type, thinking, lang, cfg)
                        if "error" in m:
                            print(f"ERROR: {m['error']}")
                            rounds_data.append({"error": m["error"], "round": rnd})
                        else:
                            quality = check_quality(m["content"])
                            m["quality"] = quality
                            m["round"] = rnd
                            del m["content"]
                            del m["reasoning"]
                            rounds_data.append(m)
                            print(f"E2E={m['e2e_s']}s TTFT={m['ttft_s']}s "
                                  f"Dec={m.get('decode_tps',0)}tok/s "
                                  f"NetTTFB={m.get('network_ttfb_ms',0)}ms "
                                  f"Q={quality}/5")

                    valid = [r for r in rounds_data if "error" not in r]
                    errors = [r for r in rounds_data if "error" in r]
                    summary = {"rounds_valid": len(valid), "rounds_error": len(errors)}

                    if valid:
                        for field in ["e2e_s", "ttft_s", "decode_tps", "thinking_time_s",
                                      "thinking_tokens", "content_tokens", "network_ttfb_ms", "quality"]:
                            vals = [r[field] for r in valid if r.get(field) is not None]
                            if vals:
                                summary[field] = {
                                    "avg": round(statistics.mean(vals), 2),
                                    "min": round(min(vals), 2),
                                    "max": round(max(vals), 2),
                                    "p50": round(statistics.median(vals), 2),
                                }

                    results[key] = {
                        "config": {"model": model, "prompt_type": prompt_type,
                                   "thinking": thinking, "lang": lang, "rounds": args.rounds},
                        "summary": summary,
                        "rounds": rounds_data,
                        "network": net_info.get(cfg["api_url"], {}),
                    }

    # 输出
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = args.output or f"overseas_kimi_{timestamp}.json"
    output_path = Path(__file__).parent / "results" / "overseas" / "kimi" / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "meta": {
            "test_type": "overseas_kimi",
            "timestamp": timestamp,
            "hostname": socket.gethostname(),
            "network_precheck": net_info,
        },
        "results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print(f"结果已保存: {output_path}")
    print(f"有效测试: {sum(1 for r in results.values() if r['summary']['rounds_valid'] > 0)}/{len(results)}")

    # 摘要
    print(f"\n{'=' * 80}")
    print("快速摘要")
    print(f"{'=' * 80}")
    print(f"{'模型':<20} {'场景':<10} {'Think':<9} {'E2E':>6} {'TTFT':>6} {'Decode':>7} {'NetTTFB':>9} {'质量':>4}")
    print("-" * 80)
    for key in sorted(results.keys()):
        s = results[key]["summary"]
        if s["rounds_valid"] == 0:
            continue
        c = results[key]["config"]
        e2e = s.get("e2e_s", {}).get("avg", 0)
        ttft = s.get("ttft_s", {}).get("avg", 0)
        dec = s.get("decode_tps", {}).get("avg", 0)
        net_ttfb = s.get("network_ttfb_ms", {}).get("avg", 0)
        q = s.get("quality", {}).get("avg", 0)
        print(f"{c['model']:<20} {c['prompt_type']:<10} {c['thinking']:<9} "
              f"{e2e:>5.1f}s {ttft:>5.2f}s {dec:>6.1f}t/s {net_ttfb:>7.0f}ms {q:>4.1f}")

if __name__ == "__main__":
    main()
