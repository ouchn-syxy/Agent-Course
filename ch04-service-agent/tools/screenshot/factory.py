"""
平台自动检测工厂

根据当前操作系统返回对应的 ScreenshotTool 实例。
"""

from __future__ import annotations

import sys

from .base import BaseScreenshot


def create_screenshot_tool() -> BaseScreenshot:
    """
    自动检测当前平台，返回合适的截图工具实例

    Returns:
        DarwinScreenshot (macOS) 或 Win32Screenshot (Windows)

    Raises:
        RuntimeError: 当前平台不受支持
    """
    if sys.platform == "darwin":
        from .platform_darwin import DarwinScreenshot
        return DarwinScreenshot()

    if sys.platform == "win32":
        from .platform_win32 import Win32Screenshot
        return Win32Screenshot()

    raise RuntimeError(
        f"不支持的平台: {sys.platform}。"
        f"当前仅支持 macOS (darwin) 和 Windows (win32)。"
    )


# 模块级便捷别名
ScreenshotTool = create_screenshot_tool
