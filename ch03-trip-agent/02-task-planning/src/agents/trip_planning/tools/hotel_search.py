"""Mock 酒店查询工具 — 按城市、日期、预算返回逼真酒店列表。

覆盖城市：北京、上海、广州、成都、杭州、三亚、西安、昆明。
按预算档位返回不同档次酒店。
"""

from __future__ import annotations

import hashlib
import json

from inherit.llm.tool_registry import ToolDef

# 各城市的酒店模板
_HOTEL_DATA: dict[str, list[dict]] = {
	"北京": [
		{"name": "北京王府井希尔顿酒店", "area": "王府井", "rating": 4.8, "price_per_night": 1200,
		 "features": "市中心/地铁直达/含早"},
		{"name": "北京国贸大酒店", "area": "国贸CBD", "rating": 4.9, "price_per_night": 1800,
		 "features": "天际线景观/行政酒廊/商务"},
		{"name": "北京南锣鼓巷四合院客栈", "area": "南锣鼓巷", "rating": 4.6, "price_per_night": 500,
		 "features": "老北京风情/特色民宿/胡同"},
		{"name": "北京如家精选（前门店）", "area": "前门", "rating": 4.2, "price_per_night": 280,
		 "features": "经济实惠/地铁旁/干净整洁"},
		{"name": "北京颐和安缦酒店", "area": "颐和园", "rating": 4.9, "price_per_night": 3500,
		 "features": "皇家园林/奢华体验/私密空间"},
	],
	"上海": [
		{"name": "上海外滩华尔道夫酒店", "area": "外滩", "rating": 4.9, "price_per_night": 2200,
		 "features": "外滩江景/历史建筑/奢华"},
		{"name": "上海静安香格里拉", "area": "静安寺", "rating": 4.7, "price_per_night": 1400,
		 "features": "市中心/购物便利/商务"},
		{"name": "上海豫园万丽酒店", "area": "豫园", "rating": 4.5, "price_per_night": 700,
		 "features": "老城厢/近豫园/性价比高"},
		{"name": "上海汉庭（南京东路店）", "area": "南京东路", "rating": 4.0, "price_per_night": 250,
		 "features": "步行街旁/经济/交通方便"},
	],
	"广州": [
		{"name": "广州四季酒店", "area": "珠江新城", "rating": 4.9, "price_per_night": 1600,
		 "features": "小蛮腰景观/云端体验/奢华"},
		{"name": "广州花园酒店", "area": "环市东路", "rating": 4.6, "price_per_night": 600,
		 "features": "园林式/老牌五星/粤式早茶"},
		{"name": "广州长隆酒店", "area": "番禺长隆", "rating": 4.7, "price_per_night": 900,
		 "features": "亲子/近乐园/主题房间"},
	],
	"成都": [
		{"name": "成都博舍酒店", "area": "太古里", "rating": 4.8, "price_per_night": 1600,
		 "features": "设计感/太古里旁/网红打卡"},
		{"name": "成都锦江宾馆", "area": "锦江畔", "rating": 4.5, "price_per_night": 500,
		 "features": "老牌国宾/近春熙路/园林"},
		{"name": "成都宽窄巷子精品客栈", "area": "宽窄巷子", "rating": 4.4, "price_per_night": 350,
		 "features": "景区内/川西风格/拍照好看"},
		{"name": "成都背包十年青年旅舍", "area": "春熙路", "rating": 4.3, "price_per_night": 60,
		 "features": "青年旅舍/社交氛围/超高性价比"},
	],
	"杭州": [
		{"name": "杭州西子湖四季酒店", "area": "西湖", "rating": 4.9, "price_per_night": 2500,
		 "features": "西湖畔/园林景观/顶级奢华"},
		{"name": "杭州法云安缦", "area": "灵隐", "rating": 4.9, "price_per_night": 3000,
		 "features": "禅意/山林间/隐世体验"},
		{"name": "杭州悦榕庄", "area": "西溪湿地", "rating": 4.7, "price_per_night": 1500,
		 "features": "湿地景观/度假/水疗"},
		{"name": "杭州西湖亚朵酒店", "area": "湖滨", "rating": 4.5, "price_per_night": 400,
		 "features": "近西湖/文艺风/性价比"},
	],
	"三亚": [
		{"name": "三亚亚特兰蒂斯酒店", "area": "海棠湾", "rating": 4.8, "price_per_night": 2500,
		 "features": "水世界/海洋馆/亲子首选"},
		{"name": "三亚艾迪逊酒店", "area": "海棠湾", "rating": 4.7, "price_per_night": 1800,
		 "features": "时尚设计/私人沙滩/网红"},
		{"name": "三亚亚龙湾万豪", "area": "亚龙湾", "rating": 4.6, "price_per_night": 900,
		 "features": "一线海景/沙滩/度假"},
		{"name": "三亚海棠湾民生威斯汀", "area": "海棠湾", "rating": 4.4, "price_per_night": 600,
		 "features": "家庭友好/泳池/性价比"},
	],
	"西安": [
		{"name": "西安索菲特传奇酒店", "area": "钟楼", "rating": 4.8, "price_per_night": 1200,
		 "features": "历史建筑/市中心/法式优雅"},
		{"name": "西安威斯汀大酒店", "area": "大雁塔", "rating": 4.6, "price_per_night": 700,
		 "features": "大雁塔景观/唐风设计"},
		{"name": "西安钟楼饭店", "area": "钟楼", "rating": 4.3, "price_per_night": 350,
		 "features": "钟楼旁/老牌饭店/位置绝佳"},
		{"name": "西安回民街民宿", "area": "回民街", "rating": 4.2, "price_per_night": 150,
		 "features": "美食街旁/烟火气/经济实惠"},
	],
	"昆明": [
		{"name": "昆明洲际酒店", "area": "滇池", "rating": 4.7, "price_per_night": 800,
		 "features": "滇池景观/度假/环境优美"},
		{"name": "昆明翠湖宾馆", "area": "翠湖", "rating": 4.5, "price_per_night": 450,
		 "features": "翠湖旁/老牌国宾/红嘴鸥观赏"},
		{"name": "昆明花之城豪生", "area": "盘龙区", "rating": 4.3, "price_per_night": 300,
		 "features": "花卉主题/性价比/适合中转"},
	],
}


def _hex_seed(s: str) -> int:
	"""将字符串转换为 0-99 的伪随机种子。"""
	return int(hashlib.md5(s.encode()).hexdigest()[:4], 16) % 100


class HotelSearch:
	"""Mock 酒店查询工具 — 按城市、日期、预算返回逼真酒店列表。"""


	def search(
			self,
			city: str,
			checkin: str = "",
			checkout: str = "",
			budget_range: str = "",
			preference: str = "",
	) -> str:
		"""搜索城市酒店。

		:param city:         城市名称
		:param checkin:      入住日期 YYYY-MM-DD
		:param checkout:     退房日期 YYYY-MM-DD
		:param budget_range: 预算范围，如 "300-600" 表示每晚 300-600 元
		:param preference:   偏好，如 "亲子"、"商务"、"海景"
		:return: JSON 字符串
		"""
		matched_city: str | None = None
		for key in _HOTEL_DATA:
			if key in city or city in key:
				matched_city = key
				break

		if matched_city is None:
			# 尝试模糊匹配
			for key in _HOTEL_DATA:
				seed: int = _hex_seed(city + key)
				if seed > 80:
					matched_city = key
					break

		if matched_city is None:
			return json.dumps({
				"error": f"暂未收录城市'{city}'的酒店数据。支持的城市：{', '.join(_HOTEL_DATA.keys())}",
			}, ensure_ascii=False)

		hotels: list[dict] = _HOTEL_DATA[matched_city]

		# 按预算过滤
		min_price: int = 0
		max_price: int = 99999
		if budget_range:
			parts: list[str] = budget_range.replace("元", "").replace("/晚", "").strip().split("-")
			try:
				if len(parts) == 2:
					min_price = int(parts[0].strip())
					max_price = int(parts[1].strip())
				elif len(parts) == 1:
					max_price = int(parts[0].strip())
			except ValueError:
				pass

		filtered: list[dict] = [h for h in hotels if min_price <= h["price_per_night"] <= max_price]
		note: str
		if not filtered:
			# 如果预算过滤后为空，返回全量并加提示
			filtered = hotels
			note = f"（注意：预算{min_price}-{max_price}元/晚范围内无匹配酒店，已展示全部）"
		else:
			note = ""

		results: list[dict] = []
		for h in filtered:
			entry: dict = {
				"name": h["name"],
				"area": h["area"],
				"city": matched_city,
				"rating": h["rating"],
				"price_per_night": h["price_per_night"],
				"features": h["features"],
			}
			if checkin and checkout:
				entry["checkin"] = checkin
				entry["checkout"] = checkout
				try:
					days: int = max(1, (__import__("datetime").datetime.strptime(checkout, "%Y-%m-%d")
					                    - __import__("datetime").datetime.strptime(checkin, "%Y-%m-%d")).days)
				except Exception:
					days = 1
				entry["total_price"] = h["price_per_night"] * days
				entry["nights"] = days
			results.append(entry)

		if note:
			return json.dumps({"hotels": results, "count": len(results), "note": note}, ensure_ascii=False, indent=2)
		return json.dumps({"hotels": results, "count": len(results)}, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="hotel_search",
			description=(
				"搜索城市酒店住宿信息，返回酒店名称、区域、评分、价格、特色等。"
				"可按预算范围过滤。"
			),
			parameters={
				"city": {
					"type": "string",
					"description": "城市名称，如'成都'、'三亚'",
				},
				"checkin": {
					"type": "string",
					"description": "入住日期 YYYY-MM-DD",
				},
				"checkout": {
					"type": "string",
					"description": "退房日期 YYYY-MM-DD",
				},
				"budget_range": {
					"type": "string",
					"description": "每晚预算范围，如'300-600'表示300到600元/晚",
				},
				"preference": {
					"type": "string",
					"description": "偏好类型，如'亲子'、'商务'、'海景'、'性价比'",
				},
			},
			required=["city"],
			func=self.search,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  HotelSearch 演示")
	print("=" * 60)

	tool: HotelSearch = HotelSearch()

	print('\n🏨  search(city="成都", checkin="2026-07-20", checkout="2026-07-23", budget_range="300-600")')
	result: str = tool.search("成都", "2026-07-20", "2026-07-23", "300-600")
	print(f"   {result[:400]}...")

	print('\n🏨  search(city="三亚", checkin="2026-08-01", checkout="2026-08-03", preference="海景")')
	result = tool.search("三亚", "2026-08-01", "2026-08-03", preference="海景")
	print(f"   {result[:400]}...")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
