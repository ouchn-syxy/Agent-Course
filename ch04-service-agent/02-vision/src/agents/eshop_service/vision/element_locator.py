"""元素定位器 — 在截图中定位指定 UI 元素，输出屏幕绝对坐标。

领域约束通过 domain_context 参数注入，与 InfoInspector 模式一致。
"""

from __future__ import annotations

from PIL import Image

from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from agents.eshop_service.vision.models.types import ElementLocation
from vlm.client import VLMClient


class ElementLocator:
	"""UI 元素定位器。

	用自然语言描述目标元素，VLM 在截图中定位后返回像素坐标。
	自动将图片坐标转换为屏幕绝对坐标（叠加窗口偏移量）。

	使用方式：
		locator = ElementLocator(vlm_client, prompt_manager)
		pos = locator.locate(screenshot, "发送按钮", window_offset=(100, 50))
		print(f"发送按钮屏幕坐标: ({pos.center_x}, {pos.center_y})")
	"""


	def __init__(self, vlm: VLMClient, pm: PromptManager) -> None:
		"""初始化定位器。

		Args:
			vlm: VLM 客户端。
			pm: Prompt 管理器。
		"""
		self._vlm: VLMClient = vlm
		self._pm: PromptManager = pm


	def locate(
			self,
			domain_context: str | None,
			screenshot: Image.Image,
			target: str,
			window_offset: tuple[int, int] = (0, 0),
	) -> ElementLocation:
		"""在截图中定位指定元素。

		Args:
			domain_context: 业务领域约束文本，描述界面特征、元素分布等。
			                None 时不注入领域背景段。
			screenshot: 截图 PIL Image。
			target: 目标元素的自然语言描述，如 "发送按钮"、"客户列表中张三的条目"。
			window_offset: 窗口左上角在屏幕上的坐标 (x, y)，
			              用于将图片坐标转换为屏幕绝对坐标。

		Returns:
			ElementLocation: 含屏幕绝对坐标的定位结果。
		"""
		prompt: str = self._pm.render(
			"agents/eshop_service/vision/locate.j2",
			domain_context=domain_context,
			target=target,
			element_location_schema=render_model_code(ElementLocation),
		)
		json_raw: str = self._vlm.chat_with_image_json(screenshot, prompt)
		result: ElementLocation = ElementLocation.model_validate_json(json_raw)

		# VLM 归一化坐标 → 原图像素 → 屏幕绝对坐标。
		scale_x = screenshot.width / 1000
		scale_y = screenshot.height / 1000
		if result.confidence > 0:
			result.center_x = round(result.center_x * scale_x) + window_offset[0]
			result.center_y = round(result.center_y * scale_y) + window_offset[1]
			result.bbox.x = round(result.bbox.x * scale_x)
			result.bbox.y = round(result.bbox.y * scale_y)
			result.bbox.width = round(result.bbox.width * scale_x)
			result.bbox.height = round(result.bbox.height * scale_y)

		return result


if __name__ == "__main__":
	"""演示 ElementLocator 元素定位。

	用法：
		cd ch04-service-agent/02-vision/src
		python vision/locator.py

	前提：config.yaml 中 vlm 配置已填写，
	      data/tests/screenshot.png 已准备就绪。
	"""

	from config import Config
	from inherit.utils.path import get_prj_root

	# ── 1. 加载配置 ──────────────────────────────────────────
	cfg = Config.from_yaml()
	pm = PromptManager(get_prj_root() / "prompts")

	vlm = VLMClient(
		api_key=cfg.vlm.api_key_env,
		base_url=cfg.vlm.base_url,
		model=cfg.vlm.model,
		provider=cfg.vlm.provider,
	)
	print(f"✅ VLMClient 就绪  provider={vlm.provider}  model={vlm.model}")

	# ── 2. 加载测试截图 ──────────────────────────────────────
	screenshot_path = get_prj_root() / "data" / "tests" / "screenshot.png"
	if not screenshot_path.exists():
		print(f"❌ 截图不存在: {screenshot_path}")
		raise SystemExit(1)

	screenshot = Image.open(screenshot_path)
	print(f"✅ 已加载截图: {screenshot_path.name}  ({screenshot.width}×{screenshot.height})")

	# ── 3. 定位多个元素 ──────────────────────────────────────
	locator = ElementLocator(vlm, pm)

	# 模拟窗口偏移（实际使用时由 screenshot 工具返回）
	window_offset = (200, 100)

	domain_context = (
		"这是一个电商客服工作台截屏，典型三栏布局：\n"
		"- 左侧：客户列表区，显示等待咨询的客户列表\n"
		"- 中间：聊天区，显示与当前客户的对话记录\n"
		"- 右侧：客户信息面板，显示客户订单、偏好等\n"
	)

	targets = [
		"发送按钮",
		"消息输入框",
		"重置按钮",
		"客户列表中钱七的条目",
		"右侧面板的搜索按钮",
	]

	print("\n" + "=" * 60)
	print("🧪 ElementLocator.locate()")
	print(f"   窗口偏移: {window_offset}")
	print("=" * 60)

	for target in targets:
		result = locator.locate(
			domain_context=domain_context,
			screenshot=screenshot,
			target=target,
			window_offset=window_offset,
		)
		b = result.bbox
		print(f"\n🎯 \"{target}\"")
		print(f"   置信度: {result.confidence}")
		print(f"   屏幕坐标: ({result.center_x}, {result.center_y})")
		print(f"   边界框: ({b.x},{b.y}) {b.width}×{b.height}")

	print("\n✅ Demo 完成")
