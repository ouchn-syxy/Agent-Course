"""截图分析器 — 将应用截图送入 VLM，提取 UI 结构和消息内容。

领域约束通过 domain_context 参数注入，与 InfoInspector 模式一致：
调用方负责提供业务相关的布局描述、识别规则等，分析器本身不耦合具体业务。
"""

from PIL import Image

from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.model_render import render_model_code
from agents.eshop_service.vision.models.types import ScreenAnalysis
from vlm.client import VLMClient


class ScreenAnalyzer:
	"""截图结构分析器。

	将应用截图送入 VLM，识别功能区域布局、
	提取聊天/消息内容、定位可交互元素。

	使用方式：
		analyzer = ScreenAnalyzer(vlm_client, prompt_manager)
		result = analyzer.analyze(screenshot, domain_context="三栏布局：...")
		print(f"识别到 {len(result.regions)} 个区域, {len(result.messages)} 条消息")
	"""


	def __init__(self, vlm: VLMClient, pm: PromptManager) -> None:
		"""初始化分析器。

		Args:
			vlm: VLM 客户端。
			pm: Prompt 管理器。
		"""
		self._vlm: VLMClient = vlm
		self._pm: PromptManager = pm


	def analyze(self, domain_context: str | None, screenshot: Image.Image) -> ScreenAnalysis:
		"""分析截图，提取 UI 结构和消息。

		Args:
			domain_context: 业务领域约束文本，描述界面布局、识别规则等。
			                None 时不注入领域背景段。
			screenshot: 应用截图的 PIL 截图。

		Returns:
			ScreenAnalysis: 含区域、消息、活跃用户的结构化分析结果。
		"""
		prompt: str = self._pm.render(
			"agents/eshop_service/vision/analyze.j2",
			domain_context=domain_context,
			screen_analysis_schema=render_model_code(ScreenAnalysis),
		)
		json_raw: str = self._vlm.chat_with_image_json(screenshot, prompt)
		result = ScreenAnalysis.model_validate_json(json_raw)

		# VLM 输出使用 0～1000 归一化坐标，在边界层统一换算为原图像素。
		scale_x = screenshot.width / 1000
		scale_y = screenshot.height / 1000
		for region in result.regions:
			region.bbox.x = round(region.bbox.x * scale_x)
			region.bbox.y = round(region.bbox.y * scale_y)
			region.bbox.width = round(region.bbox.width * scale_x)
			region.bbox.height = round(region.bbox.height * scale_y)
			for element in region.elements:
				element.center_x = round(element.center_x * scale_x)
				element.center_y = round(element.center_y * scale_y)
				element.bbox.x = round(element.bbox.x * scale_x)
				element.bbox.y = round(element.bbox.y * scale_y)
				element.bbox.width = round(element.bbox.width * scale_x)
				element.bbox.height = round(element.bbox.height * scale_y)
		return result


if __name__ == "__main__":

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

	# ── 3. 分析截图 ──────────────────────────────────────────
	analyzer = ScreenAnalyzer(vlm, pm)

	domain_context = (
		"这是一个电商客服工作台截屏，典型三栏布局：\n"
		"- 左侧：客户列表区，显示等待咨询的客户列表\n"
		"- 中间：聊天区，显示与当前客户的对话记录\n"
		"- 右侧：客户信息面板，显示客户订单、偏好等\n"
		"聊天区中每条消息格式为：{客户名称}: {消息内容}\n"
		"当前对话的客户为活跃用户。"
	)

	print("\n" + "=" * 60)
	print("🧪 ScreenAnalyzer.analyze()")
	print("=" * 60)
	result = analyzer.analyze(domain_context, screenshot)

	# ── 4. 输出结果 ──────────────────────────────────────────
	print(f"\n📊 活跃客户: {result.active_customer}")

	print(f"\n📐 功能区域 ({len(result.regions)} 个):")
	for r in result.regions:
		b = r.bbox
		print(f"  ▸ {r.name}  ({b.x},{b.y})→({b.x+b.width},{b.y+b.height}) {b.width}×{b.height}")
		for e in r.elements:
			print(f"      • {e.name}  @({e.center_x},{e.center_y})")

	print(f"\n💬 消息 ({len(result.messages)} 条):")
	for m in result.messages:
		unread = " 🔴" if m.has_unread else ""
		print(f"  ▸ {m.customer_name}: {m.content}{unread}")

	if result.raw_text:
		print(f"\n📝 截图文本: {result.raw_text[:120]}{'...' if len(result.raw_text) > 120 else ''}")

	print("\n✅ Demo 完成")
