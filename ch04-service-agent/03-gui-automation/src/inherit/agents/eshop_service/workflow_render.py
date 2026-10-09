"""流程图渲染 — 基于策略配置生成 Mermaid 流程图 DSL。

输出 Mermaid graph TD 格式，可在支持 Mermaid 的 Markdown 编辑器中渲染。
"""

from inherit.agents.eshop_service.message_category_manager import MessageCategoryManager

# 节点颜色列表，按顺序循环使用
_ACTION_COLORS: list[str] = [
	"fill:#e3f2fd,stroke:#2196f3",
	"fill:#e8eaf6,stroke:#3f51b5",
	"fill:#e0f2f1,stroke:#009688",
	"fill:#fce4ec,stroke:#f44336",
	"fill:#f5f5f5,stroke:#9e9e9e",
]


def render_mermaid(mgr: MessageCategoryManager) -> str:
	"""基于 MessageCategoryManager 中的分类与策略配置生成 Mermaid graph TD 流程图。

	:param mgr: 已初始化的 MessageCategoryManager 实例
	:return: Mermaid DSL 文本
	"""

	lines: list[str] = []
	lines.append("```mermaid")
	lines.append("graph TD")
	lines.append("    A[收到客户消息] --> B{消息分类}")

	node_id: int = 1
	hint_to_node: dict[str, str] = {}
	node_styles: dict[str, str] = {}  # node_id → style string
	color_index: int = 0  # 循环取颜色的游标

	for cat in mgr.core_categories:
		cat_name: str = cat.name

		for sub in mgr.sub_categories:
			if sub.parent != cat_name:
				continue
			sub_name: str = sub.name

			hints: list[str] = sub.strategy.action_hints if sub.strategy else []
			response_mode: str = sub.strategy.response_mode if sub.strategy else "auto"

			# 分类节点
			node_id += 1
			class_node: str = f"N{node_id}"
			lines.append(f"    B -->|\"{cat_name} / {sub_name}\"| {class_node}")

			# 按 action_hints 展开节点链
			prev_node: str = class_node
			for hint in hints:
				if hint in hint_to_node:
					current_node: str = hint_to_node[hint]
					lines.append(f"    {prev_node} --> {current_node}")
				else:
					node_id += 1
					current_node = f"N{node_id}"
					hint_to_node[hint] = current_node
					lines.append(f"    {prev_node} --> {current_node}[\"{hint}\"]")

					node_styles[current_node] = _ACTION_COLORS[color_index % len(_ACTION_COLORS)]
					color_index += 1

				prev_node = current_node

			# 转人工分支
			if response_mode in ("human", "auto_with_escalation"):
				node_id += 1
				human_node: str = f"N{node_id}"
				label: str = "转人工处理" if response_mode == "human" else "满足条件时转人工"
				lines.append(f"    {prev_node} --> {human_node}[\"{label}\"]")
				node_styles[human_node] = "fill:#fce4ec,stroke:#f44336"

	# 追加节点样式声明
	for nid, style in node_styles.items():
		lines.append(f"    style {nid} {style}")

	lines.append("```")
	return "\n".join(lines)


# ──────────────────────────────────────────────
# 简易演示：直接运行本文件即可预览流程图
# ──────────────────────────────────────────────
if __name__ == "__main__":
	import re

	from inherit.utils.path import get_prj_root

	proj_root = get_prj_root()
	mgr = MessageCategoryManager(proj_root / "data" / "eshop_service" / "message_category")
	mermaid: str = render_mermaid(mgr)

	lines_list: list[str] = mermaid.split("\n")
	# 从所有行中提取 node ID（格式: N数字）
	node_ids: set[str] = set()
	for line in lines_list:
		node_ids.update(re.findall(r'\b(N\d+)\b', line))
	edge_count: int = sum(1 for l in lines_list if "-->" in l)

	print("📊 流程图统计")
	print(f"   节点数: {len(node_ids)} (含 A, B)")
	print(f"   边数:   {edge_count}")
	print()

	print(mermaid)
