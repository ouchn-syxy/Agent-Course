"""
截图工具命令行接口

用法
----
    python -m tools.screenshot fullscreen
    python -m tools.screenshot region 100 200 400 300
    python -m tools.screenshot window --title "Chrome"
    python -m tools.screenshot window --id 12345
    python -m tools.screenshot list-windows
    python -m tools.screenshot list-windows --filter "Chrome"

全局选项
--------
    -o, --output <path>   指定输出路径（默认自动生成时间戳文件名）
    -p, --prefix <str>    文件名前缀（默认 screenshot）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .factory import create_screenshot_tool


def cmd_fullscreen(args: argparse.Namespace) -> None:
    tool = create_screenshot_tool()
    img = tool.capture_fullscreen(monitor_index=args.monitor)
    out = tool.save(img, path=args.output, prefix=args.prefix)
    print(f"全屏截图已保存: {out}  ({img.size[0]}x{img.size[1]})")


def cmd_region(args: argparse.Namespace) -> None:
    tool = create_screenshot_tool()
    img = tool.capture_region(args.x, args.y, args.width, args.height)
    out = tool.save(img, path=args.output, prefix=args.prefix)
    print(f"区域截图已保存: {out}  ({img.size[0]}x{img.size[1]})")


def cmd_window(args: argparse.Namespace) -> None:
    tool = create_screenshot_tool()
    img = tool.capture_window(title=args.title, window_id=args.id)
    out = tool.save(img, path=args.output, prefix=args.prefix)
    print(f"窗口截图已保存: {out}  ({img.size[0]}x{img.size[1]})")


def cmd_list_windows(args: argparse.Namespace) -> None:
    tool = create_screenshot_tool()
    windows = tool.list_windows()

    if args.filter:
        keyword = args.filter.lower()
        windows = [w for w in windows if keyword in w.title.lower()]

    if not windows:
        print("(无匹配窗口)")
        return

    # 列宽
    id_w = max(len(str(w.id)) for w in windows) + 2
    for w in windows:
        geo = f"({w.x},{w.y}) {w.width}x{w.height}"
        print(f"[{w.id:>{id_w}}]  {w.title[:60]:60s}  {geo}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screenshot",
        description="跨平台屏幕截图工具（macOS / Windows）",
    )
    sub = parser.add_subparsers(dest="command")

    # ── fullscreen ──────────────────────────────────────
    p_full = sub.add_parser("fullscreen", help="全屏截图")
    p_full.add_argument(
        "-m", "--monitor", type=int, default=0,
        help="显示器索引（0=主显示器，默认 0）",
    )

    # ── region ──────────────────────────────────────────
    p_region = sub.add_parser("region", help="区域截图")
    p_region.add_argument("x", type=int, help="左上角 X 坐标")
    p_region.add_argument("y", type=int, help="左上角 Y 坐标")
    p_region.add_argument("width", type=int, help="宽度（像素）")
    p_region.add_argument("height", type=int, help="高度（像素）")

    # ── window ──────────────────────────────────────────
    p_win = sub.add_parser("window", help="按标题或 ID 截取窗口")
    group = p_win.add_mutually_exclusive_group(required=True)
    group.add_argument("--title", "-t", type=str, help="窗口标题（子串匹配）")
    group.add_argument("--id", type=int, help="窗口 ID")

    # ── list-windows ────────────────────────────────────
    p_list = sub.add_parser("list-windows", help="列出所有可见窗口")
    p_list.add_argument(
        "--filter", "-f", type=str,
        help="过滤标题（大小写不敏感子串匹配）",
    )

    # ── 全局选项 ────────────────────────────────────────
    for p in [p_full, p_region, p_win]:
        p.add_argument("--output", "-o", type=str, default=None, help="输出文件路径")
        p.add_argument("--prefix", "-p", type=str, default="screenshot", help="文件名前缀")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "fullscreen": cmd_fullscreen,
        "region": cmd_region,
        "window": cmd_window,
        "list-windows": cmd_list_windows,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except (ImportError, ValueError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(130)


if __name__ == "__main__":
    main()
