#!/usr/bin/env python
"""生成「COROS MCP × DeepSeek Harness」接入教程视频（约 2 分 12 秒，无声）。

产物（都在 promo/ 下）：
    promo.mp4        1920×1080 / 30fps / H.264
    cover.png        封面（第一幕中段），也用作仓库社交预览图
    preview_*.png    抽帧，方便肉眼检查排版

用法：
    python promo/make_video.py
    FFMPEG=/path/to/ffmpeg python promo/make_video.py

设计原则：不依赖任何外部素材，全部用 PIL 画；改文案直接改下面的 scene_* 函数。
中文走微软雅黑、代码走 Consolas —— Consolas 没有汉字字形，混排会自动切回雅黑。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
ROOT = Path(__file__).resolve().parent
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

BG_TOP = (11, 18, 32)
BG_BOTTOM = (7, 11, 21)
INK = (233, 239, 247)
DIM = (138, 152, 175)
FAINT = (86, 100, 122)
TEAL = (45, 212, 191)
AMBER = (251, 191, 36)
GREEN = (74, 222, 128)
RED = (248, 113, 113)

F_CN = r"C:\Windows\Fonts\msyh.ttc"
F_CN_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
F_MONO = r"C:\Windows\Fonts\consola.ttf"
F_MONO_BOLD = r"C:\Windows\Fonts\consolab.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=0)


FONTS = {
    "h1": _font(F_CN_BOLD, 70),
    "h2": _font(F_CN_BOLD, 52),
    "h3": _font(F_CN_BOLD, 34),
    "body": _font(F_CN, 29),
    "small": _font(F_CN, 24),
    "cn_sm": _font(F_CN, 22),
    "kicker_cn": _font(F_CN_BOLD, 26),
    "kicker": _font(F_MONO_BOLD, 26),
    "mono": _font(F_MONO, 24),
    "mono_sm": _font(F_MONO, 21),
    "code": _font(F_MONO, 23),
    "code_sm": _font(F_MONO, 20),
    "big": _font(F_CN_BOLD, 96),
}

# Consolas 没有汉字字形，混排会渲染成方框 —— 这些等宽样式遇到 CJK 要换雅黑
MONO_FALLBACK = {
    "mono": "small",
    "mono_sm": "cn_sm",
    "code": "small",
    "code_sm": "cn_sm",
    "kicker": "kicker_cn",
}


def is_cjk(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f" for c in s)


def pick(style: str, s: str) -> ImageFont.FreeTypeFont:
    if is_cjk(s) and style in MONO_FALLBACK:
        return FONTS[MONO_FALLBACK[style]]
    return FONTS[style]


# ---------------------------------------------------------------- 画布与基础件

_BG: Image.Image | None = None


def background() -> Image.Image:
    global _BG
    if _BG is not None:
        return _BG
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / (H - 1)
        d.line([(0, y), (W, y)], fill=(
            int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * k),
            int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * k),
            int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * k),
        ))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W - 760, -420, W + 260, 520], fill=(22, 78, 82))
    glow = glow.filter(ImageFilter.GaussianBlur(190))
    img = Image.blend(img, glow, 0.22)
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 60):
        gd.line([(x, 0), (x, H)], fill=(255, 255, 255, 5))
    for y in range(0, H, 60):
        gd.line([(0, y), (W, y)], fill=(255, 255, 255, 5))
    _BG = Image.alpha_composite(img.convert("RGBA"), grid).convert("RGB")
    return _BG


def alpha_at(t: float, start: float, dur: float = 0.4) -> float:
    if t <= start:
        return 0.0
    return min(1.0, (t - start) / dur)


def text(ov: ImageDraw.ImageDraw, xy, s: str, style="body", color=INK, a=1.0):
    if a <= 0.01 or not s:
        return
    ov.text(xy, s, font=pick(style, s), fill=(color[0], color[1], color[2], int(255 * a)))


def wrap(s: str, style: str, width: float) -> list[str]:
    f = pick(style, s)
    out, cur = [], ""
    for ch in s:
        if f.getlength(cur + ch) > width and cur:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return out


def panel(ov, box, a=1.0, fill=(255, 255, 255, 10), outline=(255, 255, 255, 30), r=14):
    if a <= 0.01:
        return
    ov.rounded_rectangle(
        box, radius=r,
        fill=(fill[0], fill[1], fill[2], int(fill[3] * a)),
        outline=(outline[0], outline[1], outline[2], int(outline[3] * a)),
        width=2,
    )


def code_block(ov, x, y, lines, width, a=1.0, size="code", pad=26, lead=1.55, highlight=(), hl_color=TEAL):
    """ov 是 RGBA 图层；lines: [(text, color)]；highlight: 要高亮的行号集合。返回块高度。"""
    dr = ImageDraw.Draw(ov)
    lh = int(FONTS[size].size * lead)
    height = pad * 2 + lh * len(lines)
    panel(dr, [x, y, x + width, y + height], a=a, fill=(6, 10, 18, 200), outline=(255, 255, 255, 26))
    for i, (s, color) in enumerate(lines):
        ly = y + pad + i * lh
        if i in highlight:
            dr.rounded_rectangle([x + 10, ly - 5, x + width - 10, ly + lh - 6], radius=8,
                                 fill=(hl_color[0], hl_color[1], hl_color[2], int(26 * a)))
            dr.rectangle([x + 10, ly - 5, x + 15, ly + lh - 6],
                         fill=(hl_color[0], hl_color[1], hl_color[2], int(215 * a)))
        text(dr, (x + pad, ly), s, size, color, a)
    return height


def chrome(ov, idx: int, total: int, kicker: str, a=1.0):
    text(ov, (150, 128), kicker, "kicker_cn" if is_cjk(kicker) else "kicker", AMBER, a)
    text(ov, (W - 246, 132), f"{idx:02d} / {total:02d}", "kicker", FAINT, a)


def tick(ov, x, y, color, a=1.0):
    c = (color[0], color[1], color[2], int(255 * a))
    ov.line([(x + 3, y + 16), (x + 10, y + 23)], fill=c, width=3)
    ov.line([(x + 10, y + 23), (x + 23, y + 7)], fill=c, width=3)


# ---------------------------------------------------------------- 各幕


def scene_title(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    a = alpha_at(t, 0.1, 0.5)
    text(d, (150, 296), "TUTORIAL  ·  约 2 分钟装完", "kicker", TEAL, a)
    a = alpha_at(t, 0.3, 0.6)
    text(d, (150, 368), "把 COROS 官方 MCP", "h1", INK, a)
    text(d, (150, 454), "接进 DeepSeek Harness", "h1", INK, a)
    a = alpha_at(t, 0.9, 0.5)
    d.rounded_rectangle([150, 566, 660, 572], radius=3, fill=(TEAL[0], TEAL[1], TEAL[2], int(230 * a)))
    text(d, (150, 608), "一个 $defs 引发的血案，和 100 行补丁", "h3", AMBER, a)
    a = alpha_at(t, 1.4, 0.6)
    for i, line in enumerate([
        "01 症状   02 根因   03 为什么不能直连   04 下载",
        "05 写配置   06 重启   07 验证   08 排错   09 收尾",
    ]):
        text(d, (150, 700 + i * 46), line, "body", DIM, a)
    a = alpha_at(t, 2.2, 0.6)
    text(d, (150, 906), "github.com/red-tassel-zhang/dsh-coros-mcp", "mono", TEAL, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_symptom(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 1, 9, "01 · 症状")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "整轮对话直接 400", "h2", INK, a)
    text(d, (150, 268), "不是某个工具不可用 —— 是这一批 tools 全部没发出去", "body", DIM, a)

    a = alpha_at(t, 0.8)
    code_block(ov, 150, 348, [
        ("> 本轮运行失败", FAINT),
        ("", INK),
        ("Invalid schema for function", DIM),
        ("  'mcp__coros__createScheduledWorkout':", DIM),
        ("", INK),
        ("Pointer '/$defs/Section' does not exist", RED),
    ], 1140, a=a, size="mono")

    a = alpha_at(t, 1.8)
    panel(d, [150, 640, 1770, 880], a=a, fill=(255, 255, 255, 6))
    text(d, (190, 672), "受影响的是 6 个写工具，读工具全都正常", "h3", AMBER, a)
    for i, name in enumerate([
        "createScheduledWorkout", "updateScheduledWorkout", "createTrainingPlan",
        "updateTrainingPlan", "createSingleWorkout", "updateWorkoutDetails",
    ]):
        col, row = i // 2, i % 2
        text(d, (196 + col * 560, 742 + row * 42), "· " + name, "mono_sm", DIM, a)
    text(d, (150, 940), "所以现象是：看数据没事，一让他做课表就整轮报错。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_rootcause(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 2, 9, "02 · 根因")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "$defs 的位置和 $ref 的指法对不上", "h2", INK, a)
    text(d, (150, 268), "定义嵌在子 schema 里，引用却从文档根开始找", "body", DIM, a)

    a = alpha_at(t, 0.7)
    code_block(ov, 150, 340, [
        ('{ "type": "object",', DIM),
        ('  "properties": {', DIM),
        ('    "course": {', DIM),
        ('      "$defs": { "Section": { ... } },', AMBER),
        ('      "properties": {', DIM),
        ('        "sections": { "items": {', DIM),
        ('          "$ref": "#/$defs/Section"', RED),
        ('        }', DIM),
        ('      }', DIM),
        ('    }', DIM),
        ('  }', DIM),
        ('}', DIM),
    ], 880, a=a, size="code_sm", highlight=(3, 6))

    a = alpha_at(t, 1.6)
    panel(d, [1090, 340, 1770, 612], a=a, fill=(255, 255, 255, 8))
    for i, (head, body) in enumerate([
        ("← 定义在这里", "$defs 写在 course 这个子 schema 内部"),
        ("← 却从文档根找", "# 表示文档根，根上没有 $defs"),
    ]):
        y = 376 + i * 112
        text(d, (1126, y), head, "h3", TEAL if i == 0 else RED, a)
        for j, ln in enumerate(wrap(body, "cn_sm", 590)):
            text(d, (1126, y + 44 + j * 32), ln, "cn_sm", DIM, a)

    a = alpha_at(t, 2.2)
    text(d, (150, 790), "指针解析失败 → 模型侧认为整批 tools 不合法 → 这一轮全部拒绝。", "body", DIM, a)
    text(d, (150, 842), "服务端短期不会改，所以只能在我们这侧补。", "body", DIM, a)
    a = alpha_at(t, 3.0)
    text(d, (150, 916), "补法：把子 schema 里的 $defs 提升到文档根，$ref 就能正确解析。", "body", TEAL, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_why(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 3, 9, "03 · 为什么不能直连")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "两层，缺一不可", "h2", INK, a)
    text(d, (150, 268), "鉴权是一层，schema 是另一层，正好各缺一半", "body", DIM, a)

    chain = [
        ("DeepSeek Harness", "dsh-mcp-client · stdio · serverName: coros", INK),
        ("coros-mcp-proxy.js", "只改 $defs，其余逐字节透传", TEAL),
        ("npx mcp-remote@0.14.3", "OAuth 登录 · token 刷新 · 本地缓存", INK),
        ("mcpcn.coros.com/mcp", "COROS 官方远程 MCP", INK),
    ]
    for i, (title, sub, color) in enumerate(chain):
        a2 = alpha_at(t, 0.5 + i * 0.28)
        y = 342 + i * 126
        hot = i == 1
        panel(d, [150, y, 1060, y + 94], a=a2,
              fill=(45, 212, 191, 18) if hot else (255, 255, 255, 8),
              outline=(45, 212, 191, 130) if hot else (255, 255, 255, 30))
        text(d, (188, y + 12), title, "h3", color, a2)
        text(d, (188, y + 56), sub, "small", DIM, a2)
        if i < len(chain) - 1:
            d.line([(600, y + 96), (600, y + 124)], fill=(255, 255, 255, int(60 * a2)), width=3)

    a = alpha_at(t, 1.7)
    panel(d, [1130, 342, 1770, 806], a=a, fill=(255, 255, 255, 6))
    text(d, (1168, 374), "分工不可合并", "h3", INK, a)
    for i, (head, body, color) in enumerate([
        ("mcp-remote", "dsh-mcp-client 只支持 stdio 与\nstreamable-http，后者只能加静态\nheaders，没有 OAuth 流程", TEAL),
        ("代理", "服务端返回的 inputSchema 不合规，\n需要在到达模型之前把它改好", AMBER),
    ]):
        y = 442 + i * 190
        text(d, (1168, y), head, "mono", color, a)
        for j, ln in enumerate(body.split("\n")):
            text(d, (1168, y + 38 + j * 32), ln, "cn_sm", DIM, a)
    text(d, (150, 862), "两者串成一个 stdio 命令，就是下一步要写的两行 args。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_download(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 4, 9, "04 · 下载")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "只要两个文件，不用 clone", "h2", INK, a)
    text(d, (150, 268), "浏览器打开直链 Ctrl+S 存下来；不用 npm install", "body", DIM, a)

    for i, (name, desc, color) in enumerate([
        ("coros-mcp-proxy.js", "唯一要下载的代码 · 7 KB · 零依赖 · 单文件", TEAL),
        ("cordis.patch.yml", "合并进 profile 的配置片段 · 0.7 KB", AMBER),
    ]):
        a2 = alpha_at(t, 0.5 + i * 0.3)
        y = 352 + i * 148
        panel(d, [150, y, 1770, y + 118], a=a2, fill=(255, 255, 255, 8),
              outline=(color[0], color[1], color[2], 70))
        text(d, (192, y + 16), name, "mono", color, a2)
        text(d, (192, y + 60), desc, "small", DIM, a2)
        text(d, (1560, y + 28), "Raw →", "mono_sm", FAINT, a2)

    a = alpha_at(t, 1.4)
    text(d, (150, 682), "直链前缀（后面接上面两个文件名）：", "small", FAINT, a)
    code_block(ov, 150, 722, [
        ("https://raw.githubusercontent.com/", DIM),
        ("  red-tassel-zhang/dsh-coros-mcp/main/", TEAL),
    ], 1080, a=a, size="mono_sm")
    a = alpha_at(t, 2.2)
    text(d, (150, 908), "代理放哪都行，建议 ~/.dsh/coros-proxy/ —— 不会被清理，也方便升级替换。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_config(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 5, 9, "05 · 写配置")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "把两行 args 写进 profile", "h2", INK, a)
    text(d, (150, 272), "<DSH_HOME>/profiles/<profile>/cordis.patch.yml", "mono_sm", TEAL, a)

    a = alpha_at(t, 0.5)
    code_block(ov, 150, 324, [
        ("- insert:", DIM),
        ("    - id: mcp-coros", DIM),
        ("      name: '@deepseek-ai/dsh-mcp-client'", DIM),
        ("      config:", DIM),
        ("        serverName: coros", INK),
        ("        transport: stdio", INK),
        ("        command: node", INK),
        ("        args:", INK),
        ("          - '<绝对路径>/coros-mcp-proxy.js'", GREEN),
        ("          - 'https://mcpcn.coros.com/mcp'", GREEN),
        ("        toolCallTimeoutMs: 120000", INK),
    ], 980, a=a, size="code", highlight=(8, 9))

    a = alpha_at(t, 1.5)
    panel(d, [1170, 312, 1770, 700], a=a, fill=(255, 255, 255, 6))
    for i, (head, body) in enumerate([
        ("顶层是数组", "每项都以 - 开头；已有内容\n就把这段插进去，别覆盖"),
        ("路径要绝对", "相对路径在子进程里解析不了；\nWindows 上 command 建议写 node.exe"),
        ("按区域改 URL", "mcpcn / mcpeu / mcpus 三个入口\n按账号所在区域选一个"),
    ]):
        y = 346 + i * 120
        text(d, (1206, y), head, "h3", TEAL, a)
        for j, ln in enumerate(body.split("\n")):
            text(d, (1206, y + 42 + j * 30), ln, "cn_sm", DIM, a)
    text(d, (150, 906), "改完保存，别急着重载插件 —— 下一步是重启。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_restart(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 6, 9, "06 · 重启")
    a = alpha_at(t, 0.2, 0.5)
    text(d, (150, 330), "重启 DSH", "big", INK, a)
    a = alpha_at(t, 0.9)
    text(d, (150, 476), "插件树只在启动时结算 —— 刷新页面没用。", "h3", AMBER, a)
    a = alpha_at(t, 1.6)
    text(d, (150, 566), "很多人卡在这一步：改完 yml、按了 Ctrl+R、发现工具还是没出现，", "body", DIM, a)
    text(d, (150, 616), "于是回去翻配置 —— 其实只差一次完整重启。", "body", DIM, a)
    a = alpha_at(t, 2.4)
    text(d, (150, 762), "重启后，工具会以 mcp__coros__<tool> 的名字出现在模型侧。", "body", TEAL, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_verify(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 7, 9, "07 · 验证")
    a = alpha_at(t, 0.15)
    text(d, (150, 196), "先单独验 OAuth，再看工具", "h2", INK, a)
    text(d, (150, 268), "把代理摘掉跑一次，能登录就说明鉴权这层没问题", "body", DIM, a)

    a = alpha_at(t, 0.5)
    code_block(ov, 150, 338, [
        ("npx -y mcp-remote@0.14.3 https://mcpcn.coros.com/mcp", INK),
    ], 1180, a=a, size="mono_sm")

    a = alpha_at(t, 1.1)
    text(d, (150, 424), "成功时 stderr 会打印：", "small", FAINT, a)
    for i, ln in enumerate(wrap(
        "Proxy established successfully between local STDIO and remote StreamableHTTPClientTransport",
        "mono_sm", 1120,
    )):
        text(d, (150, 462 + i * 32), ln, "mono_sm", GREEN, a)

    a = alpha_at(t, 1.9)
    text(d, (150, 556), "然后确认工具真的进来了：", "small", FAINT, a)
    for i, (name, color) in enumerate([
        ("queryUserInfo", GREEN), ("querySportRecords", GREEN),
        ("querySleepOverview", GREEN), ("queryRecoveryStatus", GREEN),
        ("createScheduledWorkout", TEAL), ("updateWorkoutDetails", TEAL),
    ]):
        col, row = i % 2, i // 2
        x, y = 150 + col * 820, 598 + row * 46
        a2 = alpha_at(t, 1.9 + i * 0.08)
        tick(d, x, y, color, a2)
        text(d, (x + 38, y), "mcp__coros__" + name, "mono_sm", DIM, a2)

    a = alpha_at(t, 2.6)
    text(d, (150, 830), "绿勾是读、青勾是写 —— 写工具能出现，说明 6 个坏 schema 已经修好。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_trouble(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 8, 9, "08 · 排错")
    a = alpha_at(t, 0.15)
    text(d, (150, 178), "三个最常见的坑", "h2", INK, a)

    for i, (sym, cause, fix, color) in enumerate([
        ("Pointer '/$defs/Section' does not exist", "代理没在链路上",
         "确认 args 第一项指向 coros-mcp-proxy.js", RED),
        ("工具列表里没有 mcp__coros__*", "没登录 / 行没生效 / 启动失败",
         "单跑一次 mcp-remote 确认登录，再重启", AMBER),
        ("spawn npx ENOENT / EINVAL", "Windows 上 npx 解析到无扩展名脚本",
         "代理已内置解析，或用 MCP_REMOTE_NPX_CLI 指定", AMBER),
    ]):
        a2 = alpha_at(t, 0.5 + i * 0.35)
        y = 274 + i * 208
        panel(d, [150, y, 1770, y + 176], a=a2, fill=(255, 255, 255, 7),
              outline=(color[0], color[1], color[2], 60))
        text(d, (190, y + 18), sym, "mono_sm", color, a2)
        text(d, (190, y + 60), "原因 · " + cause, "cn_sm", DIM, a2)
        for j, ln in enumerate(wrap("处理 · " + fix, "cn_sm", 1480)):
            text(d, (190, y + 98 + j * 30), ln, "cn_sm", INK, a2)

    a = alpha_at(t, 1.8)
    text(d, (150, 926), "完整排错表在 docs/tutorial.md，还带回滚步骤。", "body", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def scene_outro(t: float) -> Image.Image:
    img = background().copy()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    chrome(d, 9, 9, "09 · 收尾")
    a = alpha_at(t, 0.2, 0.5)
    text(d, (150, 262), "30+ 个工具，读写全通", "h1", INK, a)
    a = alpha_at(t, 0.8)
    text(d, (150, 382), "改的只是一个 100 行的代理，其余都是官方能力。", "body", DIM, a)

    a = alpha_at(t, 1.3)
    text(d, (150, 500), "github.com/red-tassel-zhang/dsh-coros-mcp", "h3", TEAL, a)
    a = alpha_at(t, 1.9)
    for i, ln in enumerate([
        "官方只支持 ChatGPT / Codex / Claude / OpenClaw / WorkBuddy；",
        "DeepSeek Harness 不在列表里 —— 所以才有这个仓库。",
    ]):
        text(d, (150, 592 + i * 46), ln, "body", DIM, a)
    a = alpha_at(t, 2.6)
    text(d, (150, 764), "MIT  ·  issue / PR 都欢迎  ·  详细步骤见 docs/tutorial.md", "small", FAINT, a)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


SCENES = [
    (7.0, scene_title),
    (13.0, scene_symptom),
    (15.0, scene_rootcause),
    (15.0, scene_why),
    (13.0, scene_download),
    (17.0, scene_config),
    (9.0, scene_restart),
    (14.0, scene_verify),
    (17.0, scene_trouble),
    (12.0, scene_outro),
]
XFADE = 0.34


def render(t: float) -> Image.Image:
    starts, acc = [], 0.0
    for dur, _ in SCENES:
        starts.append(acc)
        acc += dur

    idx = len(SCENES) - 1
    for i, (dur, _) in enumerate(SCENES):
        if starts[i] <= t < starts[i] + dur:
            idx = i
            break

    frame = SCENES[idx][1](t - starts[idx])

    if idx > 0 and (t - starts[idx]) < XFADE:
        prev_dur = SCENES[idx - 1][0]
        prev = SCENES[idx - 1][1](prev_dur - XFADE + (t - starts[idx]))
        frame = Image.blend(prev, frame, (t - starts[idx]) / XFADE)

    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    bd.line([(0, H - 4), (W, H - 4)], fill=(255, 255, 255, 16), width=4)
    bd.line([(0, H - 4), (int(W * (t / acc)), H - 4)], fill=(45, 212, 191, 150), width=4)
    return Image.alpha_composite(frame.convert("RGBA"), bar).convert("RGB")


def main() -> int:
    total = sum(d for d, _ in SCENES)
    frames = int(round(total * FPS))
    out = ROOT / "promo.mp4"
    print(f"total {total:.1f}s / {frames} frames -> {out}", flush=True)
    cmd = [
        FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(frames):
        proc.stdin.write(render(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"  frame {i}/{frames}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")

    render(3.4).save(ROOT / "cover.png")
    for name, at in [("preview_symptom", 12.0), ("preview_config", 70.0),
                     ("preview_verify", 96.0), ("preview_trouble", 110.0)]:
        render(at).save(ROOT / f"{name}.png")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
