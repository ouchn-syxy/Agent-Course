"""
截图工具包

跨平台（macOS / Windows）屏幕截图工具。

使用方式
--------
>>> from tools.screenshot import create_screenshot_tool
>>> tool = create_screenshot_tool()
>>>
>>> # 全屏截图
>>> img = tool.capture_fullscreen()
>>> tool.save(img)
>>>
>>> # 指定区域截图
>>> img = tool.capture_region(100, 100, 400, 300)
>>>
>>> # 按窗口标题截图
>>> windows = tool.list_windows()
>>> for w in windows:
...     print(w.title)
>>> img = tool.capture_window(title="网店客服工作台")
"""

from .factory import create_screenshot_tool, ScreenshotTool
from .base import BaseScreenshot, WindowInfo

__all__ = [
    "create_screenshot_tool",
    "ScreenshotTool",
    "BaseScreenshot",
    "WindowInfo",
]
