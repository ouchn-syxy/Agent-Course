"""Mock 航班查询工具 — 参数化生成逼真航班数据。

支持城市对：北京、上海、广州、成都、杭州、三亚、西安、昆明。
按日期和城市对返回确定性的航班列表（含航司、航班号、时间、价格）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from inherit.llm.tool_registry import ToolDef

_MOCK_AIRLINES: list[tuple[str, str, float]] = [
	("中国国航", "CA", 1.0),
	("南方航空", "CZ", 0.95),
	("东方航空", "MU", 0.9),
	("海南航空", "HU", 0.85),
	("春秋航空", "9C", 0.55),
	("吉祥航空", "HO", 0.75),
	("厦门航空", "MF", 0.8),
	("四川航空", "3U", 0.7),
]

# 城市对基准价格（元）
_PRICE_MATRIX: dict[tuple[str, str], int] = {
	("北京", "上海"): 800,
	("北京", "成都"): 1200,
	("北京", "三亚"): 1800,
	("北京", "西安"): 600,
	("北京", "昆明"): 1500,
	("上海", "成都"): 1300,
	("上海", "三亚"): 1600,
	("上海", "西安"): 900,
	("上海", "昆明"): 1400,
	("广州", "成都"): 1000,
	("广州", "三亚"): 500,
	("广州", "西安"): 1100,
	("广州", "昆明"): 800,
	("成都", "三亚"): 1200,
	("成都", "西安"): 500,
	("成都", "昆明"): 400,
	("杭州", "成都"): 1100,
	("杭州", "三亚"): 1400,
	("杭州", "西安"): 800,
	("杭州", "昆明"): 1200,
}


def _get_price(city_from: str, city_to: str, base_price: int) -> int:
	"""根据日期种子偏移价格，制造±20%波动。"""
	seed = int(hashlib.md5(f"{city_from}{city_to}".encode()).hexdigest()[:8], 16)
	offset = (seed % 41) - 20  # -20 ~ +20
	return max(200, base_price + offset * (base_price // 100))


def _parse_date(s: str) -> date:
	"""解析 YYYY-MM-DD 格式日期，带基本校验。"""
	try:
		return datetime.strptime(s, "%Y-%m-%d").date()
	except ValueError:
		today = date.today()
		return today


class FlightSearch:
	"""Mock 航班查询工具 — 参数化生成逼真航班数据。"""


	def search(
			self,
			city_from: str,
			city_to: str,
			date_str: str = "",
	) -> str:
		"""搜索城市间航班。

		返回 JSON 格式的航班列表，含航司、航班号、时间、价格。

		:param city_from: 出发城市
		:param city_to:   到达城市
		:param date_str:  出发日期（YYYY-MM-DD），不传默认当天
		:return: JSON 字符串
		"""
		if city_from.strip() == city_to.strip():
			return json.dumps(
				{"error": f"出发城市与到达城市相同（{city_from}），请检查输入"},
				ensure_ascii=False,
			)

		base = 0
		for (a, b), p in _PRICE_MATRIX.items():
			if (a in city_from and b in city_to) or (a in city_to and b in city_from):
				base = p
				break

		if base == 0:
			base = 800  # 未知城市对默认价

		travel_date: date = _parse_date(date_str) if date_str else date.today()
		date_seed: int = travel_date.toordinal()

		flights: list[dict] = []
		for i, (airline, code, multiplier) in enumerate(_MOCK_AIRLINES):
			price: int = int(_get_price(city_from, city_to, base) * multiplier)
			# 每家航司生成 2-3 个航班
			num_flights: int = 2 if i >= len(_MOCK_AIRLINES) - 2 else 3
			for j in range(num_flights):
				hour: int = 7 + (i * 3 + j * 5) % 14
				minute: int = (i * 7 + j * 23) % 60
				dep_time: str = f"{hour:02d}:{minute:02d}"
				arr_hour: int = hour + 1 + (base // 400)  # 航程约 1-4 小时
				arr_minute: int = (minute + 15) % 60
				arr_time: str = f"{arr_hour:02d}:{arr_minute:02d}"
				flights.append({
					"airline": airline,
					"flight_no": f"{code}{3000 + i * 10 + j + (date_seed % 100)}",
					"departure": dep_time,
					"arrival": arr_time,
					"price": price + j * 50,
					"city_from": city_from.strip(),
					"city_to": city_to.strip(),
					"date": date_str or str(date.today()),
				})

		flights.sort(key=lambda f: f["price"])
		return json.dumps({"flights": flights, "count": len(flights)}, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="flight_search",
			description=(
				"搜索城市间航班信息，返回航司、航班号、起降时间、"
				"价格等结构化数据。支持单程查询。"
			),
			parameters={
				"city_from": {
					"type": "string",
					"description": "出发城市名称，如'北京'、'上海'",
				},
				"city_to": {
					"type": "string",
					"description": "到达城市名称，如'成都'、'三亚'",
				},
				"date_str": {
					"type": "string",
					"description": "出发日期，格式 YYYY-MM-DD，如 '2026-05-01'",
				},
			},
			required=["city_from", "city_to"],
			func=self.search,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  FlightSearch 演示")
	print("=" * 60)

	tool: FlightSearch = FlightSearch()

	print('\n✈️  search(city_from="北京", city_to="成都", date_str="2026-07-20")')
	result: str = tool.search("北京", "成都", "2026-07-20")
	print(f"   {result[:400]}...")

	print('\n✈️  search(city_from="上海", city_to="三亚")')
	result = tool.search("上海", "三亚")
	print(f"   {result[:400]}...")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
