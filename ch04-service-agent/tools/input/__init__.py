"""
输入模拟工具包

跨平台（macOS / Windows / Linux）键盘鼠标模拟工具。

使用方式
--------
>>> from tools.input import Mouse, Keyboard, Clipboard
>>>
>>> # 鼠标
>>> m = Mouse()
>>> m.move_to(100, 200)
>>> m.click()
>>> m.double_click(x=300, y=400)
>>> m.drag(100, 100, 500, 500)
>>> m.scroll_up(3)
>>> print(m.position)  # (x, y)
>>>
>>> # 键盘
>>> kb = Keyboard()
>>> kb.type("hello")
>>> kb.tap(Key.enter)
>>> kb.hotkey("cmd", "c")   # macOS 复制
>>> kb.hotkey("ctrl", "v")  # Windows 粘贴
>>>
>>> # 剪切板
>>> cb = Clipboard()
>>> cb.write("要粘贴的文本")
>>> cb.paste()             # 读取剪切板，逐字键入到光标处
>>> text = cb.read()       # 读取剪切板内容
"""

from .mouse import Mouse, LEFT, RIGHT, MIDDLE
from .keyboard import Keyboard, Key
from .clipboard import Clipboard

# 键盘方向键（避免与鼠标按钮冲突，加 ARROW_ 前缀）
from .keyboard import (
    ENTER, TAB, SPACE, ESC, BACKSPACE, DELETE,
    SHIFT, CTRL, ALT, CMD,
    UP, DOWN,
    HOME, END, PAGE_UP, PAGE_DOWN,
    F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
)

ARROW_LEFT = Key.left
ARROW_RIGHT = Key.right
ARROW_UP = UP
ARROW_DOWN = DOWN

__all__ = [
    "Mouse", "Keyboard", "Clipboard", "Key",
    "LEFT", "RIGHT", "MIDDLE",
    "ENTER", "TAB", "SPACE", "ESC", "BACKSPACE", "DELETE",
    "SHIFT", "CTRL", "ALT", "CMD",
    "ARROW_UP", "ARROW_DOWN", "ARROW_LEFT", "ARROW_RIGHT",
    "HOME", "END", "PAGE_UP", "PAGE_DOWN",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
]
