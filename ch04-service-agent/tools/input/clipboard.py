"""
剪切板读写操作

基于 pyperclip 实现跨平台剪切板访问，配合 Keyboard 实现光标处粘贴。
"""

from __future__ import annotations

from typing import Optional

import pyperclip


class Clipboard:
    """跨平台剪切板操作"""

    def __init__(self, keyboard: Optional["Keyboard"] = None) -> None:
        """
        Args:
            keyboard: 可选，Keyboard 实例，用于 paste()。
                      不传则 paste() 时自动创建。
        """
        self._kb = keyboard

    def _ensure_keyboard(self) -> "Keyboard":
        if self._kb is None:
            from .keyboard import Keyboard
            self._kb = Keyboard()
        return self._kb

    # ── 读 ─────────────────────────────────────────────────

    def read(self) -> str:
        """读取剪切板中的文本内容"""
        return pyperclip.paste()

    # ── 写 ─────────────────────────────────────────────────

    def write(self, text: str) -> None:
        """将文本写入剪切板"""
        pyperclip.copy(text)

    # ── 粘贴 ───────────────────────────────────────────────

    def paste(self) -> None:
        """
        在光标处粘贴剪切板内容

        通过系统快捷键（macOS: Cmd+V / 其他: Ctrl+V）直接粘贴，
        避免逐字键入导致的长文本超时或截断问题。
        """
        import platform
        if platform.system() == "Darwin":
            self._ensure_keyboard().hotkey("cmd", "v")
        else:
            self._ensure_keyboard().hotkey("ctrl", "v")
