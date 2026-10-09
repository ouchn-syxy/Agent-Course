"""
通用辅助函数
"""

from datetime import datetime
from pathlib import Path


def make_filename(prefix: str = "screenshot") -> str:
    """
    生成带时间戳的截图文件名
    例如: screenshot_20260716_143052.png

    Returns:
        绝对路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 输出到 tools/screenshot/output/ 目录
    base = Path(__file__).resolve().parent / "output"
    out_dir = base
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir / f"{prefix}_{timestamp}.png")
