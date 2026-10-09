"""窗口操作工具 — 查找窗口 + 截屏。

两个方法都通过子进程调用 ``tools.screenshot`` CLI。
所有方法均为无状态纯函数，不维护任何中间状态。
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from inherit.agents.eshop_service.tools._base import run_tool_cli
from inherit.llm.tool_registry import ToolDef


class WindowInfo(BaseModel):
	"""窗口元信息 — find() 的返回值。"""

	window_id: int = Field(description="操作系统窗口 ID")
	title: str = Field(description="窗口标题栏文本")
	x: int = Field(description="窗口左上角屏幕 X 坐标")
	y: int = Field(description="窗口左上角屏幕 Y 坐标")
	width: int = Field(description="窗口宽度（像素）")
	height: int = Field(description="窗口高度（像素）")


class ScreenshotResult(BaseModel):
	"""截图结果 — screenshot() 的返回值。"""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	file_path: str = Field(description="截图文件的绝对路径")
	width: int = Field(description="截图宽度（像素）")
	height: int = Field(description="截图高度（像素）")
	image: Image.Image = Field(description="截图 PIL Image 对象（仅内存使用，不参与序列化）", exclude=True)


class Window:
	"""无状态窗口操作工具。

	所有方法均为纯函数，不维护任何实例状态。
	截图文件统一保存到构造时指定的缓存目录。

	使用方式：
		w = Window(Path("/tmp/screenshots"))
		info = w.find("Chrome")
		result = w.screenshot(info.window_id)
	"""


	def __init__(self, cache_dir: Path) -> None:
		"""初始化窗口工具。

		Args:
			cache_dir: 截图缓存目录，不存在时自动创建。
		"""
		self._cache_dir: Path = cache_dir
		self._cache_dir.mkdir(parents=True, exist_ok=True)


	# ── 公开方法 ──────────────────────────────────────────

	def find(self, keyword: str = "网店客服工作台") -> WindowInfo:
		"""查找标题包含 keyword 的窗口。

		Args:
			keyword: 窗口标题关键词。默认使用业务页面标题，避免多个 Chrome 窗口时选错。

		Returns:
			WindowInfo: 窗口元信息。

		Raises:
			ValueError: 未找到匹配窗口或 CLI 执行失败。
		"""
		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"screenshot", "list-windows", "--filter", keyword,
		)
		if result.returncode != 0:
			raise ValueError(f"列出窗口失败: {result.stderr.strip()}")

		output: str = result.stdout.strip()
		if not output or "(无匹配窗口)" in output:
			raise ValueError(f"未找到 {keyword} 窗口")

		for line in output.splitlines():
			match: re.Match[str] | None = re.match(
				r"\[\s*(\d+)]\s+(.+?)\s{2,}\((-?\d+),(-?\d+)\)\s+(\d+)x(\d+)",
				line.strip(),
			)
			if match:
				info = WindowInfo(
					window_id=int(match.group(1)),
					title=match.group(2).strip(),
					x=int(match.group(3)),
					y=int(match.group(4)),
					width=int(match.group(5)),
					height=int(match.group(6)),
				)
				print(
					f"✅ 找到 {keyword} 窗口: {info.title} "
					f"({info.width}x{info.height}"
					f" @ ({info.x}, {info.y}))"
				)
				return info

		raise ValueError(f"未找到 {keyword} 窗口")


	def activate(self, app_name: str = "Google Chrome") -> None:
		"""将已打开的 Chrome 置于前台，并验证前台应用确实已经切换。

		macOS 的区域截图会采集屏幕当前可见内容；如果 VS Code 或终端盖在
		Chrome 上方，即使按窗口标题找到了 Chrome，得到的图片仍可能是被遮挡
		的内容。因此每次识别或执行前必须先激活 Chrome。
		"""
		script = f'''
tell application "{app_name}" to activate
delay 0.3
tell application "System Events"
	set frontmost of process "{app_name}" to true
	delay 0.2
	set frontApp to name of first application process whose frontmost is true
end tell
return frontApp
'''
		result: subprocess.CompletedProcess[str] = subprocess.run(
			["osascript", "-e", script],
			capture_output=True,
			text=True,
			check=False,
		)
		if result.returncode != 0:
			raise RuntimeError(f"无法将 {app_name} 置于前台: {result.stderr.strip()}")
		front_app = result.stdout.strip()
		if front_app != app_name:
			raise RuntimeError(f"前台应用仍是 {front_app or '未知应用'}，不是 {app_name}")
		print(f"✅ 已确认 {app_name} 位于最前台，准备查找工作台窗口")


	def screenshot(self, window_id: int, filename: str | None = None) -> ScreenshotResult:
		"""截取指定窗口，保存到缓存目录。

		Args:
			window_id: 操作系统窗口 ID。
			filename: 输出文件名（不含路径），None 时自动生成时间戳文件名。

		Returns:
			ScreenshotResult: 含截图路径和尺寸。

		Raises:
			RuntimeError: 截图 CLI 执行失败。
		"""
		if filename is None:
			filename = f"screenshot_{int(time.time() * 1000)}.png"
		output_path: Path = self._cache_dir / filename

		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"screenshot",
			"window", "--id", str(window_id),
			"-o", str(output_path),
		)
		if result.returncode != 0:
			raise RuntimeError(f"截图失败: {result.stderr.strip()}")

		img: Image.Image = Image.open(output_path)
		img.load()

		screenshot_result = ScreenshotResult(
			file_path=str(output_path.resolve()),
			width=img.width,
			height=img.height,
			image=img,
		)
		print(f"📸 截图完成: {img.width}x{img.height} → {output_path.name}")
		return screenshot_result


	# ── ToolDef ───────────────────────────────────────────

	def to_tool_defs(self) -> list[ToolDef]:
		return [
			ToolDef(
				name="find_window",
				description=(
					"按标题关键词查找窗口，返回窗口 ID、标题、大小和屏幕位置。"
					"通常作为 GUI 操作的第一步调用。"
				),
				parameters={
					"keyword": {
						"type": "string",
						"description": "窗口标题关键词，用于筛选目标窗口。",
					},
				},
				required=[],
				func=self.find,
			),
			ToolDef(
				name="screenshot",
				description=(
					"截取指定窗口的屏幕截图，保存到缓存目录。"
					"返回截图文件路径和尺寸。"
				),
				parameters={
					"window_id": {
						"type": "integer",
						"description": "要截图的窗口 ID。",
					},
				},
				required=["window_id"],
				func=self.screenshot,
			),
		]


if __name__ == "__main__":
	print("=" * 60)
	print("  Window 演示")
	print("=" * 60)

	w = Window(Path(tempfile.gettempdir()) / "gui_automation_screenshots")

	# 查找窗口
	try:
		info = w.find()
		print(info.model_dump_json(indent=2))

		# 截图
		result = w.screenshot(info.window_id)
		print(result.model_dump_json(indent=2))
	except (ValueError, RuntimeError) as e:
		print(f"❌ {e}")
