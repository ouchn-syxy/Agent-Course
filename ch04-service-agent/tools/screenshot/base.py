"""
截图工具抽象基类

定义跨平台统一的截图接口。macOS / Windows 子类各自实现。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class WindowInfo:
    """窗口信息"""
    id: int             # 窗口 ID（系统级句柄）
    title: str          # 窗口标题
    x: int              # 左上角 x
    y: int              # 左上角 y
    width: int          # 宽度
    height: int         # 高度
    is_visible: bool    # 是否可见（未最小化等）


class BaseScreenshot(ABC):
    """截图工具抽象基类"""

    @abstractmethod
    def capture_fullscreen(self, monitor_index: int = 0) -> Image.Image:
        """
        截取整个屏幕

        Args:
            monitor_index: 显示器索引，0 = 主显示器

        Returns:
            PIL Image 对象
        """
        ...

    @abstractmethod
    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """
        截取指定矩形区域

        Args:
            x, y: 区域左上角坐标
            width, height: 区域宽高

        Returns:
            PIL Image 对象
        """
        ...

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        """
        枚举当前所有可见窗口

        Returns:
            WindowInfo 列表，按 z-order 排列
        """
        ...

    def capture_window(
        self,
        *,
        title: Optional[str] = None,
        window_id: Optional[int] = None,
    ) -> Image.Image:
        """
        截取指定窗口

        至少提供 title 或 window_id 之一。

        Args:
            title:    窗口标题（大小写不敏感子串匹配，取首个匹配）
            window_id: 精确窗口 ID

        Returns:
            PIL Image 对象

        Raises:
            ValueError: 找不到匹配窗口
        """
        if window_id is not None:
            target = self._find_by_id(window_id)
        elif title is not None:
            target = self._find_by_title(title)
        else:
            raise ValueError("至少提供 title 或 window_id 之一")

        if target is None:
            identifier = f"id={window_id}" if window_id is not None else f"title='{title}'"
            raise ValueError(f"未找到匹配窗口: {identifier}")

        return self.capture_region(target.x, target.y, target.width, target.height)

    def save(
        self,
        image: Image.Image,
        path: Optional[str] = None,
        prefix: str = "screenshot",
    ) -> str:
        """
        保存截图到文件

        Args:
            image:  PIL Image 对象
            path:   保存路径，为 None 时自动生成时间戳文件名
            prefix: 自动生成文件名时的前缀

        Returns:
            实际保存的文件路径
        """
        from .utils import make_filename

        if path is None:
            path = make_filename(prefix=prefix)

        image.save(path, format="PNG")
        return path

    # ── 内部辅助 ─────────────────────────────────────────

    def _find_by_title(self, title: str) -> Optional[WindowInfo]:
        title_lower = title.lower()
        for win in self.list_windows():
            if win.title and title_lower in win.title.lower():
                return win
        return None

    def _find_by_id(self, window_id: int) -> Optional[WindowInfo]:
        for win in self.list_windows():
            if win.id == window_id:
                return win
        return None
