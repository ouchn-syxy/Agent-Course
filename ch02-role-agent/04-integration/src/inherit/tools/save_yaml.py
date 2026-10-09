"""
通用 YAML 保存工具。

接收字典数据，序列化为 YAML 写入文件。
不耦合任何具体数据模型——save() 接受 dict 直接写入。
"""

from pathlib import Path
from typing import Any

import yaml

from inherit.llm.tool_registry import ToolDef


class SaveYaml:
	"""通用 YAML 保存器，将 dict 序列化为 YAML 文件。

	用法：
		saver = SaveYaml(output_dir=Path("output"))
		result = saver.save(name="鲁迅", data={"name": "鲁迅", "era": "...", ...})
	"""


	def __init__(self, output_dir: Path) -> None:
		"""
		Args:
			output_dir: YAML 文件输出目录。
		"""
		self._output_dir: Path = Path(output_dir)
		self._output_dir.mkdir(parents=True, exist_ok=True)


	def save(self, name: str, data: dict[str, Any]) -> str:
		"""将 dict 序列化为 YAML 并写入文件。

		Args:
			name: 文件名（不含扩展名），如 "鲁迅"。
			data: 待保存的字典数据。

		Returns:
			保存结果信息。
		"""
		filepath = self._output_dir / f"{name}.yaml"
		yaml_body = yaml.dump(
			data,
			allow_unicode=True,
			default_flow_style=False,
			sort_keys=False,
		)
		header = f"# {name} 数据定义\n# 由 Agent 自动生成\n\n"
		filepath.write_text(header + yaml_body, encoding="utf-8")

		return f"✅ 已保存到: {filepath}"


	def to_tool_def(self) -> ToolDef:
		"""生成此工具的 ToolDef 注册描述。"""
		return ToolDef(
			name="save_yaml",
			description="将数据对象保存为 YAML 文件。",
			parameters={
				"name": {
					"type": "string",
					"description": "文件名（不含扩展名）",
				},
				"data": {
					"type": "object",
					"description": "待保存的数据对象",
				},
			},
			required=["name", "data"],
			func=self.save,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  SaveYaml 演示")
	print("=" * 60)

	saver = SaveYaml(output_dir=Path("output"))
	r = saver.save(name="鲁迅", data={"name": "鲁迅", "era": "晚清至民国（1881-1936）"})
	print(r)
