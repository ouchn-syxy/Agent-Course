"""
Tool Registry — 工具注册、Schema 生成与执行框架。

手动实现 OpenAI Function Calling 的工具管理，不依赖 LangChain。
以 ToolDef 数据类描述工具，注册中心围绕 ToolDef 完成注册→Schema→执行。

用法：
    from tool_registry import ToolRegistry, ToolDef

    registry = ToolRegistry()
    registry.register(ToolDef(
        name="web_search",
        description="搜索互联网获取人物资料",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "最大结果数", "default": 5},
        },
        required=["query"],
        func=web_search,
    ))
    # LLM 调用时：
    tools = registry.get_tools_schema()
    # 解析 LLM 返回的 tool_calls 后：
    result = registry.execute("web_search", {"query": "鲁迅"})
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from openai.types.chat import ChatCompletionToolParam


@dataclass
class ToolDef:
	"""工具定义：元数据 + 可调用对象 + OpenAI Schema 转换。"""

	name: str
	description: str
	parameters: dict[str, Any]
	func: Callable[..., Any]
	required: list[str] = field(default_factory=list)


	def to_openai_tool(self) -> ChatCompletionToolParam:
		"""转为 OpenAI Function Calling 的 tool 格式。"""
		return {
			"type": "function",
			"function": {
				"name": self.name,
				"description": self.description,
				"parameters": {
					"type": "object",
					"properties": self.parameters,
					"required": self.required,
				},
			},
		}


class ToolRegistry:
	"""工具注册中心，以 ToolDef 描述工具，管理完整的工具生命周期。

	设计要点：
	  - register(ToolDef) 注册，学生可看清每一步
	  - get_tools_schema() 调用 ToolDef.to_openai_tool() 输出 OpenAI 格式
	  - execute() 将 LLM 返回的 arguments JSON 字符串解析后传给工具函数
	  - list() 返回所有已注册的 ToolDef 对象
	"""


	def __init__(self) -> None:
		"""初始化空的工具注册表。"""
		self._tools: dict[str, ToolDef] = {}


	def register(self, tool: ToolDef) -> None:
		"""注册一个工具。

		Args:
			tool: ToolDef 实例。

		Raises:
			ValueError: 工具名已注册。
		"""
		if tool.name in self._tools:
			raise ValueError(f"工具 '{tool.name}' 已注册，请使用不同的名称。")
		self._tools[tool.name] = tool


	def execute(self, tool_name: str, **kwargs: Any) -> str:
		"""执行指定工具并返回结果字符串。

		Args:
			tool_name: 工具名称。
			**kwargs: 工具参数，按参数名展开传入。

		Returns:
			工具执行结果字符串。
		"""
		tool = self._tools.get(tool_name)
		if tool is None:
			return f"错误：未找到工具 '{tool_name}'。可用工具：{', '.join(self._tools.keys())}"

		try:
			result = tool.func(**kwargs)
		except TypeError as e:
			return f"参数错误：{e}。请检查参数名和类型是否正确。"
		except Exception as e:
			return f"工具执行异常：{type(e).__name__}: {e}"

		# 将结果统一为字符串
		if isinstance(result, str):
			return result
		if isinstance(result, (list, dict)):
			return json.dumps(result, ensure_ascii=False, indent=2)
		return str(result)


	def list(self) -> list[ToolDef]:
		"""返回所有已注册工具。"""
		return list(self._tools.values())


if __name__ == "__main__":

	def _greet(name: str) -> str:
		"""打招呼。"""
		return f"你好，{name}！"


	def _add(a: int, b: int) -> int:
		"""两数相加。"""
		return a + b


	def _list_status() -> list[str]:
		"""返回状态列表。"""
		return ["在线", "忙碌", "离线"]


	print("=" * 60)
	print("  ToolRegistry + ToolDef 完整演示")
	print("=" * 60)

	# ── 1. ToolDef 构造 & to_openai_tool() ──
	print("\n📦 1. ToolDef 构造 & to_openai_tool()")
	td = ToolDef(
		name="greet",
		description="向某人打招呼",
		parameters={
			"name": {"type": "string", "description": "对方的名字"},
		},
		required=["name"],
		func=_greet,
	)
	print(f"   name: {td.name}")
	print(f"   to_openai_tool():")
	print(f"   {json.dumps(td.to_openai_tool(), ensure_ascii=False, indent=6)}")

	# ── 2. 注册工具 ──
	print("\n📦 2. register()")
	registry = ToolRegistry()
	registry.register(td)
	registry.register(ToolDef(
		name="add",
		description="计算两数之和",
		parameters={
			"a": {"type": "integer", "description": "第一个加数"},
			"b": {"type": "integer", "description": "第二个加数"},
		},
		required=["a", "b"],
		func=_add,
	))
	registry.register(ToolDef(
		name="list_status",
		description="查看在线状态列表",
		parameters={},
		func=_list_status,
	))
	print("   ✅ 注册 greet / add / list_status 三个工具")

	# ── 3. 重复注册 ──
	print("\n📦 3. 重复注册（应报错）")
	try:
		registry.register(td)
	except ValueError as e:
		print(f"   ✅ ValueError: {e}")

	# ── 4. execute() — 各场景 ──
	print("\n📦 5. execute()")

	# 字符串返回值
	print(f"   5a. greet(name='世界'): {registry.execute('greet', name='世界')}")

	# 整数返回值 → 自动转字符串
	print(f"   5b. add(a=3, b=5): {registry.execute('add', a=3, b=5)}")

	# 列表返回值 → 自动转 JSON
	print(f"   5c. list_status(): {registry.execute('list_status')}")

	# 缺少参数
	print(f"   5d. add(a=3)（缺 b）: {registry.execute('add', a=3)}")

	# 未知工具
	print(f"   5e. 未知工具: {registry.execute('unknown')}")

	# ── 5. list() ──
	print("\n📦 6. list()")
	print(", ".join([t.name for t in registry.list()]))

	# ── 6. 空 registry ──
	print("📦 7. 空 registry")
	empty = ToolRegistry()
	print(f"   list() 数量: {len(empty.list())}")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
