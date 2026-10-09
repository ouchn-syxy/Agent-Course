"""批量 GUI 回复编排器 — 自动循环遍历用户选项卡执行回复。

职责：截图工作台 → VLM 识别左侧栏用户选项卡 → 循环点击每个用户 →
调用 GUIReplyAgent 处理该用户的聊天回复 → 统计结果。

     ┌──────────────────────────────────────────┐
     │  BatchGUIReplyAgent                      │
     │                                          │
     │  1. 截图整个客服工作台                     │
     │  2. VLM 识别左侧栏用户选项卡坐标            │
     │  3. 循环（直到处理数 >= max_users）：        │
     │     for user in users（无限循环）：         │
     │       a. click(user.x, user.y)            │
     │       b. sleep(wait_seconds)              │
     │       c. GUIReplyAgent.run()              │
     │       d. 记录日志/结果                      │
     │  4. 输出统计摘要                           │
     └──────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agents.eshop_service.gui_reply_agent import GUIReplyAgent
from inherit.agents.eshop_service.message_classifier import MessageClassifier
from agents.eshop_service.reply_generator import ReplyGenerator
from inherit.agents.eshop_service.strategy_engine import StrategyEngine
from inherit.agents.eshop_service.tools.input import Input
from inherit.agents.eshop_service.tools.window import ScreenshotResult, Window, WindowInfo
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from inherit.utils.path import get_prj_root
from inherit.vlm.tool_vlm_client import ToolVLMClient


# ═══════════════════════════════════════════════════════════════════════
# 类型定义（Pydantic → JSON Schema → 注入提示词）
# ═══════════════════════════════════════════════════════════════════════


class UserTabItem(BaseModel):
	"""单个用户选项卡 — VLM 从截图中识别的可点击条目。"""

	name: str = Field(description="用户名（显示在选项卡上）")
	x: int = Field(ge=0, le=1000, description="可点击位置 X 归一化坐标（0～1000）")
	y: int = Field(ge=0, le=1000, description="可点击位置 Y 归一化坐标（0～1000）")


class UserTabList(BaseModel):
	"""用户选项卡列表 — VLM 截图识别结果。"""

	users: list[UserTabItem] = Field(description="用户选项卡列表，按从上到下排列")


# ═══════════════════════════════════════════════════════════════════════
# 运行时数据结构（dataclass）
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class UserTab:
	"""VLM 识别出的用户选项卡信息。"""

	name: str
	"""用户名称（显示在选项卡上）。"""

	abs_x: int
	"""绝对屏幕 X 坐标（可直接传给 Input.click）。"""

	abs_y: int
	"""绝对屏幕 Y 坐标（可直接传给 Input.click）。"""


@dataclass
class UserResult:
	"""单个用户处理结果。"""

	user_name: str
	result: str
	elapsed_seconds: float


@dataclass
class BatchResult:
	"""批量处理汇总结果。"""

	total_users: int = 0
	"""总共处理的用户数（含重复）。"""

	results: list[UserResult] = field(default_factory=list)
	"""每个用户的处理结果列表。"""

	start_time: float = 0.0
	"""开始时间戳。"""

	end_time: float = 0.0
	"""结束时间戳。"""


	@property
	def total_elapsed(self) -> float:
		"""总耗时（秒）。"""
		return self.end_time - self.start_time


	@property
	def avg_elapsed(self) -> float:
		"""平均每用户耗时（秒）。"""
		return self.total_elapsed / max(self.total_users, 1)


	def summary(self) -> str:
		"""生成统计摘要文本。"""
		if not self.results:
			return "⚠️ 无处理记录"

		lines: list[str] = [
			"=" * 60,
			"📊 批量处理统计摘要",
			"=" * 60,
			f"  处理总数: {self.total_users} 个用户会话",
			f"  总耗时: {self.total_elapsed:.1f}s",
			f"  平均耗时: {self.avg_elapsed:.1f}s / 用户",
			"-" * 60,
		]
		for i, r in enumerate(self.results, 1):
			lines.append(f"  [{i}] {r.user_name} ({r.elapsed_seconds:.1f}s) → {r.result[:80]}")
		lines.append("=" * 60)
		return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 批量编排器
# ═══════════════════════════════════════════════════════════════════════


class BatchGUIReplyAgent:
	"""批量 GUI 回复编排器 — 自动循环遍历所有用户选项卡执行回复。

	使用 VLM 识别左侧栏用户选项卡位置，然后逐一切换用户，
	调用 GUIReplyAgent 处理聊天回复。

	使用方式：
		batch = BatchGUIReplyAgent(
			batch_vlm=vlm_client,
			reply_vlm=tool_vlm_client,
			pm=prompt_manager,
			classifier=classifier,
			strategy_engine=strategy_engine,
			reply_generator=reply_generator,
			reply_max_steps=20,
			wait_seconds=2.0,
		)
		result = batch.run(max_users=20)
		print(result.summary())
	"""


	def __init__(
			self,
			vlm: ToolVLMClient,
			pm: PromptManager,
			classifier: MessageClassifier,
			strategy_engine: StrategyEngine,
			reply_generator: ReplyGenerator,
			reply_max_steps: int = 20,
			wait_seconds: float = 1.0,
			verbose: bool = True,
	) -> None:
		"""初始化批量编排器。

		Args:
			vlm: VLM 客户端，用于识别用户选项卡（纯视觉，非 FC）。
			vlm: 支持 Function Calling 的 VLM 客户端，传给 GUIReplyAgent。
			pm: Prompt 管理器。
			classifier: 消息分类器。
			strategy_engine: 策略引擎。
			reply_generator: 回复生成器。
			reply_max_steps: 每个用户的 GUIReplyAgent 最大 ReAct 步数。
			wait_seconds: 切换用户后等待页面加载的秒数。
			verbose: 是否输出详细日志。
		"""
		self._vlm: ToolVLMClient = vlm
		self._pm: PromptManager = pm
		self._reply_agent: GUIReplyAgent = GUIReplyAgent(
			vlm=self._vlm,
			pm=self._pm,
			classifier=classifier,
			strategy_engine=strategy_engine,
			reply_generator=reply_generator,
			max_steps=reply_max_steps,
			verbose=verbose,
		)

		self._wait_seconds: float = wait_seconds
		self._verbose: bool = verbose

		self._window: Window = Window(get_prj_root() / "tmp")
		self._input: Input = Input()


	# ── 日志 ──────────────────────────────────────────────

	def _log(self, msg: str) -> None:
		"""verbose=True 时打印消息。"""
		if self._verbose:
			print(msg)


	def _find_window(self) -> WindowInfo:
		return self._window.find("网店客服工作台")


	# ── 用户选项卡识别 ────────────────────────────────────

	def _identify_user_tabs(self, image: ScreenshotResult) -> list[UserTab]:
		"""使用 VLM 识别截图左侧栏中的用户选项卡。

		Args:
			image: 工作台全屏截图。
			window_info: 窗口元信息（用于坐标转换）。

		Returns:
			UserTab 列表，按从上到下排列。

		Raises:
			RuntimeError: VLM 返回结果无法解析。
		"""
		# 生成 Pydantic schema 并注入提示词
		prompt: str = self._pm.render(
			"agents/eshop_service/batch_gui_reply_agent/identify_users.j2",
			user_tabs_schema=render_model_code(UserTabList),
		)

		self._log("🔍 正在通过 VLM 识别左侧栏用户选项卡...")
		json_raw: str = self._vlm.chat_with_image_json(image.image, prompt)

		try:
			user_tab_list: UserTabList = UserTabList.model_validate_json(json_raw)
		except json.JSONDecodeError as e:
			raise RuntimeError(f"VLM 返回的 JSON 无法解析: {e}\n原始内容: {json_raw[:500]}") from e

		if not user_tab_list.users:
			raise RuntimeError(f"VLM 未识别到任何用户选项卡。原始内容: {json_raw[:500]}")

		window_info: WindowInfo = self._find_window()
		users: list[UserTab] = []
		for item in user_tab_list.users:
			# 坐标转换：截图坐标 → 绝对屏幕坐标
			# VLM（doubao-seed 系列）返回 1000×1000 归一化坐标
			sx: int = item.x
			sy: int = item.y
			abs_x: int = round(sx / 1000 * window_info.width) + window_info.x
			abs_y: int = round(sy / 1000 * window_info.height) + window_info.y

			tab: UserTab = UserTab(name=str(item.name), abs_x=abs_x, abs_y=abs_y)
			users.append(tab)

		self._log(f"✅ 识别到 {len(users)} 个用户选项卡:")
		for i, item in enumerate(users):
			self._log(f"  [{i + 1}] {item.name} @ 绝对坐标 ({item.abs_x}, {item.abs_y})")

		return users


	# ── 主循环 ────────────────────────────────────────────

	def run(self, max_users: int = 20, target_user: str | None = None) -> BatchResult:
		"""启动批量处理循环。

		流程：
		  1. 定位窗口 → 截图
		  2. VLM 识别用户选项卡
		  3. 循环点击每个用户 → 等待加载 → GUIReplyAgent.run()
		  4. 输出统计摘要

		Args:
			max_users: 最多处理的用户会话数（不是用户数，而是处理次数）。

		Returns:
			BatchResult 统计结果。
		"""
		result: BatchResult = BatchResult(start_time=time.time())

		# 1) 先将 Chrome 置前，避免区域截图截到覆盖其上的 VS Code 或终端
		self._window.activate()

		# 2) 定位浏览器窗口
		window_info: WindowInfo = self._find_window()
		self._log(f"🪟 窗口: {window_info.title} ({window_info.width}×{window_info.height})")

		# 3) 截取工作台全屏
		screenshot: ScreenshotResult = self._window.screenshot(window_info.window_id)

		# 4) VLM 识别用户选项卡
		users: list[UserTab] = self._identify_user_tabs(screenshot)
		if target_user:
			users = [user for user in users if user.name == target_user]
			if not users:
				raise RuntimeError(f"未在左侧用户列表中识别到指定用户「{target_user}」")
			self._log(f"🎯 课堂定向演示：仅处理用户「{target_user}」")
		if not users:
			print("⚠️ 未识别到任何用户选项卡，退出")
			result.end_time = time.time()
			return result

		# 5) 循环处理用户
		print(f"\n{'=' * 60}")
		print(f"🚀 开始批量处理，共 {len(users)} 个用户，目标最多 {max_users} 次")
		print(f"{'=' * 60}\n")

		user_idx: int = 0
		while result.total_users < max_users:
			user: UserTab = users[user_idx % len(users)]
			user_idx += 1
			result.total_users += 1

			print(f"\n── [{result.total_users}/{max_users}] 切换到用户: {user.name} ──")

			# a) 点击用户选项卡
			click_result: str = self._input.click(user.abs_x, user.abs_y)
			self._log(f"  🖱️ {click_result}")

			# b) 等待页面加载
			self._log(f"  ⏳ 等待 {self._wait_seconds:.1f}s 页面加载...")
			time.sleep(self._wait_seconds)

			# c) 调用 GUIReplyAgent
			t_start: float = time.time()
			try:
				self._reply_agent.run()
				reply_result: str = "处理完成"
			except Exception as e:
				reply_result = f"❌ GUIReplyAgent 异常: {type(e).__name__}: {e}"
				self._log(f"  {reply_result}")
			elapsed: float = time.time() - t_start

			user_result: UserResult = UserResult(
				user_name=user.name,
				result=reply_result,
				elapsed_seconds=elapsed,
			)
			result.results.append(user_result)

			self._log(f"  ✅ 用户 {user.name} 处理完成 ({elapsed:.1f}s): {reply_result[:100]}")

		result.end_time = time.time()

		# 5) 输出摘要
		print(f"\n{result.summary()}")

		return result
