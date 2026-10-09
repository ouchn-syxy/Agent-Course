"""Mock 景点查询工具 — 按城市和偏好返回逼真景点列表。

覆盖城市：北京、上海、广州、成都、杭州、三亚、西安、昆明。
按自然风光/人文历史/美食购物/亲子休闲等偏好分类。
"""

from __future__ import annotations

import json

from inherit.llm.tool_registry import ToolDef

_ATTRACTION_DATA: dict[str, list[dict]] = {
	"北京": [
		{"name": "故宫博物院", "category": "人文历史", "rating": 4.9, "duration": "4-6小时",
		 "address": "北京市东城区景山前街4号", "ticket": "60元", "description": "明清皇宫，世界最大的宫殿建筑群"},
		{"name": "八达岭长城", "category": "人文历史", "rating": 4.8, "duration": "半天",
		 "address": "北京市延庆区G6京藏高速58号出口", "ticket": "40元", "description": "万里长城精华段，世界文化遗产"},
		{"name": "颐和园", "category": "自然风光", "rating": 4.7, "duration": "3-4小时",
		 "address": "北京市海淀区新建宫门路19号", "ticket": "30元", "description": "皇家园林，昆明湖与万寿山"},
		{"name": "天坛公园", "category": "人文历史", "rating": 4.7, "duration": "2-3小时",
		 "address": "北京市东城区天坛路甲1号", "ticket": "15元", "description": "明清祭天场所，祈年殿为标志性建筑"},
		{"name": "798艺术区", "category": "文艺打卡", "rating": 4.4, "duration": "2-4小时",
		 "address": "北京市朝阳区酒仙桥路4号", "ticket": "免费", "description": "当代艺术聚集地，工业遗址改造"},
		{"name": "南锣鼓巷", "category": "美食购物", "rating": 4.3, "duration": "1-2小时",
		 "address": "北京市东城区南锣鼓巷", "ticket": "免费", "description": "老北京胡同文化，特色小店和美食"},
	],
	"上海": [
		{"name": "外滩", "category": "人文历史", "rating": 4.8, "duration": "1-2小时",
		 "address": "上海市黄浦区中山东一路", "ticket": "免费", "description": "万国建筑博览群，黄浦江夜景绝佳"},
		{"name": "上海迪士尼乐园", "category": "亲子休闲", "rating": 4.7, "duration": "一整天",
		 "address": "上海市浦东新区川沙镇", "ticket": "475元起", "description": "中国大陆首座迪士尼主题乐园"},
		{"name": "豫园", "category": "人文历史", "rating": 4.5, "duration": "2-3小时",
		 "address": "上海市黄浦区福佑路168号", "ticket": "40元", "description": "明代江南私家园林，城隍庙商圈"},
	],
	"广州": [
		{"name": "广州塔（小蛮腰）", "category": "文艺打卡", "rating": 4.5, "duration": "2-3小时",
		 "address": "广州市海珠区阅江西路222号", "ticket": "150元起", "description": "600米地标，360°俯瞰羊城"},
		{"name": "长隆野生动物世界", "category": "亲子休闲", "rating": 4.8, "duration": "一整天",
		 "address": "广州市番禺区大石镇", "ticket": "300元", "description": "亚洲最大的野生动物主题公园"},
		{"name": "沙面岛", "category": "人文历史", "rating": 4.4, "duration": "1-2小时",
		 "address": "广州市荔湾区沙面岛", "ticket": "免费", "description": "欧陆风情建筑群，拍照圣地"},
	],
	"成都": [
		{"name": "大熊猫繁育研究基地", "category": "亲子休闲", "rating": 4.8, "duration": "半天",
		 "address": "成都市成华区熊猫大道1375号", "ticket": "55元", "description": "近距离观察国宝大熊猫，必去景点"},
		{"name": "都江堰景区", "category": "人文历史", "rating": 4.7, "duration": "半天",
		 "address": "成都市都江堰市公园路", "ticket": "80元", "description": "世界文化遗产，千年水利工程奇迹"},
		{"name": "宽窄巷子", "category": "美食购物", "rating": 4.5, "duration": "2-3小时",
		 "address": "成都市青羊区宽窄巷子", "ticket": "免费", "description": "成都标志性文化街区，茶馆与美食"},
		{"name": "锦里古街", "category": "美食购物", "rating": 4.4, "duration": "1-2小时",
		 "address": "成都市武侯区武侯祠大街231号", "ticket": "免费", "description": "三国文化主题街区，小吃与手工艺品"},
		{"name": "青城山", "category": "自然风光", "rating": 4.7, "duration": "一天",
		 "address": "成都市都江堰市青城山镇", "ticket": "90元", "description": "道教名山，前山人文后山自然"},
		{"name": "武侯祠", "category": "人文历史", "rating": 4.5, "duration": "2-3小时",
		 "address": "成都市武侯区武侯祠大街231号", "ticket": "50元", "description": "三国文化圣地，诸葛亮纪念祠堂"},
		{"name": "春熙路", "category": "美食购物", "rating": 4.3, "duration": "1-3小时",
		 "address": "成都市锦江区春熙路", "ticket": "免费", "description": "成都最繁华商业街，IFS、太古里"},
		{"name": "九寨沟", "category": "自然风光", "rating": 4.9, "duration": "2-3天",
		 "address": "四川省阿坝州九寨沟县", "ticket": "169元起", "description": "世界自然遗产，童话世界般的山水"},
	],
	"杭州": [
		{"name": "西湖风景名胜区", "category": "自然风光", "rating": 4.8, "duration": "一天",
		 "address": "杭州市西湖区龙井路1号", "ticket": "免费（部分景点收费）",
		 "description": "世界文化遗产，淡妆浓抹总相宜"},
		{"name": "灵隐寺", "category": "人文历史", "rating": 4.7, "duration": "2-3小时",
		 "address": "杭州市西湖区法云弄1号", "ticket": "75元", "description": "千年古刹，江南禅宗名寺"},
		{"name": "西溪国家湿地公园", "category": "自然风光", "rating": 4.5, "duration": "半天",
		 "address": "杭州市西湖区天目山路518号", "ticket": "80元", "description": "城市湿地，泛舟芦荡之间"},
	],
	"三亚": [
		{"name": "亚龙湾", "category": "自然风光", "rating": 4.7, "duration": "半天",
		 "address": "三亚市亚龙湾国家旅游度假区", "ticket": "免费", "description": "天下第一湾，沙白水清，适合游泳"},
		{"name": "蜈支洲岛", "category": "自然风光", "rating": 4.8, "duration": "一天",
		 "address": "三亚市海棠湾镇", "ticket": "144元", "description": "潜水胜地，海水能见度极高"},
		{"name": "南山文化旅游区", "category": "人文历史", "rating": 4.6, "duration": "半天",
		 "address": "三亚市崖城镇南山村", "ticket": "129元", "description": "108米海上观音像，佛教文化"},
		{"name": "天涯海角", "category": "自然风光", "rating": 4.3, "duration": "2-3小时",
		 "address": "三亚市天涯区", "ticket": "81元", "description": "经典地标，海天一色适合拍照"},
	],
	"西安": [
		{"name": "秦始皇兵马俑博物馆", "category": "人文历史", "rating": 4.9, "duration": "半天",
		 "address": "西安市临潼区秦陵北路", "ticket": "120元", "description": "世界第八大奇迹，秦代军事阵列"},
		{"name": "大雁塔·大唐不夜城", "category": "文艺打卡", "rating": 4.6, "duration": "3-4小时",
		 "address": "西安市雁塔区慈恩路66号", "ticket": "免费（登塔收费）", "description": "唐代文化地标，夜间灯光秀"},
		{"name": "西安城墙", "category": "人文历史", "rating": 4.7, "duration": "2-4小时",
		 "address": "西安市中心", "ticket": "54元", "description": "中国现存最完整古城墙，可骑行一圈"},
		{"name": "华山", "category": "自然风光", "rating": 4.8, "duration": "1-2天",
		 "address": "渭南市华阴市华山镇", "ticket": "160元", "description": "五岳之西岳，险峻著称，长空栈道"},
	],
	"昆明": [
		{"name": "石林风景区", "category": "自然风光", "rating": 4.6, "duration": "一天",
		 "address": "昆明市石林彝族自治县", "ticket": "130元", "description": "世界自然遗产，喀斯特地貌奇观"},
		{"name": "滇池·西山", "category": "自然风光", "rating": 4.5, "duration": "半天",
		 "address": "昆明市西山区", "ticket": "免费（西山索道另收费）", "description": "高原明珠，冬季红嘴鸥聚集"},
		{"name": "云南民族村", "category": "人文历史", "rating": 4.3, "duration": "半天",
		 "address": "昆明市西山区滇池路1310号", "ticket": "90元", "description": "25个少数民族文化风俗展示"},
	],
}


class AttractionSearch:
	"""Mock 景点查询工具 — 按城市和偏好返回逼真景点列表。"""


	def search(
			self,
			city: str,
			category: str = "",
			limit: int = 10,
	) -> str:
		"""搜索城市景点。

		:param city:     城市名称
		:param category: 景点分类筛选：自然风光/人文历史/美食购物/亲子休闲/文艺打卡
		:param limit:    最大返回数量
		:return: JSON 字符串
		"""
		matched_city: str | None = None
		for key in _ATTRACTION_DATA:
			if key in city or city in key:
				matched_city = key
				break

		if matched_city is None:
			return json.dumps({
				"error": f"暂未收录城市'{city}'的景点数据。支持的城市：{', '.join(_ATTRACTION_DATA.keys())}",
			}, ensure_ascii=False)

		all_attractions: list[dict] = _ATTRACTION_DATA[matched_city]

		results: list[dict]
		if category:
			cats: list[str] = [c.strip() for c in category.replace("、", ",").replace("/", ",").split(",")]
			filtered: list[dict] = [a for a in all_attractions
			                        if any(c in a["category"] or a["category"] in c for c in cats)]
			if not filtered:
				return json.dumps({
					"note": f"未找到类别'{category}'的景点，已展示{city}全部景点。"
					        f"可用类别：自然风光、人文历史、美食购物、亲子休闲、文艺打卡",
					"attractions": all_attractions[:limit],
					"count": min(len(all_attractions), limit),
				}, ensure_ascii=False, indent=2)
			results = filtered[:limit]
		else:
			results = all_attractions[:limit]

		# 去重输出字段
		output: list[dict] = []
		for a in results:
			output.append({
				"name": a["name"],
				"category": a["category"],
				"rating": a["rating"],
				"duration": a["duration"],
				"address": a["address"],
				"ticket": a["ticket"],
				"description": a["description"],
			})

		return json.dumps({
			"city": matched_city,
			"attractions": output,
			"count": len(output),
		}, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="attraction_search",
			description=(
				"搜索城市景点信息，返回景点名称、类别、评分、建议游玩时长、地址、门票、简介。"
				"可按类别筛选（自然风光/人文历史/美食购物/亲子休闲/文艺打卡）。"
			),
			parameters={
				"city": {
					"type": "string",
					"description": "城市名称，如'成都'、'西安'",
				},
				"category": {
					"type": "string",
					"description": "类别筛选：自然风光、人文历史、美食购物、亲子休闲、文艺打卡。不传则返回全部。",
				},
				"limit": {
					"type": "integer",
					"description": "最大返回数量，默认10",
					"default": 10,
				},
			},
			required=["city"],
			func=self.search,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  AttractionSearch 演示")
	print("=" * 60)

	tool: AttractionSearch = AttractionSearch()

	print('\n🎯  search(city="成都", category="自然风光", limit=3)')
	result: str = tool.search("成都", "自然风光", limit=3)
	print(f"   {result[:400]}...")

	print('\n🎯  search(city="西安", category="人文历史", limit=3)')
	result = tool.search("西安", "人文历史", limit=3)
	print(f"   {result[:400]}...")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
