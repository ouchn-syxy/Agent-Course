"""
输入模拟工具 CLI

用法
----
    # 鼠标
    python -m tools.input mouse pos                     # 获取当前位置
    python -m tools.input mouse move --to 100 200       # 移动到目标
    python -m tools.input mouse move --rel 50 -30       # 相对移动
    python -m tools.input mouse click                   # 当前位置点击
    python -m tools.input mouse click --pos 300 400     # 指定坐标点击
    python -m tools.input mouse dclick --pos 300 400    # 双击
    python -m tools.input mouse rclick --pos 300 400    # 右键
    python -m tools.input mouse drag 100 100 500 500    # 拖拽
    python -m tools.input mouse scroll --dy -3          # 向上滚动

    # 键盘
    python -m tools.input keyboard type "hello"          # 输入文本
    python -m tools.input keyboard tap enter             # 按键
    python -m tools.input keyboard hotkey cmd c          # 组合键

全局选项
--------
    -d, --duration <秒>   动作耗时（仅移动/拖拽，默认无延时）
"""

from __future__ import annotations

import argparse
import sys


def cmd_mouse_pos(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    x, y = m.position
    print(f"鼠标位置: ({x}, {y})")


def cmd_mouse_move(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    if args.to:
        m.move_to(args.to[0], args.to[1], duration=args.duration)
    elif args.rel:
        m.move_rel(args.rel[0], args.rel[1], duration=args.duration)
    x, y = m.position
    print(f"已移动至: ({x}, {y})")


def cmd_mouse_click(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    x = args.pos[0] if args.pos else None
    y = args.pos[1] if args.pos else None
    m.click(x, y)
    if x is not None:
        print(f"已单击: ({x}, {y})")
    else:
        print(f"已单击当前位置")


def cmd_mouse_double_click(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    x = args.pos[0] if args.pos else None
    y = args.pos[1] if args.pos else None
    m.double_click(x, y)
    if x is not None:
        print(f"已双击: ({x}, {y})")
    else:
        print("已双击当前位置")


def cmd_mouse_right_click(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    x = args.pos[0] if args.pos else None
    y = args.pos[1] if args.pos else None
    m.right_click(x, y)
    if x is not None:
        print(f"已右键: ({x}, {y})")
    else:
        print("已右键当前位置")


def cmd_mouse_drag(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    m.drag(
        args.from_[0], args.from_[1],
        args.to[0], args.to[1],
        duration=args.duration,
    )
    print(f"已拖拽: ({args.from_[0]},{args.from_[1]}) → ({args.to[0]},{args.to[1]})")


def cmd_mouse_scroll(args: argparse.Namespace) -> None:
    from .mouse import Mouse
    m = Mouse()
    m.scroll(dx=args.dx or 0, dy=args.dy or 0)
    direction = ""
    if args.dy:
        direction = "下" if args.dy > 0 else "上"
    elif args.dx:
        direction = "右" if args.dx > 0 else "左"
    print(f"已滚动: {direction} {abs(args.dx or args.dy)} 步")


def cmd_keyboard_type(args: argparse.Namespace) -> None:
    from .keyboard import Keyboard
    kb = Keyboard()
    kb.type(args.text)
    print(f"已输入: '{args.text}'")


def cmd_keyboard_tap(args: argparse.Namespace) -> None:
    from .keyboard import Keyboard
    kb = Keyboard()
    key = kb._resolve_key(args.key)
    kb.tap(key)
    print(f"已按键: {args.key}")


def cmd_keyboard_hotkey(args: argparse.Namespace) -> None:
    from .keyboard import Keyboard
    kb = Keyboard()
    kb.hotkey(*args.keys)
    print(f"已按组合键: {'+'.join(args.keys)}")


def cmd_clipboard_read(args: argparse.Namespace) -> None:
    from .clipboard import Clipboard
    c = Clipboard()
    text = c.read()
    print(text)


def cmd_clipboard_write(args: argparse.Namespace) -> None:
    from .clipboard import Clipboard
    c = Clipboard()
    c.write(args.text)
    print(f"已写入剪切板: '{args.text}'")


def cmd_clipboard_paste(args: argparse.Namespace) -> None:
    from .clipboard import Clipboard
    c = Clipboard()
    c.paste()
    print("已在光标处粘贴剪切板内容")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="input",
        description="跨平台键盘鼠标模拟工具（macOS / Windows）",
    )
    sub = parser.add_subparsers(dest="device")

    # ═══════════════════════════════════════════════════════
    # 鼠标
    # ═══════════════════════════════════════════════════════
    p_mouse = sub.add_parser("mouse", help="鼠标操作")
    m_sub = p_mouse.add_subparsers(dest="action")

    p_pos = m_sub.add_parser("pos", help="获取鼠标当前位置")

    p_move = m_sub.add_parser("move", help="移动鼠标")
    group = p_move.add_mutually_exclusive_group(required=True)
    group.add_argument("--to", type=int, nargs=2, metavar=("X", "Y"), help="绝对坐标")
    group.add_argument("--rel", type=int, nargs=2, metavar=("DX", "DY"), help="相对位移")
    p_move.add_argument("-d", "--duration", type=float, default=0.0, help="移动耗时（秒）")

    p_click = m_sub.add_parser("click", help="单击（左键）")
    p_click.add_argument("--pos", type=int, nargs=2, metavar=("X", "Y"), help="点击坐标")

    p_dclick = m_sub.add_parser("dclick", help="双击（左键）")
    p_dclick.add_argument("--pos", type=int, nargs=2, metavar=("X", "Y"), help="点击坐标")

    p_rclick = m_sub.add_parser("rclick", help="右键单击")
    p_rclick.add_argument("--pos", type=int, nargs=2, metavar=("X", "Y"), help="点击坐标")

    p_drag = m_sub.add_parser("drag", help="拖拽")
    p_drag.add_argument("from_", type=int, nargs=2, metavar=("FROM_X", "FROM_Y"), help="起点坐标")
    p_drag.add_argument("to", type=int, nargs=2, metavar=("TO_X", "TO_Y"), help="终点坐标")
    p_drag.add_argument("-d", "--duration", type=float, default=0.5, help="拖拽耗时（秒）")

    p_scroll = m_sub.add_parser("scroll", help="滚轮滚动")
    p_scroll.add_argument("--dx", type=int, default=None, help="水平滚动步数")
    p_scroll.add_argument("--dy", type=int, default=None, help="垂直滚动步数")

    # ═══════════════════════════════════════════════════════
    # 键盘
    # ═══════════════════════════════════════════════════════
    p_kb = sub.add_parser("keyboard", help="键盘操作")
    k_sub = p_kb.add_subparsers(dest="action")

    p_type = k_sub.add_parser("type", help="输入文本")
    p_type.add_argument("text", type=str, help="要输入的文本")

    p_tap = k_sub.add_parser("tap", help="按下单个键")
    p_tap.add_argument("key", type=str, help="键名（如 enter / esc / tab / a）")

    p_hotkey = k_sub.add_parser("hotkey", help="按下组合键")
    p_hotkey.add_argument("keys", type=str, nargs="+", help="组合键序列（如 cmd c / ctrl v）")

    # ═══════════════════════════════════════════════════════
    # 剪切板
    # ═══════════════════════════════════════════════════════
    p_cb = sub.add_parser("clipboard", help="剪切板操作")
    cb_sub = p_cb.add_subparsers(dest="action")

    cb_read = cb_sub.add_parser("read", help="读取剪切板内容")
    cb_write = cb_sub.add_parser("write", help="写入文本到剪切板")
    cb_write.add_argument("text", type=str, help="要写入的文本")
    cb_paste = cb_sub.add_parser("paste", help="在光标处粘贴剪切板内容")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.device is None:
        parser.print_help()
        sys.exit(1)

    handlers: dict[str, dict[str, callable]] = {
        "mouse": {
            "pos": cmd_mouse_pos,
            "move": cmd_mouse_move,
            "click": cmd_mouse_click,
            "dclick": cmd_mouse_double_click,
            "rclick": cmd_mouse_right_click,
            "drag": cmd_mouse_drag,
            "scroll": cmd_mouse_scroll,
        },
        "keyboard": {
            "type": cmd_keyboard_type,
            "tap": cmd_keyboard_tap,
            "hotkey": cmd_keyboard_hotkey,
        },
        "clipboard": {
            "read": cmd_clipboard_read,
            "write": cmd_clipboard_write,
            "paste": cmd_clipboard_paste,
        },
    }

    handler = handlers.get(args.device, {}).get(args.action)
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
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
