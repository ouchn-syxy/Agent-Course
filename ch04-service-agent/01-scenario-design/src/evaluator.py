"""评估器 — 基于 sample_messages.json 标注数据评估分类器和策略引擎。

流程：
  1. 加载 sample_messages.json（22 条人工标注样本）
  2. 逐条调用 MessageClassifier.classify()
  3. 对比预测结果与标注 label（大类、子类、情感、紧急度）
  4. 输出逐条明细 + 汇总准确率

用法:
    python main.py --eval
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.eshop_service.message_classifier import MessageClassifier
from agents.eshop_service.models.types import ConversationMessage, MessageClassificationResult
from agents.eshop_service.strategy_engine import StrategyEngine
from inherit.utils.path import get_prj_root

_SAMPLE_PATH: Path = get_prj_root() / "data" / "sample_messages.json"


# ============================================================
# 逐条评估
# ============================================================

def evaluate(
		classifier: MessageClassifier,
		engine: StrategyEngine,
		sample_path: Path | None = None,
) -> None:
	"""加载样本集，逐条分类并对比标注，输出评估报告。

	:param classifier: 已初始化的消息分类器
	:param engine: 已初始化的策略引擎
	:param sample_path: 样本文件路径，默认 data/sample_messages.json
	"""
	path = sample_path or _SAMPLE_PATH
	if not path.exists():
		print(f"❌ 样本文件不存在：{path}")
		return

	with open(path, encoding="utf-8") as f:
		samples: list[dict] = json.load(f)

	# ── 统计维度 ──
	total = len(samples)
	parent_correct = 0
	name_correct = 0
	sentiment_correct = 0
	urgency_correct = 0
	response_mode_correct = 0
	errors: list[dict] = []

	print("=" * 70)
	print("  📊 分类器评估报告")
	print(f"  样本集: {path.name}  |  共 {total} 条")
	print("=" * 70)

	for i, sample in enumerate(samples, 1):
		msg_id = sample["id"]
		label = sample["label"]
		conversation_raw = sample["conversation"]

		# 构造 ConversationMessage 列表
		conversation = [
			ConversationMessage(role=m["role"], content=m["content"])
			for m in conversation_raw
		]

		# ── 分类 ──
		result: MessageClassificationResult = classifier.classify(conversation)
		decision = engine.decide(conversation, result)

		# ── 逐字段对比 ──
		p_ok = result.parent == label["parent"]
		n_ok = result.name == label["name"]
		s_ok = result.sentiment == label["sentiment"]
		u_ok = result.urgency == label["urgency"]

		# response_mode 对比：根据子类的预设策略判断预期模式
		expected_mode = decision.response_mode.value if hasattr(decision, 'response_mode') else None

		if p_ok:
			parent_correct += 1
		if n_ok:
			name_correct += 1
		if s_ok:
			sentiment_correct += 1
		if u_ok:
			urgency_correct += 1

		# ── 逐条输出 ──
		status = "✅" if (p_ok and n_ok and s_ok and u_ok) else "❌"
		buyer_msg = conversation_raw[0]["content"][:50]
		print(f"\n[{i:02d}/{total}] {status} {msg_id}")
		print(f"  消息: {buyer_msg}{'...' if len(conversation_raw[0]['content']) > 50 else ''}")
		print(f"  标注大类: {label['parent']:<10s}  预测大类: {result.parent}")
		print(f"  标注子类: {label['name']:<10s}  预测子类: {result.name}")
		print(f"  标注情感: {label['sentiment']:<6s}  预测情感: {result.sentiment}")
		print(f"  标注紧急: {label['urgency']:<6s}  预测紧急: {result.urgency}")
		print(f"  回复模式: {decision.response_mode.value}  |  置信度: {result.confidence:.2f}")

		if not (p_ok and n_ok and s_ok and u_ok):
			diffs = []
			if not p_ok:
				diffs.append(f"大类: {label['parent']}→{result.parent}")
			if not n_ok:
				diffs.append(f"子类: {label['name']}→{result.name}")
			if not s_ok:
				diffs.append(f"情感: {label['sentiment']}→{result.sentiment}")
			if not u_ok:
				diffs.append(f"紧急: {label['urgency']}→{result.urgency}")
			print(f"  ⚠️ 差异: {', '.join(diffs)}")
			errors.append({"id": msg_id, "diffs": diffs})

	# ── 汇总 ──
	print("\n" + "=" * 70)
	print("  📈 汇总统计")
	print("=" * 70)
	print(f"  大类准确率:   {parent_correct}/{total}  =  {parent_correct / total * 100:.1f}%")
	print(f"  子类准确率:   {name_correct}/{total}  =  {name_correct / total * 100:.1f}%")
	print(f"  情感准确率:   {sentiment_correct}/{total}  =  {sentiment_correct / total * 100:.1f}%")
	print(f"  紧急度准确率: {urgency_correct}/{total}  =  {urgency_correct / total * 100:.1f}%")

	fully_correct = total - len(errors)
	print(f"  全对样本数:   {fully_correct}/{total}  =  {fully_correct / total * 100:.1f}%")

	if errors:
		print(f"\n  差异样本 ({len(errors)} 条):")
		for e in errors:
			print(f"    {e['id']}: {', '.join(e['diffs'])}")

	print()
