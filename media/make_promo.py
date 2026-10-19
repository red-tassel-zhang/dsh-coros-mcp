#!/usr/bin/env python3
"""生成 dsh-coros-mcp 的 40 秒推广视频（1920x1080 / 30fps / 无声）。

纯 PIL 逐帧绘制 + ffmpeg 编码，不依赖任何外部素材，所以可以随时改文案重出。

    python media/make_promo.py

输出：
    media/promo.mp4    成片
    media/cover.png    封面（取第一幕中段）
    media/preview_*.png 三张抽帧，方便肉眼检查
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
ROOT = Path(__file__).resolve().parent
# 可以用 FFMPEG=/path/to/ffmpeg 覆盖；默认从 PATH 找
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

# ── 配色 ─────────────────────────────────────────────────────────────────────
BG_TOP = (11, 18, 32)
BG_BOTTOM = (7, 11, 21)
CARD = (17, 26, 43)
CARD_EDGE = (38, 53, 78)
TEXT = (232, 238, 248)
DIM = (138, 152, 175)
FAINT = (86, 100, 122)
TEAL = (45, 212, 191)
AMBER = (251, 191, 36)
RED = (248, 113, 113)
GREEN = (74, 222, 128)

# ── 字体 ─────────────────────────────────────────────────────────────────────
F_CN = r"C:\Windows\Fonts\msyh.ttc"
F_CN_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
F_MONO = r"C:\Windows\Fonts\consola.ttf"
F_MONO_BOLD = r"C:\Windows\Fonts\consolab.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=0)


FONTS = {
    "h1": font(F_CN_BOLD, 74),
    "h2": font(F_CN_BOLD, 54),
    "h3": font(F_CN_BOLD, 40),
    "body": font(F_CN, 30),
    "small": font(F_CN, 25),
    "kicker": font(F_MONO_BOLD, 27),
    "kicker_cn": font(F_CN_BOLD, 27),
    "mono": font(F_MONO, 25),
    "mono_sm": font(F_MONO, 22),
    "cn": font(F_CN, 26),
    "cn_sm": font(F_CN, 23),
    "num": font(F_CN_BOLD, 132),
}


def has_cjk(s: str) -> bool:
    """Consolas 没有汉字字形，会自动渲染成方框 —— 遇到 CJK 就换微软雅黑。"""
    for ch in s:
        if "\u4e00" <= ch <= "\u9fff" or ch in "「」—←":
            return True
    return False


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ease(t: float) -> float:
    """ease-out cubic"""
    t = clamp(t)
    return 1 - (1 - t) ** 3


def alpha_at(t: float, start: float, dur: float = 0.35) -> float:
    return clamp((t - start) / dur)


def background() -> Image.Image:
    """深色渐变 + 左上角柔光，只算一次。"""
    base = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(base)
    for y in range(H):
        k = y / (H - 1)
        draw.line(
            [(0, y), (W, y)],
            fill=(
                int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * k),
                int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * k),
                int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * k),
            ),
        )

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([-420, -520, 1180, 620], fill=(45, 212, 191, 26))
    g.ellipse([1180, 620, 2260, 1500], fill=(56, 120, 255, 22))
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    return Image.alpha_composite(base.convert("RGBA"), glow)


BASE = background()


def layer_text(layer, xy, s, font_key, fill, alpha=1.0, anchor="la", dy=0.0):
    if alpha <= 0.01:
        return
    if has_cjk(s):
        font_key = {"mono": "cn", "mono_sm": "cn_sm", "kicker": "kicker_cn"}.get(font_key, font_key)
    draw = ImageDraw.Draw(layer)
    draw.text(
        (xy[0], xy[1] + dy),
        s,
        font=FONTS[font_key],
        fill=(fill[0], fill[1], fill[2], int(255 * alpha)),
        anchor=anchor,
    )


def layer_rect(layer, box, radius, fill=None, outline=None, width=2, alpha=1.0):
    if alpha <= 0.01:
        return
    draw = ImageDraw.Draw(layer)
    f = None if fill is None else (fill[0], fill[1], fill[2], int(255 * alpha))
    o = None if outline is None else (outline[0], outline[1], outline[2], int(255 * alpha))
    draw.rounded_rectangle(box, radius=radius, fill=f, outline=o, width=width)


def composite(layer: Image.Image) -> Image.Image:
    return Image.alpha_composite(BASE.copy(), layer).convert("RGB")


def kicker(layer, t, label, color=AMBER):
    a = alpha_at(t, 0.0)
    layer_text(layer, (150, 132 + (1 - ease(a)) * 16), label, "kicker", color, a)


def headline(layer, t, s, color=TEXT, start=0.1, y=196):
    a = alpha_at(t, start)
    layer_text(layer, (150, y + (1 - ease(a)) * 22), s, "h2", color, a)


def caption(layer, t, s, color=DIM, start=0.5, y=880):
    a = alpha_at(t, start, 0.4)
    layer_text(layer, (150, y), s, "body", color, a)


def terminal_dots(draw, x, y, alpha=1.0):
    for i, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse(
            [x + i * 30, y, x + i * 30 + 15, y + 15],
            fill=(color[0], color[1], color[2], int(255 * alpha)),
        )


# ── 各幕 ─────────────────────────────────────────────────────────────────────


def scene_title(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a0 = alpha_at(t, 0.0)
    layer_text(layer, (150, 286 + (1 - ease(a0)) * 18), "CASE STUDY  ·  2026", "kicker", TEAL, a0)

    for i, line in enumerate(("把 COROS 官方 MCP", "接进 DeepSeek Harness")):
        a = alpha_at(t, 0.18 + i * 0.16, 0.45)
        dy = (1 - ease(a)) * 30
        layer_text(layer, (150, 344 + i * 100 + dy), line, "h1", TEXT, a)

    a = alpha_at(t, 0.62, 0.4)
    layer_rect(layer, [150, 566, 150 + 520 * ease(a), 573], 3, fill=TEAL, alpha=a)

    a = alpha_at(t, 0.78, 0.4)
    layer_text(layer, (150, 606 + (1 - ease(a)) * 18), "一个 $defs 引发的血案", "h3", AMBER, a)

    a = alpha_at(t, 1.05, 0.5)
    layer_text(
        layer,
        (150, 700 + (1 - ease(a)) * 14),
        "两行配置 + 一个 100 行的代理，让 30+ 个 COROS 工具在 DSH 里跑起来",
        "body",
        DIM,
        a,
    )

    a = alpha_at(t, 1.5, 0.5)
    layer_text(layer, (150, 944), "github.com/red-tassel-zhang/dsh-coros-mcp", "mono", FAINT, a)
    return composite(layer)


def scene_symptom(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kicker(layer, t, "01  ·  症状")
    headline(layer, t, "整轮对话直接 400", start=0.12)
    a = alpha_at(t, 0.34)
    layer_text(
        layer,
        (150, 282 + (1 - ease(a)) * 14),
        "不是某个工具不可用 —— 是这一批 tools 全部没发出去",
        "body",
        DIM,
        a,
    )

    a = alpha_at(t, 0.5, 0.4)
    layer_rect(layer, [150, 360, 1770, 742], 20, fill=(8, 13, 24), outline=CARD_EDGE, alpha=a)
    if a > 0.5:
        draw = ImageDraw.Draw(layer)
        terminal_dots(draw, 182, 392, a)
        layer_text(layer, (300, 386), "dsh  ·  profile: desktop", "mono_sm", FAINT, a)

    lines = [
        ("> 本轮运行失败", DIM, 0.85, "mono"),
        ("Invalid schema for function 'mcp__coros__createScheduledWorkout':", RED, 1.15, "mono"),
        ("Pointer '/$defs/Section' does not exist", RED, 1.55, "mono"),
        ("request_id: 3f9a1c2e-6b7d-4c21-9f0e-2a5b8d1c4e77", FAINT, 2.0, "mono_sm"),
    ]
    for i, (line, color, start, key) in enumerate(lines):
        p = clamp((t - start) / 0.55)
        if p <= 0:
            continue
        shown = line[: max(1, int(len(line) * p))]
        layer_text(layer, (200, 458 + i * 58), shown, key, color, 1.0)

    a = alpha_at(t, 2.5, 0.5)
    layer_rect(layer, [150, 790, 1770, 800], 4, fill=(38, 53, 78), alpha=a)
    caption(
        layer,
        t,
        "读数据全正常，一做课表就炸 —— 坏 schema 只出现在 6 个写工具里",
        DIM,
        start=2.65,
        y=828,
    )
    return composite(layer)


def scene_rootcause(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kicker(layer, t, "02  ·  根因")
    headline(layer, t, "「#」指文档根，可根上没有 $defs", start=0.12)

    a = alpha_at(t, 0.45, 0.4)
    layer_rect(layer, [150, 330, 1170, 762], 20, fill=(8, 13, 24), outline=CARD_EDGE, alpha=a)

    code = [
        ("{", DIM, False),
        ('  "properties": {', DIM, False),
        ('    "course": {', DIM, False),
        ('      "$defs": { "Section": { … } },', AMBER, True),
        ('      "properties": {', DIM, False),
        ('        "sections": {', DIM, False),
        ('          "items": { "$ref": "#/$defs/Section" }', RED, True),
        ("        }", DIM, False),
        ("      }", DIM, False),
        ("    }", DIM, False),
        ("  }", DIM, False),
        ("}", DIM, False),
    ]
    draw = ImageDraw.Draw(layer)
    for i, (line, color, hot) in enumerate(code):
        p = clamp((t - 0.7 - i * 0.07) / 0.25)
        if p <= 0:
            continue
        y = 366 + i * 32
        if hot:
            draw.rounded_rectangle([176, y - 6, 1144, y + 30], radius=6, fill=(color[0], color[1], color[2], 26))
        layer_text(layer, (200, y), line, "mono_sm", color, p)

    for i, (label, color) in enumerate((("← 嵌在子 schema 里", AMBER), ("← 却按文档根去指", RED))):
        a2 = alpha_at(t, 2.0 + i * 0.3, 0.4)
        layer_text(layer, (1150, 462 + i * 96), label, "small", color, a2, anchor="ra")

    a = alpha_at(t, 1.9, 0.4)
    layer_rect(layer, [1210, 330, 1770, 762], 20, fill=CARD, outline=CARD_EDGE, alpha=a)
    layer_text(layer, (1250, 366), "受影响 · 6 个写工具", "small", TEXT, a)
    tools = [
        "createScheduledWorkout",
        "updateScheduledWorkout",
        "createTrainingPlan",
        "updateTrainingPlan",
        "createSingleWorkout",
        "updateWorkoutDetails",
    ]
    for i, name in enumerate(tools):
        a2 = alpha_at(t, 2.1 + i * 0.12, 0.35)
        layer_text(layer, (1250, 420 + i * 46), name, "mono_sm", DIM, a2)
        layer_text(layer, (1250, 420 + i * 46), "mcp__coros__", "mono_sm", FAINT, 0.0)

    a = alpha_at(t, 2.9, 0.45)
    layer_rect(layer, [150, 800, 1770, 810], 4, fill=(38, 53, 78), alpha=a)
    layer_text(layer, (150, 836), "合规写法：把 $defs 提到 schema 根，$ref 立刻就解析得开", "body", GREEN, a)
    return composite(layer)


def scene_architecture(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kicker(layer, t, "03  ·  方案")
    headline(layer, t, "三层，缺一不可", start=0.12)

    rows = [
        ("DeepSeek Harness", "dsh-mcp-client · stdio 行 · serverName: coros", TEXT, CARD_EDGE),
        ("coros-mcp-proxy.js", "100 行 · 零依赖 · 只修 $defs，其余逐字节透传", TEAL, TEAL),
        ("npx mcp-remote@0.14.3", "OAuth 登录 · token 刷新 · 本地缓存", TEXT, CARD_EDGE),
        ("mcpcn.coros.com/mcp", "COROS 官方远程 MCP", TEXT, CARD_EDGE),
    ]
    top, box_h, gap = 314, 100, 40
    for i, (title, sub, color, edge) in enumerate(rows):
        a = alpha_at(t, 0.4 + i * 0.34, 0.4)
        if a <= 0:
            continue
        y = top + i * (box_h + gap)
        layer_rect(
            layer,
            [150, y, 1120, y + box_h],
            14,
            fill=CARD,
            outline=edge,
            width=3 if edge == TEAL else 2,
            alpha=a,
        )
        layer_text(layer, (192, y + 12), title, "h3", color, a)
        layer_text(layer, (192, y + 62), sub, "mono_sm", DIM, a)

        if i < len(rows) - 1:
            a2 = alpha_at(t, 0.62 + i * 0.34, 0.3)
            draw = ImageDraw.Draw(layer)
            x = 635
            draw.line([(x, y + box_h + 6), (x, y + box_h + gap - 8)], fill=(70, 86, 112, int(255 * a2)), width=3)
            draw.polygon(
                [(x - 9, y + box_h + gap - 16), (x + 9, y + box_h + gap - 16), (x, y + box_h + gap - 2)],
                fill=(70, 86, 112, int(255 * a2)),
            )

    a = alpha_at(t, 2.1, 0.45)
    layer_rect(layer, [1210, 316, 1770, 832], 20, fill=CARD, outline=CARD_EDGE, alpha=a)
    layer_text(layer, (1250, 352), "分工不可合并", "small", TEXT, a)
    notes = [
        ("mcp-remote", "解决「怎么登录」"),
        ("proxy", "解决「schema 不合规」"),
        ("代理不碰 token", "不联网 · 不落盘"),
        ("只拦 tools/list", "tools/call 原样透传"),
    ]
    for i, (k, v) in enumerate(notes):
        a2 = alpha_at(t, 2.25 + i * 0.14, 0.35)
        y = 420 + i * 96
        layer_text(layer, (1250, y), k, "mono_sm", TEAL, a2)
        layer_text(layer, (1250, y + 30), v, "small", DIM, a2)

    caption(layer, t, "为什么不做成 DSH 插件？那等于 fork 一份 dsh-mcp-client", DIM, start=3.0, y=888)
    return composite(layer)


def scene_result(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kicker(layer, t, "04  ·  结果")

    a = alpha_at(t, 0.15, 0.5)
    layer_text(layer, (150, 236 + (1 - ease(a)) * 24), "30+", "num", TEAL, a)
    a = alpha_at(t, 0.45, 0.45)
    layer_text(layer, (470, 268 + (1 - ease(a)) * 18), "个原生工具", "h3", TEXT, a)
    layer_text(layer, (470, 322 + (1 - ease(a)) * 18), "查询 · 课表 · 训练计划，读写全通", "body", DIM, a)

    good = [
        "queryUserInfo",
        "queryRecoveryStatus",
        "querySleepOverview",
        "querySportRecords",
        "createScheduledWorkout",
        "updateTrainingPlan",
        "createSingleWorkout",
        "updateWorkoutDetails",
    ]
    for i, name in enumerate(good):
        a2 = alpha_at(t, 0.8 + i * 0.1, 0.35)
        col, row = i // 4, i % 4
        x = 150 + col * 830
        y = 470 + row * 52
        if a2 > 0.02:
            draw = ImageDraw.Draw(layer)
            tick = (GREEN[0], GREEN[1], GREEN[2], int(255 * a2))
            draw.line([(x + 3, y + 14), (x + 10, y + 21)], fill=tick, width=3)
            draw.line([(x + 10, y + 21), (x + 23, y + 5)], fill=tick, width=3)
        layer_text(layer, (x + 36, y), "mcp__coros__" + name, "mono_sm", DIM, a2)

    a = alpha_at(t, 1.6, 0.45)
    layer_text(layer, (150, 686), "从读数据到写课表 —— 只能看的那一半，现在也能改了", "body", FAINT, a)

    a = alpha_at(t, 1.9, 0.45)
    layer_rect(layer, [150, 800, 1770, 810], 4, fill=(38, 53, 78), alpha=a)
    layer_text(layer, (150, 848), "github.com/red-tassel-zhang/dsh-coros-mcp", "mono", TEAL, a)
    a = alpha_at(t, 2.2, 0.45)
    layer_text(layer, (150, 900), "MIT License  ·  issue / PR 都欢迎", "small", FAINT, a)
    return composite(layer)


SCENES = [
    (6.0, scene_title),
    (8.0, scene_symptom),
    (9.0, scene_rootcause),
    (9.0, scene_architecture),
    (8.0, scene_result),
]
XFADE = 0.34


def render(t: float) -> Image.Image:
    starts = []
    acc = 0.0
    for dur, _ in SCENES:
        starts.append(acc)
        acc += dur

    index = 0
    for i, (dur, _) in enumerate(SCENES):
        if starts[i] <= t < starts[i] + dur:
            index = i
            break
    else:
        index = len(SCENES) - 1

    local = t - starts[index]
    frame = SCENES[index][1](local)

    if index > 0 and local < XFADE:
        prev_dur = SCENES[index - 1][0]
        prev = SCENES[index - 1][1](prev_dur - 0.001)
        frame = Image.blend(prev, frame, ease(local / XFADE))

    # 片头淡入 / 片尾淡出
    if t < 0.6:
        frame = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), frame, ease(t / 0.6))
    total = sum(d for d, _ in SCENES)
    if t > total - 0.9:
        frame = Image.blend(frame, Image.new("RGB", (W, H), (0, 0, 0)), ease((t - (total - 0.9)) / 0.9))

    # 进度条
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bar)
    draw.line([(0, H - 4), (W, H - 4)], fill=(255, 255, 255, 16), width=4)
    draw.line([(0, H - 4), (int(W * (t / total)), H - 4)], fill=(45, 212, 191, 150), width=4)
    frame = Image.alpha_composite(frame.convert("RGBA"), bar).convert("RGB")
    return frame


def main() -> int:
    total = sum(d for d, _ in SCENES)
    frames = int(round(total * FPS))
    out = ROOT / "promo.mp4"
    cmd = [
        FFMPEG,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    for i in range(frames):
        t = i / FPS
        frame = render(t)
        proc.stdin.write(frame.tobytes())
        if i % 60 == 0:
            print(f"  frame {i}/{frames}", flush=True)

    proc.stdin.close()
    code = proc.wait()
    if code != 0:
        print(f"ffmpeg exited with {code}", file=sys.stderr)
        return code

    # 封面 + 抽帧检查
    render(3.2).save(ROOT / "cover.png")
    for label, t in (("a", 4.0), ("b", 18.5), ("c", 31.0)):
        render(t).save(ROOT / f"preview_{label}.png")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"done: {out} ({size_mb:.1f} MB, {total:.1f}s, {frames} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
