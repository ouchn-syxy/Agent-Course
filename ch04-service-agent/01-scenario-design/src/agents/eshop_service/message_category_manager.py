"""消息分类管理器 — 加载并查询 core.json + sub.json，被 message_classifier 和 strategy_engine 共用。"""

import json
from pathlib import Path
from typing import Optional

from agents.eshop_service.models.types import MessageCoreCategory, MessageSubCategory


class MessageCategoryManager:
	"""消息分类配置的唯一读取入口。

	core.json 定义大类（name / description），
	sub.json 定义子类（name / parent / description / 策略规则）。

	使用示例::

		from agents.eshop_service.message_category_manager import MessageCategoryManager

		mgr = MessageCategoryManager(Path("data/eshop_service/message_category"))
		core = mgr.find_core("售前咨询")
		sub = mgr.find_sub("退货退款", "售后服务")
	"""


	def __init__(self, category_dir: Path) -> None:
		"""初始化并立即加载所有分类配置。

		:param category_dir: 包含 core.json 与 sub.json 的目录路径
		:raises FileNotFoundError: 任一 JSON 文件不存在时抛出
		"""
		core_path: Path = category_dir / "core.json"
		subs_path: Path = category_dir / "sub.json"
		if not core_path.exists():
			raise FileNotFoundError(f"大类配置文件不存在: {core_path}")
		if not subs_path.exists():
			raise FileNotFoundError(f"子类配置文件不存在: {subs_path}")
		with open(core_path, encoding="utf-8") as f:
			raw_core: list[dict] = json.load(f)
		with open(subs_path, encoding="utf-8") as f:
			raw_subs: list[dict] = json.load(f)
		self._core: list[MessageCoreCategory] = [MessageCoreCategory(**entry) for entry in raw_core]
		self._subs: list[MessageSubCategory] = [MessageSubCategory(**entry) for entry in raw_subs]


	# ── 属性 ─────────────────────────────────────────────

	@property
	def core_categories(self) -> list[MessageCoreCategory]:
		"""所有大类列表（副本，不可直接修改内部状态）。

		:return: MessageCoreCategory 列表
		"""
		return list(self._core)


	@property
	def sub_categories(self) -> list[MessageSubCategory]:
		"""所有子类列表（副本，不可直接修改内部状态）。

		:return: MessageSubCategory 列表
		"""
		return list(self._subs)


	# ── 查找 ─────────────────────────────────────────────

	def find_core(self, name: str) -> Optional[MessageCoreCategory]:
		"""按大类名称精确查找，返回副本以防外部误改内部状态。

		:param name: 大类名称（如 "售前咨询"）
		:return: 匹配的 MessageCoreCategory 副本，不存在则返回 None
		"""
		for entry in self._core:
			if entry.name == name:
				return entry.model_copy()
		return None


	def find_sub(self, name: str, parent: str) -> Optional[MessageSubCategory]:
		"""按子类名称 + 所属大类查找，返回副本以防外部误改内部状态。

		:param name: 子类名称（如 "退货退款"）
		:param parent: 所属大类名称（如 "售后服务"）
		:return: 匹配的 MessageSubCategory 副本（含策略规则），不存在则返回 None
		"""
		for entry in self._subs:
			if entry.name == name and entry.parent == parent:
				return entry.model_copy()
		return None


	def subs_of(self, parent: str) -> list[MessageSubCategory]:
		"""获取某大类下的所有子类，返回副本列表以防外部误改内部状态。

		:param parent: 大类名称（如 "售后服务"）
		:return: MessageSubCategory 副本列表，该大类无子类时返回空列表
		"""
		return [e.model_copy() for e in self._subs if e.parent == parent]


	# ── 查询 ─────────────────────────────────────────────

	def list_categories(self) -> list[str]:
		"""列出所有已注册的大类名称，供 UI 或策略引擎遍历使用。

		:return: 大类名称字符串列表
		"""
		return [e.name for e in self._core]


	def get_sub_types(self, category: str) -> list[str]:
		"""获取某个大类下的所有子类名称，供策略引擎遍历使用。

		:param category: 大类名称
		:return: 子类名称字符串列表，该大类无子类时返回空列表
		"""
		return [e.name for e in self.subs_of(category)]
