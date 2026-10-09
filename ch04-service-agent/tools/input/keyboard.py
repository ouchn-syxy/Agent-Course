"""
键盘模拟操作

基于 pynput，跨平台（macOS / Windows / Linux）。
"""

from __future__ import annotations

from typing import Optional

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key

# ── 常用键导出 ──────────────────────────────────────────

ENTER = Key.enter
TAB = Key.tab
SPACE = Key.space
ESC = Key.esc
BACKSPACE = Key.backspace
DELETE = Key.delete
SHIFT = Key.shift
CTRL = Key.ctrl
ALT = Key.alt
CMD = Key.cmd         # macOS Command / Windows Win 键
UP = Key.up
DOWN = Key.down
LEFT = Key.left
RIGHT = Key.right
HOME = Key.home
END = Key.end
PAGE_UP = Key.page_up
PAGE_DOWN = Key.page_down
F1 = Key.f1
F2 = Key.f2
F3 = Key.f3
F4 = Key.f4
F5 = Key.f5
F6 = Key.f6
F7 = Key.f7
F8 = Key.f8
F9 = Key.f9
F10 = Key.f10
F11 = Key.f11
F12 = Key.f12

# ── 组合键分隔符 ─────────────────────────────────────────
# 在 hotkey 中使用，例如 "cmd+c", "ctrl+v", "alt+tab"


class Keyboard:
    """跨平台键盘模拟"""

    def __init__(self) -> None:
        self._ctrl = KeyboardController()

    # ── 单键 ─────────────────────────────────────────────

    def press(self, key: str | Key) -> None:
        """按下按键（不释放）"""
        self._ctrl.press(key)

    def release(self, key: str | Key) -> None:
        """释放按键"""
        self._ctrl.release(key)

    def tap(self, key: str | Key) -> None:
        """按下并释放（单击一次）"""
        self._ctrl.tap(key)

    # ── 文本输入 ─────────────────────────────────────────

    def type(self, text: str, interval: float = 0.0) -> None:
        """
        逐字输入文本

        Args:
            text:     要输入的文本
            interval: 每个字符之间的间隔（秒）
        """
        if interval > 0:
            import time
            for ch in text:
                self._ctrl.press(ch)
                self._ctrl.release(ch)
                time.sleep(interval)
        else:
            self._ctrl.type(text)

    # ── 组合键 ───────────────────────────────────────────

    # ── 组合键名映射 ─────────────────────────────────────
    _MODIFIER_MAP: dict[str, str | Key] = {
        "cmd": Key.cmd,
        "command": Key.cmd,
        "ctrl": Key.ctrl,
        "control": Key.ctrl,
        "alt": Key.alt,
        "option": Key.alt,
        "shift": Key.shift,
        "tab": Key.tab,
        "enter": Key.enter,
        "space": Key.space,
        "esc": Key.esc,
        "backspace": Key.backspace,
        "delete": Key.delete,
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right,
        "home": Key.home,
        "end": Key.end,
        "pageup": Key.page_up,
        "pagedown": Key.page_down,
        **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},
    }

    def _resolve_key(self, name: str) -> str | Key:
        """将键名字符串解析为 pynput Key 或普通字符"""
        lowered = name.lower()
        if lowered in self._MODIFIER_MAP:
            return self._MODIFIER_MAP[lowered]
        if len(name) == 1:
            return name
        raise ValueError(f"无法识别的键名: '{name}'，请使用单字符或已知键名")

    def hotkey(self, *keys: str, interval: float = 0.1) -> None:
        """
        按下组合键

        用法:
            kb.hotkey("cmd", "c")        # macOS 复制
            kb.hotkey("ctrl", "v")       # Windows 粘贴
            kb.hotkey("alt", "tab")      # 切换窗口

        Args:
            *keys:    按键序列（同时按下的键）
            interval: 按下到释放之间的间隔（秒）
        """
        import time

        resolved = [self._resolve_key(k) for k in keys]
        for key in resolved:
            self._ctrl.press(key)
        time.sleep(interval)
        for key in reversed(resolved):
            self._ctrl.release(key)
