"""
macOS 截图实现

依赖: mss, PyObjC (Quartz)
"""

from __future__ import annotations

from typing import Optional

import mss
from PIL import Image

from .base import BaseScreenshot, WindowInfo


class DarwinScreenshot(BaseScreenshot):
    """macOS 截图实现"""

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
        return _list_windows_darwin()


# ═══════════════════════════════════════════════════════════
# macOS 窗口枚举（CoreGraphics / Quartz）
# ═══════════════════════════════════════════════════════════

def _list_windows_darwin() -> list[WindowInfo]:
    """通过 Quartz 获取所有窗口信息"""
    try:
        import Quartz
    except ImportError:
        raise ImportError(
            "macOS 窗口枚举需要 PyObjC，请执行: "
            "pip install pyobjc-framework-Quartz"
        )

    results: list[WindowInfo] = []
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )

    for entry in window_list:
        owner = entry.get(Quartz.kCGWindowOwnerName, "")
        name = entry.get(Quartz.kCGWindowName, "")
        # 构造可读标题: "应用名 - 窗口名"
        title = f"{owner} - {name}" if name else str(owner)

        # 窗口 ID（32 位有符号，转为无符号 int）
        wid = entry.get(Quartz.kCGWindowNumber, 0)

        bounds = entry.get(Quartz.kCGWindowBounds, {})
        x = int(bounds.get("X", 0))
        y = int(bounds.get("Y", 0))
        w = int(bounds.get("Width", 0))
        h = int(bounds.get("Height", 0))

        # 过滤掉无效窗口（宽高为 0）
        if w <= 0 or h <= 0:
            continue

        # 排除菜单栏、Dock 等系统 UI
        layer = entry.get(Quartz.kCGWindowLayer, 0)
        if layer > 1000:  # 通常 Dock 层 >= 1000, 菜单栏 1000+
            continue

        results.append(WindowInfo(
            id=wid,
            title=title,
            x=x,
            y=y,
            width=w,
            height=h,
            is_visible=True,
        ))

    return results
