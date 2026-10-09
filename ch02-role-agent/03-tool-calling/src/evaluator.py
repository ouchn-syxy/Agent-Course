"""
提取质量评估器 — LLM-as-Judge 对比自动生成 YAML 与手工参考 YAML。

按方面逐一评估提取质量，维度为：
  1. 字段完整性（completeness）：必要字段是否都已填充
  2. 内容准确性（accuracy）：提取内容是否符合人物真实特征

用法：
    python main.py --eval luxun    # 评估 luxun 角色提取质量
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionUserMessageParam

from config import Config
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from llm.client import LLMClient


# ============================================================
# 数据模型
# ============================================================

@dataclass
class EvalResult:
	"""
	单方面评估结果。

	当 LLM-as-Judge 返回的 JSON 解析成功时，两个维度分值和综合分被填充；
	解析失败时 parse_error 非空，维度分值保持默认 0。
	"""
	aspect_id: str
	dimension: str
	desc: str

	completeness: int = 0  # 字段完整性 1-5
	accuracy: int = 0  # 内容准确性 1-5
	overall: float = 0.0  # 综合分

	analysis: str = ""
	missing_fields: str = ""
	suggestions: str = ""

	parse_error: str = ""


@dataclass
class EvalReport:
	"""
	评估报告，聚合所有 EvalResult。

	提供两个维度的均值计算属性，排除 parse_error 的结果。
	"""
	profile_name: str
	results: list[EvalResult] = field(default_factory=list)


	@property
	def avg_completeness(self) -> float:
		return self._avg("completeness")


	@property
	def avg_accuracy(self) -> float:
		return self._avg("accuracy")


	@property
	def avg_overall(self) -> float:
		return self._avg("overall")


	def _avg(self, field: str) -> float:
		vals: list[float] = [
			float(getattr(r, field))
			for r in self.results
			if getattr(r, field) > 0
		]
		return round(sum(vals) / len(vals), 2) if vals else 0.0


# 评估用温度（低于对话温度，追求评分一致性）
_EVAL_TEMPERATURE: float = 0.3
# API 调用间隔（秒），避免触发频率限制
_API_DELAY: float = 0.5


# ============================================================
# 评估器
# ============================================================

class Evaluator:
	"""
	提取质量 LLM-as-Judge 评估器。

	使用独立的 LLM 调用对自动生成的 YAML 进行二维度评分，
	与提取模型可以是同一个 LLMClient 实例。
	"""


	def __init__(self, llm: LLMClient, prompt_manager: PromptManager) -> None:
		"""
		Args:
			llm: 用于评估的 LLM 客户端。评估用低温度参数以提高评分一致性。
			prompt_manager: Prompt 模板管理器。
		"""
		self._llm: LLMClient = llm
		self._pm: PromptManager = prompt_manager


	def evaluate_one(
			self,
			reference_yaml: str,
			generated_yaml: str,
			aspect: dict[str, Any],
	) -> EvalResult:
		"""
		对单个方面进行二维度评估。

		Args:
			reference_yaml: 参考角色 YAML 原文（视为标准答案）。
			generated_yaml: 自动生成的 YAML 原文。
			aspect: test_questions.json 中的单个方面对象。

		Returns:
			EvalResult 实例。解析成功时维度分值被填充，失败时 parse_error 非空。
		"""
		prompt: str = self._pm.render(
			"eval.j2",
			aspect_desc=str(aspect["desc"]),
			reference_yaml=reference_yaml,
			generated_yaml=generated_yaml,
		)

		try:
			raw: str = self._llm.chat_with_json(
				[ChatCompletionUserMessageParam(role="user", content=prompt)],
				temperature=_EVAL_TEMPERATURE,
			)
			result: dict[str, Any] = json.loads(raw)

			return EvalResult(
				aspect_id=str(aspect["id"]),
				dimension=str(aspect["dimension"]),
				desc=str(aspect["desc"]),
				completeness=int(result.get("completeness", 0)),
				accuracy=int(result.get("accuracy", 0)),
				overall=float(result.get("overall", 0)),
				analysis=str(result.get("analysis", "")),
				missing_fields=str(result.get("missing_fields", "")),
				suggestions=str(result.get("suggestions", "")),
			)
		except (json.JSONDecodeError, KeyError, ValueError) as e:
			return EvalResult(
				aspect_id=str(aspect["id"]),
				dimension=str(aspect["dimension"]),
				desc=str(aspect["desc"]),
				parse_error=str(e),
			)


	def evaluate_all(
			self,
			profile_name: str,
			reference_yaml: str,
			generated_yaml: str,
			aspects: list[dict[str, Any]],
			verbose: bool = True,
	) -> EvalReport:
		"""
		逐方面评估自动生成 YAML 的所有内容质量。

		Args:
			profile_name: 角色名。
			reference_yaml: 参考角色 YAML 原文。
			generated_yaml: 自动生成的 YAML 原文。
			aspects: 评估方面列表（来自 test_questions.json["aspects"]）。
			verbose: 是否在终端打印逐题进度。

		Returns:
			聚合所有 EvalResult 的 EvalReport。
		"""
		report: EvalReport = EvalReport(profile_name=profile_name)
		total: int = len(aspects)

		for i, aspect in enumerate(aspects, 1):
			if verbose:
				print(f"\n[{i}/{total}] 评估: {aspect['id']} ({aspect['dimension']})")

			eval_result: EvalResult = self.evaluate_one(
				reference_yaml, generated_yaml, aspect,
			)

			if eval_result.parse_error:
				print(f"  ⚠ 解析失败: {eval_result.parse_error}")
			elif verbose:
				print(
					f"  完整性={eval_result.completeness} "
					f"准确性={eval_result.accuracy} "
					f"综合={eval_result.overall}"
				)

			report.results.append(eval_result)
			time.sleep(_API_DELAY)

		return report


	@staticmethod
	def print_report(report: EvalReport) -> None:
		"""
		在终端打印评估报告摘要：各维度均值 + 逐方面分析。

		Args:
			report: evaluate_all() 返回的 EvalReport。
		"""
		print("\n" + "=" * 60)
		print(f"  提取质量评估报告 — {report.profile_name}")
		print("=" * 60)
		print(f"  评估方面数: {len(report.results)}")
		print(f"  字段完整性 均值: {report.avg_completeness}")
		print(f"  内容准确性 均值: {report.avg_accuracy}")
		print(f"  {'─' * 50}")
		print(f"  综合得分 均值: {report.avg_overall}")
		print("=" * 60)

		for r in report.results:
			if r.parse_error:
				print(f"\n  [{r.aspect_id}] ❌ 评估失败: {r.parse_error}")
				continue
			print(f"\n  [{r.aspect_id}] {r.dimension}")
			print(f"    完整性: {'★' * r.completeness}{'☆' * (5 - r.completeness)} ({r.completeness}/5)")
			print(f"    准确性: {'★' * r.accuracy}{'☆' * (5 - r.accuracy)} ({r.accuracy}/5)")
			if r.analysis:
				print(f"    分析: {r.analysis}")
			if r.missing_fields:
				print(f"    缺失字段: {r.missing_fields}")
			if r.suggestions:
				print(f"    建议: {r.suggestions}")


# ============================================================
# 便捷函数
# ============================================================

def run_evaluation(profile_name: str) -> EvalReport:
	"""
	一键运行完整评估流程。

	流程：加载参考 YAML → 加载生成 YAML → 加载评估方面列表
	→ 逐方面 LLM-as-Judge 评分 → 打印报告。

	Args:
		profile_name: 角色名称（如 "luxun"）。会对比 data/profiles/{profile_name}.yaml
		           与 output/{profile_name}.yaml。

	Returns:
		评估报告。
	"""
	base_dir: Path = get_prj_root()

	# 加载测试方面列表
	test_path: Path = base_dir / "data" / "eval" / "test_questions.json"
	with open(test_path, encoding="utf-8") as f:
		aspects: list[dict[str, Any]] = json.load(f)["aspects"]

	# 加载参考 YAML（手工编写）
	ref_path: Path = base_dir / "data" / "profiles" / f"{profile_name}.yaml"
	if not ref_path.exists():
		raise FileNotFoundError(f"参考角色文件不存在：{ref_path}")
	with open(ref_path, encoding="utf-8") as f:
		reference_yaml: str = f.read()

	# 加载生成 YAML（自动提取）
	gen_path: Path = base_dir / "output" / f"{profile_name}.yaml"
	if not gen_path.exists():
		raise FileNotFoundError(
			f"自动生成的角色文件不存在：{gen_path}\n"
			f"请先运行 python main.py --extract {profile_name} 生成角色定义。"
		)
	with open(gen_path, encoding="utf-8") as f:
		generated_yaml: str = f.read()

	cfg: Config = Config.from_yaml()
	llm: LLMClient = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	pm: PromptManager = PromptManager(base_dir / "prompts")

	print("=" * 60)
	print(f"  提取质量评估 — {profile_name}")
	print(f"  参考文件: {ref_path}")
	print(f"  生成文件: {gen_path}")
	print("=" * 60)

	evaluator: Evaluator = Evaluator(llm, pm)
	report: EvalReport = evaluator.evaluate_all(
		profile_name=profile_name,
		reference_yaml=reference_yaml,
		generated_yaml=generated_yaml,
		aspects=aspects,
	)
	evaluator.print_report(report)
	return report


if __name__ == "__main__":
	run_evaluation("luxun")
