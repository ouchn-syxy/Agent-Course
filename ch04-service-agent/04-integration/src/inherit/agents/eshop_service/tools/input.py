"""键鼠 + 剪贴板操作工具。

所有方法均通过子进程调用 ``tools.input`` CLI。
"""

from __future__ import annotations

import re
import subprocess

from inherit.agents.eshop_service.tools._base import run_tool_cli
from inherit.llm.tool_registry import ToolDef


class Input:

	# ── 鼠标 ──────────────────────────────────────────────

	def click(self, x: int, y: int) -> str:
		"""移动鼠标到 (x, y) 并单击左键。

		Args:
			x: 屏幕绝对 X 坐标（像素）。
			y: 屏幕绝对 Y 坐标（像素）。

		Returns:
			"已点击屏幕坐标 (x, y)" 或错误描述。
		"""
		move_result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "mouse", "move", "--to", str(x), str(y), "-d", "0.15",
		)
		if move_result.returncode != 0:
			return f"鼠标移动失败: {move_result.stderr.strip()}"
		position_match = re.search(
			r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)",
			move_result.stdout,
		)
		if position_match:
			actual_x = float(position_match.group(1))
			actual_y = float(position_match.group(2))
			if abs(actual_x - x) > 10 or abs(actual_y - y) > 10:
				return (
					f"鼠标移动未生效：目标 ({x}, {y})，实际 ({actual_x:.0f}, {actual_y:.0f})。"
					"请在 macOS「隐私与安全性 → 辅助功能」中允许当前终端或代码编辑器控制电脑，"
					"然后重新启动实验；本次不执行点击。"
				)

		click_result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "mouse", "click",
		)
		if click_result.returncode != 0:
			return f"鼠标点击失败: {click_result.stderr.strip()}"

		print(f"🖱️  点击: ({x}, {y})")
		return f"已点击屏幕坐标 ({x}, {y})"


	def scroll(self, dx: int, dy: int) -> str:
		"""滚动鼠标滚轮。

		Args:
			dx: 水平滚动量（通常为 0）。
			dy: 垂直滚动量，正值向下、负值向上。

		Returns:
			"已滚动 dx=X dy=Y" 或错误描述。
		"""
		cli_args: list[str] = []
		if dx:
			cli_args.extend(["--dx", str(dx)])
		if dy:
			cli_args.extend(["--dy", str(dy)])

		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "mouse", "scroll", *cli_args,
		)
		if result.returncode != 0:
			return f"滚轮失败: {result.stderr.strip()}"

		print(f"🔄 滚轮: dx={dx}, dy={dy}")
		return f"已滚动 dx={dx} dy={dy}"


	# ── 键盘 ──────────────────────────────────────────────

	def type(self, text: str) -> str:
		"""模拟键盘逐字键入文本。调用前需先 click 聚焦目标输入框。

		Args:
			text: 要键入的文本内容。

		Returns:
			"已输入文本（N 字）" 或错误描述。
		"""
		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "keyboard", "type", text,
		)
		if result.returncode != 0:
			return f"输入失败: {result.stderr.strip()}"

		preview: str = text[:60] + "..." if len(text) > 60 else text
		print(f"⌨️  输入文本: {preview}")
		return f"已输入文本（{len(text)} 字）"


	# ── 剪贴板 ────────────────────────────────────────────

	def clipboard_write(self, text: str) -> str:
		"""将文本写入系统剪贴板。配合 clipboard_paste 实现大段文本粘贴。

		Args:
			text: 要写入剪贴板的文本。

		Returns:
			"已写入剪贴板（N 字）" 或错误描述。
		"""
		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "clipboard", "write", text,
		)
		if result.returncode != 0:
			return f"写入剪贴板失败: {result.stderr.strip()}"

		preview: str = text[:60] + "..." if len(text) > 60 else text
		print(f"📋 写入剪贴板: {preview}")
		return f"已写入剪贴板（{len(text)} 字）"


	def clipboard_paste(self) -> str:
		"""在光标处粘贴剪贴板内容（Cmd+V / Ctrl+V）。

		Returns:
			"已在光标处粘贴剪贴板内容" 或错误描述。
		"""
		result: subprocess.CompletedProcess[str] = run_tool_cli(
			"input", "clipboard", "paste",
		)
		if result.returncode != 0:
			return f"粘贴失败: {result.stderr.strip()}"

		print("📋 已在光标处粘贴剪贴板内容")
		return "已在光标处粘贴剪贴板内容"


	# ── ToolDef ───────────────────────────────────────────

	def to_tool_defs(self) -> list[ToolDef]:
		return [
			ToolDef(
				name="click",
				description=(
					"在截图指定坐标处点击鼠标左键（截图相对坐标）。点击前确保元素在屏幕上可见。"
				),
				parameters={
					"x": {
						"type": "integer",
						"description": "截图中的归一化 X 坐标，范围 0～1000。",
					},
					"y": {
						"type": "integer",
						"description": "截图中的归一化 Y 坐标，范围 0～1000。",
					},
				},
				required=["x", "y"],
				func=self.click,
			),
			ToolDef(
				name="type",
				description=(
					"在已聚焦的输入框中逐字键入文本。"
					"调用前应先用 click 点击输入框使其获得焦点。"
				),
				parameters={
					"text": {
						"type": "string",
						"description": "要键入的文本内容。",
					},
				},
				required=["text"],
				func=self.type,
			),
			ToolDef(
				name="scroll",
				description=(
					"滚动鼠标滚轮。dy 正值向下、负值向上。"
				),
				parameters={
					"dx": {
						"type": "integer",
						"description": "水平滚动量（通常为 0）。",
						"default": 0,
					},
					"dy": {
						"type": "integer",
						"description": "垂直滚动量，正值向下、负值向上。",
					},
				},
				required=["dy"],
				func=self.scroll,
			),
			ToolDef(
				name="clipboard_write",
				description="将文本写入系统剪贴板。配合 clipboard_paste 使用可实现大段文本快速输入。",
				parameters={
					"text": {
						"type": "string",
						"description": "要写入剪贴板的文本。",
					},
				},
				required=["text"],
				func=self.clipboard_write,
			),
			ToolDef(
				name="clipboard_paste",
				description="在光标处粘贴剪贴板中的文本内容。适合粘贴大段文本（比逐字键入快得多）。",
				parameters={},
				required=[],
				func=self.clipboard_paste,
			),
		]


if __name__ == "__main__":
	print("=" * 60)
	print("  Input 演示")
	print("=" * 60)

	inp = Input()

	# 点击
	print(inp.click(500, 500))

	# 键入
	print(inp.type("Hello, World!"))

	# 滚轮
	print(inp.scroll(0, -3))

	# 剪贴板
	print(inp.clipboard_write("演示剪贴板文本"))
	print(inp.clipboard_paste())
