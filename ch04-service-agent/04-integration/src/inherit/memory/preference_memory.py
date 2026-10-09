"""PreferenceMemory — 用户偏好记忆模块（JSON 文件持久化）。

记录和检索用户偏好，实现跨会话的个性化推荐。
设计参考 inherit.memory.conversation_memory 的文件持久化模式。

用法：
    mem = PreferenceMemory(storage_dir=Path("data/memories"), session_id="trip_agent")
    mem.record_preference("酒店风格", "海景房")
    prefs = mem.get_preferences()
    context = mem.to_context()
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class PreferenceEntry(BaseModel):
	"""单条偏好记录 — 模型可自主发现任意偏好维度。"""
	tag: str = Field(description="偏好维度/类别（自然语言）")
	value: str = Field(description="偏好具体内容")
	updated_at: datetime = Field(default_factory=datetime.now, description="最后更新时间")


class PreferenceStore(BaseModel):
	"""偏好记忆的顶层数据结构。"""
	preferences: list[PreferenceEntry] = Field(
		default_factory=list,
		description="偏好列表",
	)


# ============================================================
# PreferenceMemory
# ============================================================

class PreferenceMemory:
	"""JSON 文件偏好记忆 — 记录用户的历史选择和偏好。

	设计要点：
	  - 按 session_id 区分会话，每个会话独立持久化偏好文件
	  - 构造时自动从 JSON 文件加载已有数据
	  - 每次写入操作后自动落盘

	Attributes:
		_session_id: 会话标识符（如 "trip_agent"），用于区分不同会话的持久化文件。
		_storage_path: 持久化文件完整路径（由 storage_dir + session_id 拼接）。
	"""


	def __init__(self, storage_dir: Path, session_id: str) -> None:
		"""
		Args:
			storage_dir: 持久化文件存储目录。
			session_id: 会话标识符（如 "trip_agent"），用于文件持久化。
		"""
		self._session_id: str = session_id
		self._storage_dir: Path = storage_dir
		self._store: PreferenceStore = PreferenceStore()

		# 自动加载已有数据
		self._load_from_file()


	# ================================================================
	# 持久化（参考 ConversationMemory 模式）
	# ================================================================

	@property
	def _storage_path(self) -> Path:
		"""完整的 JSON 文件路径。"""
		return self._storage_dir / f"{self._session_id}_preferences.json"


	def _save_to_file(self) -> None:
		"""将当前数据落盘为 JSON 文件。"""
		self._storage_dir.mkdir(parents=True, exist_ok=True)
		json_text: str = self._store.model_dump_json(indent=4, ensure_ascii=False)
		self._storage_path.write_text(json_text, encoding="utf-8", )


	def _load_from_file(self) -> None:
		"""从 JSON 文件恢复数据。文件不存在时静默跳过。"""
		if not self._storage_path.exists():
			return
		json_text: str = self._storage_path.read_text(encoding="utf-8")
		self._store = PreferenceStore.model_validate_json(json_text)


	# ================================================================
	# 偏好操作
	# ================================================================

	def _find_entry(self, tag: str) -> PreferenceEntry | None:
		"""在偏好列表中按 tag 查找已有条目。"""
		for entry in self._store.preferences:
			if entry.tag == tag:
				return entry
		return None


	def record_preference(self, tag: str, value: str) -> None:
		"""记录/更新一条偏好。tag 已存在则更新值，否则新增。

		:param tag:   偏好名称（自然语言，如 酒店风格、饮食偏好）
		:param value: 偏好内容（如 海景房、川菜/辣味）
		"""
		existing: PreferenceEntry | None = self._find_entry(tag)
		if existing:
			existing.value = value
			existing.updated_at = datetime.now()
		else:
			self._store.preferences.append(PreferenceEntry(tag=tag, value=value))
		self._save_to_file()


	def get_preferences(self) -> list[PreferenceEntry]:
		"""获取全部已记录的偏好。

		:return: 偏好条目列表
		"""
		return list(self._store.preferences)


	def get_preference(self, tag: str) -> PreferenceEntry | None:
		"""获取指定偏好。"""
		return self._find_entry(tag)


	def delete_preference(self, tag: str) -> None:
		"""删除指定偏好。"""
		entry: PreferenceEntry | None = self._find_entry(tag)
		if entry:
			self._store.preferences.remove(entry)
			self._save_to_file()


	# ================================================================
	# 上下文生成
	# ================================================================

	def to_context(self) -> str:
		"""生成可注入 prompt 的用户偏好上下文。"""
		prefs: list[PreferenceEntry] = self.get_preferences()
		if not prefs:
			return ""

		lines: list[str] = ["## 用户偏好"]
		for entry in prefs:
			lines.append(f"- {entry.tag}：{entry.value}")
		return "\n".join(lines)


# ================================================================
# 演示
# ================================================================

if __name__ == "__main__":
	import tempfile

	with tempfile.TemporaryDirectory() as tmpdir:
		storage: Path = Path(tmpdir)
		mem: PreferenceMemory = PreferenceMemory(storage_dir=storage, session_id="demo")

		# ── 记录偏好 ──
		mem.record_preference("沟通风格", "简洁直接")
		mem.record_preference("酒店风格", "海景房")
		mem.record_preference("酒店风格", "商务型")  # 更新已有 tag

		# ── 读取 ──
		prefs: list[PreferenceEntry] = mem.get_preferences()
		print("📋 当前偏好：")
		for p in prefs:
			print(f"  - {p.tag}：{p.value}")

		# ── 生成上下文 ──
		context: str = mem.to_context()
		print(f"\n📝 上下文文本：\n{context}")
