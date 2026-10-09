"""
Windows 截图实现

依赖: mss, pywin32
"""

from __future__ import annotations

from typing import Optional

import mss
from PIL import Image

from .base import BaseScreenshot, WindowInfo


class Win32Screenshot(BaseScreenshot):
    """Windows 截图实现"""

    def __init__(self) -> None:
        self._mss = mss.mss()

    # ── 全屏 ─────────────────────────────────────────────

    def capture_fullscreen(self, monitor_index: int = 0) -> Image.Image:
        monitors = self._mss.monitors
        # MSS monitors[0] 是虚拟全屏，实际显示器从 1 开始
        # 0 表示使用主显示器（索引 1）
        if monitor_index == 0:
            monitor_index = 1
        if monitor_index < 1 or monitor_index >= len(monitors):
            raise ValueError(
                f"显示器索引 {monitor_index} 超出范围 "
                f"(可用: 1~{len(monitors) - 1})"
            )
        monitor = monitors[monitor_index]
        screenshot = self._mss.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    # ── 区域 ─────────────────────────────────────────────

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        region = {"left": x, "top": y, "width": width, "height": height}
        screenshot = self._mss.grab(region)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    # ── 窗口枚举 ─────────────────────────────────────────

    def list_windows(self) -> list[WindowInfo]:
        return _list_windows_win32()


# ═══════════════════════════════════════════════════════════
# Windows 窗口枚举（Win32 API）
# ═══════════════════════════════════════════════════════════

def _list_windows_win32() -> list[WindowInfo]:
    """通过 Win32 API 获取所有可见窗口"""
    try:
        import win32gui
        import win32con
    except ImportError:
        raise ImportError(
            "Windows 窗口枚举需要 pywin32，请执行: "
            "pip install pywin32"
        )

    results: list[WindowInfo] = []

    def callback(hwnd: int, _extra: None) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True  # 继续枚举

        title = win32gui.GetWindowText(hwnd)
        # 排除没有标题且尺寸为 0 的系统窗口
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True

        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            return True

        # 排除桌面窗口本身
        class_name = win32gui.GetClassName(hwnd)
        if class_name in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return True

        # 排除最小化窗口
        if win32gui.IsIconic(hwnd):
            return True

        results.append(WindowInfo(
            id=hwnd,
            title=title or f"(无标题 - {class_name})",
            x=left,
            y=top,
            width=w,
            height=h,
            is_visible=True,
        ))
        return True

    win32gui.EnumWindows(callback, None)
    return results
