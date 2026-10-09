"""等待工具。

纯时延操作，无需调用外部 CLI，直接 ``time.sleep``。
"""

from __future__ import annotations

import time

from inherit.llm.tool_registry import ToolDef


class Wait:
	"""等待指定秒数。

	用法：
		w = Wait()
		result = w.wait(1.5)
	"""


	def wait(self, seconds: float) -> str:
		"""等待指定秒数（用于界面加载 / 动画完成）。

		Args:
			seconds: 等待秒数。

		Returns:
			执行结果描述字符串。
		"""
		print(f"⏳ 等待 {seconds:.1f}s...")
		time.sleep(seconds)
		return f"已等待 {seconds} 秒"


	def to_tool_def(self) -> ToolDef:
		return ToolDef(
			name="wait",
			description=(
				"等待指定秒数。用于：页面加载、动画完成、"
				"等待消息发送后的界面刷新等场景。"
			),
			parameters={
				"seconds": {
					"type": "number",
					"description": "等待秒数，默认 1.0。",
					"default": 1.0,
				},
			},
			required=[],
			func=self.wait,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  Wait 演示")
	print("=" * 60)

	w = Wait()
	print(w.wait(1.0))
	print(w.wait(0.5))
