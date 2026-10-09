"""
鼠标模拟操作

基于 pynput，跨平台（macOS / Windows / Linux）。
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from pynput.mouse import Button, Controller as MouseController

# ── 按钮常量 ─────────────────────────────────────────────

LEFT = Button.left
RIGHT = Button.right
MIDDLE = Button.middle


class Mouse:
    """跨平台鼠标模拟"""

    def __init__(self) -> None:
        self._ctrl = MouseController()

    # ── 位置 ─────────────────────────────────────────────

    @property
    def position(self) -> Tuple[int, int]:
        """获取当前鼠标位置 (x, y)"""
        return self._ctrl.position

    @position.setter
    def position(self, pos: Tuple[int, int]) -> None:
        """设置鼠标位置"""
        self._ctrl.position = pos

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """
        移动鼠标到绝对坐标

        Args:
            x, y:     目标坐标
            duration: 移动耗时（秒），0 表示瞬间移动
        """
        if duration <= 0:
            self._ctrl.position = (x, y)
        else:
            start_x, start_y = self._ctrl.position
            steps = max(1, int(duration * 100))
            for i in range(1, steps + 1):
                t = i / steps
                # ease-out 缓动
                eased = 1 - (1 - t) ** 3
                cur_x = int(start_x + (x - start_x) * eased)
                cur_y = int(start_y + (y - start_y) * eased)
                self._ctrl.position = (cur_x, cur_y)
                time.sleep(duration / steps)

    def move_rel(self, dx: int, dy: int, duration: float = 0.0) -> None:
        """
        相对移动鼠标

        Args:
            dx, dy:   偏移量（像素）
            duration: 移动耗时（秒）
        """
        cur_x, cur_y = self._ctrl.position
        self.move_to(cur_x + dx, cur_y + dy, duration=duration)

    # ── 点击 ─────────────────────────────────────────────

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: Button = LEFT,
        count: int = 1,
    ) -> None:
        """
        点击

        Args:
            x, y:   点击坐标，None 表示在当前位置点击
            button: 鼠标按钮（LEFT / RIGHT / MIDDLE）
            count:  点击次数（1=单击, 2=双击）
        """
        if x is not None and y is not None:
            self._ctrl.position = (x, y)
        self._ctrl.click(button, count)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """双击（左键）"""
        self.click(x, y, count=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """右键单击"""
        self.click(x, y, button=RIGHT)

    def press(self, button: Button = LEFT) -> None:
        """按下鼠标按钮（不释放）"""
        self._ctrl.press(button)

    def release(self, button: Button = LEFT) -> None:
        """释放鼠标按钮"""
        self._ctrl.release(button)

    # ── 拖拽 ─────────────────────────────────────────────

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        button: Button = LEFT,
        duration: float = 0.5,
    ) -> None:
        """
        拖拽：从起点按下 → 移动到终点 → 释放

        Args:
            from_x, from_y: 起点坐标
            to_x, to_y:     终点坐标
            button:         鼠标按钮
            duration:       拖拽耗时（秒）
        """
        self._ctrl.position = (from_x, from_y)
        time.sleep(0.05)
        self._ctrl.press(button)
        self.move_to(to_x, to_y, duration=duration)
        self._ctrl.release(button)

    # ── 滚轮 ─────────────────────────────────────────────

    def scroll(self, dx: int = 0, dy: int = 0) -> None:
        """
        滚动滚轮

        Args:
            dx: 水平滚动（正=右）
            dy: 垂直滚动（正=下，macOS 自然方向）
        """
        self._ctrl.scroll(dx, dy)

    def scroll_up(self, steps: int = 3) -> None:
        """向上滚动"""
        self._ctrl.scroll(0, -steps)

    def scroll_down(self, steps: int = 3) -> None:
        """向下滚动"""
        self._ctrl.scroll(0, steps)
