"""路径工具 — 提供项目根目录的获取方法。

职责：统一管理项目内路径解析逻辑，避免各处重复实现。
"""

from pathlib import Path


def get_cwd() -> Path:
	"""返回工作目录的绝对路径。

	通过当前文件所在位置往上两级定位到工作目录：
	   path.py → utils/ → src/

	:return: 工作目录（src/）的 Path 对象
	"""
	return Path(__file__).parent.parent.parent.resolve()


def get_prj_root() -> Path:
	"""返回小章节根目录（项目根）的绝对路径。

	通过当前文件所在位置往上三级定位到项目根：
	   path.py → utils/ → src/ → 小章节/

	:return: 小章节根目录的 Path 对象
	"""
	return Path(__file__).parent.parent.parent.parent.resolve()
