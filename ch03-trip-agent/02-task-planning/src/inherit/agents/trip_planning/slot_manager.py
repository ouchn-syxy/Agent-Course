"""槽位管理器 — 行程需求信息槽位的定义、状态管理与可视化。

8 个槽位分为必需和可选两类，每个槽位经历三态流转：
  UNKNOWN → COLLECTING → CONFIRMED
"""

from dataclasses import dataclass
from enum import Enum


# ============================================================
# 槽位枚举
# ============================================================

class SlotName(str, Enum):
	"""槽位名枚举 — 8 个出行需求信息槽位。"""

	# ── 必需槽位（4 个） ──
	DESTINATION = "destination"
	DEPARTURE_CITY = "departure_city"
	START_DATE = "start_date"
	END_DATE = "end_date"

	# ── 可选槽位（4 个） ──
	BUDGET = "budget"
	TRAVELERS = "travelers"
	PREFERENCES = "preferences"
	CONSTRAINTS = "constraints"


	@property
	def label(self) -> str:
		"""槽位中文标签。"""
		return {
			SlotName.DESTINATION: "目的地",
			SlotName.DEPARTURE_CITY: "出发城市",
			SlotName.START_DATE: "出发日期",
			SlotName.END_DATE: "返回日期",
			SlotName.BUDGET: "预算",
			SlotName.TRAVELERS: "同行人数",
			SlotName.PREFERENCES: "偏好",
			SlotName.CONSTRAINTS: "约束条件",
		}[self]


	@property
	def required(self) -> bool:
		"""是否必需槽位。"""
		_REQUIRED = {SlotName.DESTINATION, SlotName.DEPARTURE_CITY, SlotName.START_DATE, SlotName.END_DATE}
		return self in _REQUIRED


# ============================================================
# 槽位状态 & 数据结构
# ============================================================

class SlotState(str, Enum):
	"""槽位状态 — 三态模型。"""

	UNKNOWN = "unknown"  # 尚未涉及
	COLLECTING = "collecting"  # 正在收集中（LLM 已提问或用户已回答但未确认）
	CONFIRMED = "confirmed"  # 已确认


@dataclass
class SlotInfo:
	"""单个信息槽位。"""

	name: str  # 槽位名（如 destination）
	label: str  # 中文标签（如"目的地"）
	value: str = ""  # 当前值
	state: SlotState = SlotState.UNKNOWN
	required: bool = True  # 是否必需


class SlotManager:
	"""行程需求槽位管理器。

	职责：
	  - 管理 8 个槽位的状态流转
	  - 提供槽位查询（缺少哪些必需槽位、是否全部完成）
	  - 生成 LLM 上下文（当前收集状态）
	  - 生成终端可视化面板
	  - 生成最终需求摘要
	"""


	def __init__(self) -> None:
		self._slots: dict[str, SlotInfo] = {}
		for sn in SlotName:
			self._slots[sn.value] = SlotInfo(
				name=sn.value,
				label=sn.label,
				required=sn.required,
			)


	# ── 核心操作 ────────────────────────────────────────────

	def fill(self, name: SlotName, value: str) -> bool:
		"""填充槽位值，状态推进到 COLLECTING。

		Args:
			name: 槽位名（SlotName 枚举）。
			value: 填充值。

		Returns:
			True 表示覆盖了已确认的值（用户改主意），False 表示正常填充。
		"""
		key: str = name.value
		if key in self._slots:
			was_confirmed: bool = self._slots[key].state == SlotState.CONFIRMED
			self._slots[key].value = value
			self._slots[key].state = SlotState.COLLECTING
			return was_confirmed
		return False


	def reset(self, name: SlotName) -> None:
		"""重置槽位到 UNKNOWN 状态（用户明确否定已确认信息时使用）。"""
		key: str = name.value
		if key in self._slots:
			self._slots[key].value = ""
			self._slots[key].state = SlotState.UNKNOWN


	def confirm(self, name: SlotName) -> None:
		"""确认槽位，状态推进到 CONFIRMED。"""
		key: str = name.value
		if key in self._slots:
			self._slots[key].state = SlotState.CONFIRMED


	def confirm_all_collecting(self) -> None:
		"""一键确认所有 COLLECTING 状态的槽位（LLM 调用 confirm/complete 时用）。"""
		for s in self._slots.values():
			if s.state == SlotState.COLLECTING:
				s.state = SlotState.CONFIRMED


	# ── 查询 ─────────────────────────────────────────────────

	def get_missing_required(self) -> list[SlotInfo]:
		"""返回尚未填充的必需槽位（UNKNOWN 状态）。"""
		return [s for s in self._slots.values() if s.required and s.state == SlotState.UNKNOWN]


	def is_all_required_filled(self) -> bool:
		"""所有必需槽位是否至少进入了 COLLECTING 状态。"""
		return len(self.get_missing_required()) == 0


	def is_all_confirmed(self) -> bool:
		"""所有槽位（含可选）是否全部 CONFIRMED。"""
		return all(s.state == SlotState.CONFIRMED for s in self._slots.values())


	def get_slot(self, name: SlotName) -> SlotInfo | None:
		"""按名获取槽位。"""
		return self._slots.get(name.value)


	# ── 上下文生成 ──────────────────────────────────────────

	def to_context(self) -> str:
		"""生成 LLM 上下文 — 展示当前所有槽位的收集状态。

		输出分三组：已确认 / 收集中 / 未询问。
		"""
		confirmed: list[SlotInfo] = [s for s in self._slots.values() if s.state == SlotState.CONFIRMED]
		collecting: list[SlotInfo] = [s for s in self._slots.values() if s.state == SlotState.COLLECTING]
		unknown: list[SlotInfo] = [s for s in self._slots.values() if s.state == SlotState.UNKNOWN]

		lines: list[str] = []

		if confirmed:
			lines.append("## 已确认的需求")
			for s in confirmed:
				mark: str = "（必需）" if s.required else "（可选）"
				lines.append(f"- {s.label}{mark}：{s.value}")
			lines.append("")

		if collecting:
			lines.append("## 正在收集中（尚未确认）")
			for s in collecting:
				mark: str = "（必需）" if s.required else "（可选）"
				lines.append(f"- {s.label}{mark}：{s.value}")
			lines.append("")

		if unknown:
			lines.append("## 尚未询问")
			for s in unknown:
				mark: str = "（必需）" if s.required else "（可选）"
				lines.append(f"- {s.label}{mark}")
			lines.append("")

		return "\n".join(lines).strip() or "（暂无已收集的信息）"


	def to_summary(self) -> str:
		"""生成最终需求摘要（确认后输出给用户）。"""
		lines: list[str] = ["=" * 40, "  📋 最终需求摘要", "=" * 40, ""]
		for sn in SlotName:
			s: SlotInfo = self._slots[sn.value]
			val: str = s.value if s.value else "（未指定）"
			mark: str = "【必需】" if s.required else "【可选】"
			lines.append(f"  {s.label} {mark}：{val}")
		lines.append("")
		lines.append("=" * 40)
		return "\n".join(lines)


	# ── 可视化面板 ──────────────────────────────────────────

	def render_panel(self) -> str:
		"""终端 ASCII 可视化面板 — 实时展示槽位填充进度。"""
		width: int = 52
		lines: list[str] = [
			"┌" + "─" * (width - 2) + "┐",
			"│" + "  📋 需求信息收集面板".ljust(width - 2) + "│",
			"├" + "─" * 22 + "┬" + "─" * 12 + "┬" + "─" * (width - 38) + "┤",
		]

		for _, s in self._slots.items():
			mapping: dict[SlotState, str] = {
				SlotState.UNKNOWN: "⬜ 未询问",
				SlotState.COLLECTING: "🔄 收集中",
				SlotState.CONFIRMED: "✅ 已确认",
			}
			status: str = mapping.get(s.state, "  ?")
			val_display: str = s.value if s.value else "-"
			if len(val_display) > width - 40:
				val_display = val_display[:width - 43] + "..."

			label_col: str = f"  {s.label}"
			status_col: str = f" {status}"
			val_col: str = f" {val_display}"

			lines.append(
				f"│{label_col:<20}│{status_col:<10}│{val_col:<{width - 36}}│"
			)

		lines.append("└" + "─" * 22 + "┴" + "─" * 12 + "┴" + "─" * (width - 38) + "┘")
		return "\n".join(lines)


# ============================================================
# 演示：所有功能快速走查
# ============================================================
if __name__ == "__main__":
	mgr: SlotManager = SlotManager()

	# ── 初始状态 ──
	print("=== 1. 初始面板（全部 UNKNOWN）===")
	print(mgr.render_panel())

	print("缺失的必需槽位:", [s.name for s in mgr.get_missing_required()])
	print("必需全填了？", mgr.is_all_required_filled())  # False

	# ── 逐槽填充 ──
	print("\n=== 2. 填充 3 个必需 + 1 个可选 ===")
	mgr.fill(SlotName.DESTINATION, "杭州")
	mgr.fill(SlotName.DEPARTURE_CITY, "北京")
	mgr.fill(SlotName.START_DATE, "2026-08-01")
	mgr.fill(SlotName.BUDGET, "5000 元/人")
	print(mgr.render_panel())

	print("缺失的必需槽位:", [s.name for s in mgr.get_missing_required()])  # end_date

	# ── 全部必需填完 ──
	print("\n=== 3. 填完最后一个必需槽位 ===")
	mgr.fill(SlotName.END_DATE, "2026-08-05")
	print("必需全填了？", mgr.is_all_required_filled())  # True
	print("全部确认了？", mgr.is_all_confirmed())  # False

	# ── 一键确认 COLLECTING → CONFIRMED ──
	print("\n=== 4. 一键确认所有 COLLECTING ===")
	mgr.confirm_all_collecting()
	print(mgr.render_panel())
	print("全部确认了？", mgr.is_all_confirmed())  # False（可选槽位仍是 UNKNOWN）

	# ── 上下文 & 摘要 ──
	print("\n=== 5. LLM 上下文（to_context）===")
	print(mgr.to_context())

	print("\n=== 6. 最终需求摘要（to_summary）===")
	print(mgr.to_summary())

	# ── 单槽查询 ──
	print("\n=== 7. 单槽查询 ===")
	slot: SlotInfo | None = mgr.get_slot(SlotName.PREFERENCES)
	if slot:
		print(f"preferences: value={slot.value!r}, state={slot.state.value}, required={slot.required}")
