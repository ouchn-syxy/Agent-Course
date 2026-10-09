"""
记忆准确性评估器 —— 用 LLM-as-Judge 评估智能体短期记忆能力。

聚焦短期记忆质量：
  1. 信息回忆（recall）— 单次会话中能否正确回忆前文信息
  2. 上下文连贯（coherence）— 对话风格是否前后一致
  3. 防幻觉表现（anti_hallucination）— 记忆为空时是否诚实回答"不记得"

用法：
    python main.py --eval              # 运行全部评估
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from openai.types.chat import ChatCompletionUserMessageParam

from config import Config
from inherit.llm.client import LLMClient
from inherit.prompt.prompt_manager import PromptManager
from inherit.utils.path import get_prj_root
from llm.memory_chat_session import MemoryChatSession
from memory.conversation_memory import ConversationMemory


# ============================================================
# 数据模型
# ============================================================

@dataclass
class EvalResult:
	"""
	单题评估结果。

	当 LLM-as-Judge 返回的 JSON 解析成功时，三个维度分值和综合分被填充；
	解析失败时 parse_error 非空，维度分值保持默认 0。
	"""
	question_id: str
	dimension: str
	question: str
	response: str

	recall: int = 0  # 信息回忆 1-5
	coherence: int = 0  # 上下文连贯 1-5
	anti_hallucination: int = 0  # 防幻觉（5=无编造，1=完全编造）
	overall: float = 0.0  # 综合加权平均分

	analysis: str = ""  # Judge 分析说明
	parse_error: str = ""  # JSON 解析失败时的错误信息（非空表示该题评估无效）


@dataclass
class EvalReport:
	"""
	评估报告，聚合所有 EvalResult。

	提供三个维度的均值计算属性，排除 parse_error 的结果。
	"""
	profile_name: str
	results: list[EvalResult] = field(default_factory=list)


	@property
	def avg_recall(self) -> float:
		"""信息回忆均值。"""
		return self._avg("recall")


	@property
	def avg_coherence(self) -> float:
		"""上下文连贯均值。"""
		return self._avg("coherence")


	@property
	def avg_anti_hallucination(self) -> float:
		"""防幻觉均值。"""
		return self._avg("anti_hallucination")


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
	记忆准确性 LLM-as-Judge 评估器。

	使用独立的 LLM 调用对智能体回复进行三维度评分，
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
			setup_context: str,
			question: dict[str, Any],
			response: str,
	) -> EvalResult:
		"""
		对单次记忆问答进行三维度评估。

		Args:
			setup_context: 对话背景文本（用户之前说过的所有内容）。
			question: test_questions.json 中的单题对象。
			response: 智能体对该问题的回复文本。

		Returns:
			EvalResult 实例。解析成功时维度分值被填充，失败时 parse_error 非空。
		"""
		# 构建评估 prompt
		prompt: str = self._pm.render(
			"eval.j2",
			setup_context=setup_context,
			test_dimension=str(question.get("dimension_desc", question["dimension"])),
			user_question=str(question["question"]),
			agent_response=response,
			expected_info=str(question.get("expected_keywords", "")),
		)

		try:
			# 以低温度调用 LLM 做评估，保证评分稳定性
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
				recall=int(result.get("recall", 0)),
				coherence=int(result.get("coherence", 0)),
				anti_hallucination=int(result.get("anti_hallucination", 0)),
				overall=float(result.get("overall", 0)),
				analysis=str(result.get("analysis", "")),
			)
		except (json.JSONDecodeError, KeyError, ValueError) as e:
			# JSON 解析失败或字段缺失，返回带错误信息的空结果
			return EvalResult(
				question_id=str(question["id"]),
				dimension=str(question["dimension"]),
				question=str(question["question"]),
				response=response,
				parse_error=str(e),
			)


	def evaluate_all(
			self,
			profile_name: str,
			questions: list[dict[str, Any]],
			get_response: Callable[[dict[str, Any]], str],
			verbose: bool = True,
	) -> EvalReport:
		"""
		批量评估所有测试问题，生成报告。

		Args:
			profile_name: 角色名。
			questions: 测试问题列表（来自 test_questions.json["questions"]）。
			get_response: 可调用对象，签名 (question_dict) -> str。
			verbose: 是否在终端打印逐题进度。

		Returns:
			聚合所有 EvalResult 的 EvalReport。
		"""
		report: EvalReport = EvalReport(profile_name=profile_name)
		total: int = len(questions)

		for i, q in enumerate(questions, 1):
			setup_count: int = len(q.get("setup", []))
			if verbose:
				print(f"\n[{i}/{total}] 评估: {q['id']} ({q['dimension']})")
				print(f"  Setup: {setup_count} 轮 → 问题: {q['question']}")

			# --- 获取智能体回复（含重试机制） ---
			response: str = ""
			for attempt in range(_MAX_RETRIES):
				try:
					response = get_response(q)
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

			# 构建对话背景文本（供 judge 参考）
			setup_text: str = "\n".join(
				f"用户: {m['content']}" for m in q.get("setup", [])
			)

			# --- LLM-as-Judge 评分 ---
			eval_result: EvalResult = self.evaluate_one(
				setup_text, q, response,
			)

			if eval_result.parse_error:
				print(f"  ⚠ 解析失败: {eval_result.parse_error}")
			elif verbose:
				print(
					f"  得分: 回忆={eval_result.recall} "
					f"连贯={eval_result.coherence} "
					f"防幻觉={eval_result.anti_hallucination} "
					f"综合={eval_result.overall}"
				)

			report.results.append(eval_result)
			# 避免连续调用触发频率限制
			time.sleep(_API_DELAY)

		return report


	@staticmethod
	def print_report(report: EvalReport) -> None:
		"""
		在终端打印评估报告摘要：各维度均值 + 逐题分析。

		Args:
			report: evaluate_all() 返回的 EvalReport。
		"""
		print("\n" + "=" * 60)
		print(f"  记忆准确性评估报告 — {report.profile_name}")
		print("=" * 60)
		print(f"  测试题目数: {len(report.results)}")
		print(f"  信息回忆 均值: {report.avg_recall}")
		print(f"  上下文连贯 均值: {report.avg_coherence}")
		print(f"  防幻觉表现 均值: {report.avg_anti_hallucination}")
		print(f"  {'─' * 50}")
		print(f"  综合得分 均值: {report.avg_overall}")
		print("=" * 60)

		for r in report.results:
			if r.parse_error:
				print(f"\n  [{r.question_id}] ❌ 评估失败: {r.parse_error}")
				continue
			if r.analysis:
				print(f"\n  [{r.question_id}] 📝 {r.analysis}")


# ---- 便捷函数 ----

def run_evaluation(
		profile_name: str,
		enable_few_shot: bool = False,
		enable_cot: bool = False,
) -> EvalReport:
	"""
	一键运行完整评估流程。

	流程：加载角色 YAML → 加载测试问题 → 逐题 setup+query
	→ LLM-as-Judge 评分 → 打印报告。

	Args:
		profile_name: 角色名。
		enable_few_shot: 是否启用 Few-shot 示例。
		enable_cot: 是否启用 Chain-of-Thought 推理。

	Returns:
		评估报告。
	"""
	base_dir: Path = get_prj_root()

	# 加载角色 YAML
	profile_path: Path = base_dir / "data" / "profiles" / f"{profile_name}.yaml"
	with open(profile_path, encoding="utf-8") as f:
		profile: dict[str, Any] = yaml.safe_load(f)

	# 加载测试问题
	test_path: Path = base_dir / "data" / "eval" / "test_questions.json"
	with open(test_path, encoding="utf-8") as f:
		questions: list[dict[str, Any]] = json.load(f)["questions"]

	cfg: Config = Config.from_yaml()

	llm = LLMClient(
		api_key=cfg.llm.api_key_env,
		base_url=cfg.llm.base_url,
		model=cfg.llm.model,
		temperature=cfg.generation.temperature,
		top_p=cfg.generation.top_p,
		max_tokens=cfg.generation.max_tokens,
	)

	# 初始化 PromptManager
	pm: PromptManager = PromptManager(base_dir / "prompts")
	system_prompt: str = pm.render(
		"profile.j2",
		profile=profile,
		enable_few_shot=enable_few_shot,
		enable_cot=enable_cot,
	)


	def get_response(q: dict[str, Any]) -> str:
		"""为每道题独立创建带记忆的会话：先 setup 再 query。"""
		memory: ConversationMemory = ConversationMemory(
			storage_dir=base_dir / "data" / "memories",
			session_id=f"{profile_name}_eval_{q['id']}",
			llm_client=llm,
			prompt_manager=pm,
			max_turns=cfg.memory.max_turns,
			max_tokens=cfg.memory.max_tokens,
		)
		session: MemoryChatSession = MemoryChatSession(llm, system_prompt, memory)

		for msg in q.get("setup", []):
			session.send(msg["content"])
			time.sleep(0.3)
		return session.send(q["question"])


	# 运行评估
	evaluator: Evaluator = Evaluator(llm, pm)
	report: EvalReport = evaluator.evaluate_all(
		profile_name=profile_name,
		questions=questions,
		get_response=get_response,
	)
	evaluator.print_report(report)
	return report


if __name__ == '__main__':
	run_evaluation("luxun")
