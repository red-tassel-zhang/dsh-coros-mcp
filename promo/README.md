# promo

推广视频的生成方式 —— 不依赖任何外部素材，改文案重跑就行。

## 成片

| 文件 | 说明 |
|---|---|
| `promo.mp4` | 1920×1080 / 30fps / **2 分 12 秒** / H.264 / 无声 |
| `cover.png` | 封面（标题幕中段），也用作仓库社交预览图 |

这版是**教程视频**，不只是预告：九幕走完 = 一次完整的接入流程。
看视频能装，看 [`../docs/tutorial.md`](../docs/tutorial.md) 能排错。

## 重新生成

```bash
# 需要 Pillow 和 ffmpeg
python promo/make_video.py
```

ffmpeg 默认从 PATH 找；PATH 里没有就用环境变量指定：

```bash
FFMPEG=/path/to/ffmpeg python promo/make_video.py
```

Windows PowerShell 下是 `$env:FFMPEG = 'D:\msys64\mingw64\bin\ffmpeg.exe'`。

帧是直接以 rawvideo 管道喂给 ffmpeg 的，**不落盘**，所以跑完不会留下一堆 PNG。
脚本末尾会额外导出 `cover.png` 和几张 `preview_*.png` 方便肉眼检查排版。

## 为什么是无声的

因为没有任何可自由使用的背景音乐。想加的话在剪映/CapCut 里拖一段就行，
视频本身没有音轨，加音乐不会打架。

## 分镜

| 时间 | 幕 | 内容 |
|---|---|---|
| 0:00–0:07 | 标题 | 把 COROS 官方 MCP 接进 DeepSeek Harness + 九幕目录 |
| 0:07–0:20 | 01 症状 | `Pointer '/$defs/Section' does not exist`，整轮 400；读工具正常、6 个写工具全炸 |
| 0:20–0:35 | 02 根因 | `$defs` 嵌在 `course` 子 schema 里，`$ref` 却写 `#/$defs/Section` 指文档根 |
| 0:35–0:50 | 03 为什么不能直连 | 三层链：DSH → 代理 → `mcp-remote` → `mcpcn.coros.com/mcp`；分工不可合并 |
| 0:50–1:03 | 04 下载 | 两个文件 + raw 直链前缀 |
| 1:03–1:20 | 05 写配置 | 11 行 YAML，高亮 `args` 两行；三个坑（顶层数组 / 路径绝对 / 按区域改 URL） |
| 1:20–1:29 | 06 重启 | 插件树只在启动时结算 —— 刷新页面没用 |
| 1:29–1:43 | 07 验证 | 先单跑 `mcp-remote` 验 OAuth，再确认 `mcp__coros__*` 读工具 + 写工具都在 |
| 1:43–2:00 | 08 排错 | 三个最常见的坑及处理 |
| 2:00–2:12 | 09 收尾 | 仓库地址 + 官方目前不支持 DSH 的说明 |

想改文案，直接搜 `make_video.py` 里对应的 `scene_*` 函数。
所有中文都走微软雅黑、代码走 Consolas；`pick()` 会自动把错用等宽字体的中文切回雅黑
（Consolas 没有汉字字形，会渲染成方框）。
