"""
LLM-as-Judge 评估器 —— 从四个维度评估角色模拟质量。

用另一组 LLM 调用对智能体回复打分，维度为：
  1. 身份一致性（identity）
  2. 风格匹配度（style）
  3. 知识准确性（knowledge）
  4. 时代契合度（era）

输出结构化 EvalResult / EvalReport，可在终端展示或导出 CSV。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from openai.types.chat import ChatCompletionUserMessageParam

from config import Config
from llm.chat_session import ChatSession
from llm.client import LLMClient
from prompt.prompt_manager import PromptManager
from utils.path import get_prj_root


# ============================================================
# 数据模型
# ============================================================

@dataclass
class EvalResult:
	"""
	单题评估结果。

	当 LLM-as-Judge 返回的 JSON 解析成功时，四个维度分值和综合分被填充；
	解析失败时 parse_error 非空，维度分值保持默认 0。
	"""
	question_id: str
	dimension: str
	question: str
	response: str

	identity: int = 0  # 身份一致性 1-5
	style: int = 0  # 风格匹配度 1-5
	knowledge: int = 0  # 知识准确性 1-5
	era: int = 0  # 时代契合度 1-5
	overall: float = 0.0  # 综合加权平均分

	strengths: str = ""  # Judge 指出的亮点
	weaknesses: str = ""  # Judge 指出的不足
	suggestion: str = ""  # Judge 的改进建议

	parse_error: str = ""  # JSON 解析失败时的错误信息（非空表示该题评估无效）


@dataclass
class EvalReport:
	"""
	评估报告，聚合所有 EvalResult。

	提供四个维度的均值计算属性，排除 parse_error 的结果。
	"""
	profile_name: str
	results: list[EvalResult] = field(default_factory=list)


	@property
	def avg_identity(self) -> float:
		"""身份一致性均值。"""
		return self._avg("identity")


	@property
	def avg_style(self) -> float:
		"""风格匹配度均值。"""
		return self._avg("style")


	@property
	def avg_knowledge(self) -> float:
		"""知识准确性均值。"""
		return self._avg("knowledge")


	@property
	def avg_era(self) -> float:
		"""时代契合度均值。"""
		return self._avg("era")


	@property
	def avg_overall(self) -> float:
		"""综合得分均值。"""
		return self._avg("overall")


	def _avg(self, field: str) -> float:
		"""
		计算指定字段的均值，自动排除未评分的项（分值为 0）。

		Args:
			field: EvalResult 的属性名。

		Returns:
			均值，保留两位小数。无有效结果时返回 0.0。
		"""
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
# 获取回复的最大重试次数
_MAX_RETRIES: int = 3
# 重试间隔（秒）
_RETRY_DELAY: float = 2.0


# ============================================================
# 评估器
# ============================================================

class Evaluator:
	"""
	LLM-as-Judge 评估器。

	使用独立的 LLM 调用对智能体回复进行四维度评分，
	与对话模型可以是同一个 LLMClient 实例。
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
			profile_yaml: str,
			question: dict[str, Any],
			response: str,
	) -> EvalResult:
		"""
		对单个问答进行四维度评估。

		Args:
			profile_yaml: 角色 YAML 原文（供 judge 参考角色定义）。
			question: test_questions.json 中的单题对象。
			response: 智能体对该问题的回复文本。

		Returns:
			EvalResult 实例。解析成功时维度分值被填充，失败时 parse_error 非空。
		"""
		# 构建评估 prompt
		prompt: str = self._pm.render(
			"eval.j2",
			profile_yaml=profile_yaml,
			test_dimension=str(question.get("dimension_desc", question["dimension"])),
			user_question=str(question["question"]),
			agent_response=response,
		)

		last_error: Exception | None = None
		for attempt in range(_MAX_RETRIES):
			try:
				# 以低温度调用 LLM 做评估，保证评分稳定性。
				raw: str = self._llm.chat_with_json(
					[ChatCompletionUserMessageParam(role="user", content=prompt)],
					temperature=_EVAL_TEMPERATURE,
				)
				result: dict[str, Any] = json.loads(raw)
				return EvalResult(
					question_id=str(question["id"]),
					dimension=str(question["dimension"]),
					question=str(question["question"]),
					response=response,
					identity=int(result.get("identity", 0)),
					style=int(result.get("style", 0)),
					knowledge=int(result.get("knowledge", 0)),
					era=int(result.get("era", 0)),
					overall=float(result.get("overall", 0)),
					strengths=str(result.get("strengths", "")),
					weaknesses=str(result.get("weaknesses", "")),
					suggestion=str(result.get("suggestion", "")),
				)
			except (json.JSONDecodeError, KeyError, ValueError) as error:
				last_error = error
				if attempt < _MAX_RETRIES - 1:
					time.sleep(_RETRY_DELAY)

		return EvalResult(
			question_id=str(question["id"]),
			dimension=str(question["dimension"]),
			question=str(question["question"]),
			response=response,
			parse_error=str(last_error),
		)


	def evaluate_all(
			self,
			profile_name: str,
			profile_yaml_raw: str,
			questions: list[dict[str, Any]],
			get_response: Callable[[str], str],
			verbose: bool = True,
	) -> EvalReport:
		"""
		批量评估所有测试问题，生成报告。

		Args:
			profile_name: 角色名。
			profile_yaml_raw: 角色 YAML 原文，传入 judge 作为评估参考。
			questions: 测试问题列表（来自 test_questions.json["questions"]）。
			get_response: 可调用对象，签名 (question: str) -> str。
			verbose: 是否在终端打印逐题进度。

		Returns:
			聚合所有 EvalResult 的 EvalReport。
		"""
		report: EvalReport = EvalReport(profile_name=profile_name)
		total: int = len(questions)

		for i, q in enumerate(questions, 1):
			if verbose:
				print(f"\n[{i}/{total}] 评估: {q['id']} ({q['dimension']})")
				print(f"  问题: {q['question']}")

			# --- 获取智能体回复（含重试机制） ---
			response: str = ""
			for attempt in range(_MAX_RETRIES):
				try:
					response = get_response(str(q["question"]))
					break
				except Exception:
					if attempt == _MAX_RETRIES - 1:
						# 最后一次重试也失败，用占位文本
						response = "[错误：无法获取回复]"
					else:
						time.sleep(_RETRY_DELAY)

			if verbose:
				preview: str = response[:80].replace("\n", " ")
				print(f"  回复: {preview}...")

			# --- LLM-as-Judge 评分 ---
			eval_result: EvalResult = self.evaluate_one(
				profile_yaml_raw, q, response,
			)

			if eval_result.parse_error:
				print(f"  ⚠ 解析失败: {eval_result.parse_error}")
			elif verbose:
				print(
					f"  得分: 身份={eval_result.identity} "
					f"风格={eval_result.style} "
					f"知识={eval_result.knowledge} "
					f"时代={eval_result.era} "
					f"综合={eval_result.overall}"
				)

			report.results.append(eval_result)
			# 避免连续调用触发频率限制
			time.sleep(_API_DELAY)

		return report


	@staticmethod
	def print_report(report: EvalReport) -> None:
		"""
		在终端打印评估报告摘要：各维度均值 + 逐题不足。

		Args:
			report: evaluate_all() 返回的 EvalReport。
		"""
		print("\n" + "=" * 60)
		print(f"  评估报告 — {report.profile_name}")
		print("=" * 60)
		print(f"  测试题目数: {len(report.results)}")
		print(f"  身份一致性 均值: {report.avg_identity}")
		print(f"  风格匹配度 均值: {report.avg_style}")
		print(f"  知识准确性 均值: {report.avg_knowledge}")
		print(f"  时代契合度 均值: {report.avg_era}")
		print(f"  ─────────────────────────────")
		print(f"  综合得分 均值: {report.avg_overall}")
		print("=" * 60)

		for r in report.results:
			if r.parse_error:
				print(f"\n  [{r.question_id}] ❌ 评估失败: {r.parse_error}")
				continue
			if r.weaknesses:
				print(f"\n  [{r.question_id}] ⚠ {r.weaknesses}")


# ---- 便捷函数 ----

def run_evaluation(
		profile_name: str,
		enable_few_shot: bool = False,
		enable_cot: bool = False,
) -> EvalReport:
	"""
	一键运行完整评估流程。

	流程：加载角色 YAML → 加载测试问题 → 逐题对话
	→ LLM-as-Judge 评分 → 打印报告。

	Args:
		profile_name: 角色名。
		enable_few_shot: 是否启用 Few-shot 示例。
		enable_cot: 是否启用 Chain-of-Thought 推理。

	Returns:
		评估报告。
	"""
	base_dir: Path = get_prj_root()

	# 加载角色 YAML（原始文本供 judge 参考）
	profile_path: Path = base_dir / "data" / "profiles" / f"{profile_name}.yaml"
	with open(profile_path, encoding="utf-8") as f:
		profile_yaml_raw: str = f.read()
	profile: dict[str, Any] = yaml.safe_load(profile_yaml_raw)

	# 加载测试问题
	test_path: Path = base_dir / "data" / "eval" / "test_questions.json"
	with open(test_path, encoding="utf-8") as f:
		questions: list[dict[str, Any]] = json.load(f)["questions"]

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
	system_prompt: str = pm.render(
		"profile.j2",
		profile=profile,
		user_name=cfg.profile.user_name_placeholder,
		enable_few_shot=enable_few_shot,
		enable_cot=enable_cot,
	)
	session: ChatSession = ChatSession(llm, system_prompt)


	def get_response(question: str) -> str:
		return session.send(question)


	# 运行评估
	evaluator: Evaluator = Evaluator(llm, pm)
	report: EvalReport = evaluator.evaluate_all(
		profile_name=profile_name,
		profile_yaml_raw=profile_yaml_raw,
		questions=questions,
		get_response=get_response,
	)
	evaluator.print_report(report)
	return report


if __name__ == '__main__':
	run_evaluation("luxun")
