# media

推广视频的生成方式 —— 不依赖任何外部素材，改文案重跑就行。

## 成片

| 文件 | 说明 |
|---|---|
| `promo.mp4` | 1920×1080 / 30fps / 40s / H.264 / 无声 |
| `cover.png` | 封面（第一幕中段），也用作仓库社交预览图 |

## 重新生成

```bash
python media/make_promo.py
```

需要 Pillow 和 ffmpeg。ffmpeg 默认从 PATH 找，也可以用环境变量指定：

```bash
FFMPEG=/path/to/ffmpeg python media/make_promo.py
```

帧是直接以 rawvideo 管道喂给 ffmpeg 的，**不落盘**，所以跑完不会留下一堆 PNG。
脚本末尾会额外导出 `cover.png` 和几张 `preview_*.png` 方便肉眼检查排版。

## 为什么是无声的

因为没有任何可自由使用的背景音乐。想加的话在剪映/CapCut 里拖一段就行，
视频本身没有音轨，加音乐不会打架。

## 分镜

| 时间 | 内容 |
|---|---|
| 0–6s | 标题：把 COROS 官方 MCP 接进 DeepSeek Harness |
| 6–14s | 症状：`Pointer '/$defs/Section' does not exist`，整轮 400 |
| 14–23s | 根因：`$defs` 嵌在子 schema 里，`$ref` 却指文档根 |
| 23–32s | 方案：三层链路，以及为什么不做成插件 |
| 32–40s | 结果：30+ 工具读写全通 + 仓库地址 |

想改文案，直接搜 `make_promo.py` 里对应的 `scene_*` 函数。
所有中文都走微软雅黑、代码走 Consolas；`has_cjk()` 会自动把错用等宽字体的中文切回雅黑
（Consolas 没有汉字字形，会渲染成方框）。
