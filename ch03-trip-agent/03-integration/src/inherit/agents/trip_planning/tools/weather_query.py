"""天气查询工具 — 基于 Open-Meteo 免费 API，无需 API Key。

API: https://api.open-meteo.com/v1/forecast
支持全球城市经纬度查询，返回温度、降水概率、风速、天气代码等。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import requests

from inherit.llm.tool_registry import ToolDef
from inherit.utils.retry import retry

_OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"

# 常用中文城市名 → (lat, lon) 映射
_CITY_COORDS: dict[str, tuple[float, float]] = {
	"北京": (39.9042, 116.4074),
	"上海": (31.2304, 121.4737),
	"广州": (23.1291, 113.2644),
	"深圳": (22.5431, 114.0579),
	"成都": (30.5728, 104.0668),
	"杭州": (30.2741, 120.1551),
	"三亚": (18.2528, 109.5120),
	"西安": (34.3416, 108.9398),
	"昆明": (25.0389, 102.7183),
	"重庆": (29.4316, 106.9123),
	"武汉": (30.5928, 114.3055),
	"南京": (32.0603, 118.7969),
	"厦门": (24.4798, 118.0894),
	"青岛": (36.0671, 120.3826),
	"大连": (38.9140, 121.6147),
	"桂林": (25.2736, 110.2900),
	"丽江": (26.8721, 100.2299),
	"拉萨": (29.6500, 91.1000),
	"哈尔滨": (45.8038, 126.5350),
	"长沙": (28.2282, 112.9388),
}

# WMO Weather Code → 中文描述
_WMO_CODES: dict[int, str] = {
	0: "晴", 1: "大部晴", 2: "多云", 3: "阴",
	45: "雾", 48: "雾凇",
	51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
	61: "小雨", 63: "中雨", 65: "大雨",
	71: "小雪", 73: "中雪", 75: "大雪",
	80: "阵雨", 81: "中等阵雨", 82: "暴阵雨",
	95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴大冰雹",
}


def _resolve_city(city: str) -> tuple[str, float, float] | None:
	"""解析城市名 → (标准名, lat, lon)。模糊匹配。"""
	city_stripped = city.strip()
	# 精确匹配
	for name, coords in _CITY_COORDS.items():
		if city_stripped == name:
			return name, coords[0], coords[1]
	# 包含匹配
	for name, coords in _CITY_COORDS.items():
		if name in city_stripped or city_stripped in name:
			return name, coords[0], coords[1]
	# 去掉"市"再试
	if city_stripped.endswith("市"):
		base = city_stripped[:-1]
		for name, coords in _CITY_COORDS.items():
			if name == base:
				return name, coords[0], coords[1]
	return None


def _parse_date_range(date_str: str) -> tuple[date, date]:
	"""解析日期参数。支持单日和范围。
	- "2026-05-01" → (2026-05-01, 2026-05-03) 默认查3天
	- "2026-05-01~2026-05-07" → 范围
	"""
	today = date.today()
	if "~" in date_str:
		parts = date_str.split("~")
		try:
			start = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
			end = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
			return start, min(end, start + timedelta(days=14))
		except ValueError:
			return today, today + timedelta(days=3)
	if date_str.strip():
		try:
			start = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
			return start, min(start + timedelta(days=3), start + timedelta(days=14))
		except ValueError:
			pass
	return today, today + timedelta(days=3)


class WeatherQuery:
	"""天气查询工具 — 基于 Open-Meteo 免费 API，无需 API Key。"""


	@retry(max_retries=2, delay_s=1.0)
	def _call_open_meteo(self, lat: float, lon: float, start: date, end: date) -> dict:
		"""调用 Open-Meteo API。"""
		params: dict[str, str | list[str] | float] = {
			"latitude": lat,
			"longitude": lon,
			"daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_mean",
			          "wind_speed_10m_max", "weather_code"],
			"timezone": "Asia/Shanghai",
			"start_date": start.isoformat(),
			"end_date": end.isoformat(),
		}
		resp: requests.Response = requests.get(_OPEN_METEO_URL, params=params, timeout=15)
		resp.raise_for_status()
		return resp.json()


	def query(self, city: str, date_range: str = "") -> str:
		"""查询城市天气预报。

		:param city:       城市名称（中文），如'成都'
		:param date_range: 日期或日期范围。单日如 '2026-05-01'，范围如 '2026-05-01~2026-05-07'
		:return: JSON 字符串
		"""
		resolved: tuple[str, float, float] | None = _resolve_city(city)
		if resolved is None:
			return json.dumps({
				"error": f"未找到城市'{city}'。支持的城市：{', '.join(_CITY_COORDS.keys())}",
			}, ensure_ascii=False)

		name: str
		lat: float
		lon: float
		name, lat, lon = resolved
		start: date
		end: date
		start, end = _parse_date_range(date_range)

		data: dict
		try:
			data = self._call_open_meteo(lat, lon, start, end)
		except Exception as e:
			return json.dumps({"error": f"天气 API 调用失败：{e}"}, ensure_ascii=False)

		daily: dict = data.get("daily", {})
		if not daily:
			return json.dumps({"error": "天气 API 返回数据为空"}, ensure_ascii=False)

		dates: list[str] = daily.get("time", [])
		temps_max: list[float] = daily.get("temperature_2m_max", [])
		temps_min: list[float] = daily.get("temperature_2m_min", [])
		precip: list[int] = daily.get("precipitation_probability_mean", [])
		wind: list[float] = daily.get("wind_speed_10m_max", [])
		codes: list[int] = daily.get("weather_code", [])

		forecast: list[dict] = []
		for i, d in enumerate(dates):
			wmo: int = int(codes[i]) if i < len(codes) else 0
			forecast.append({
				"date": d,
				"weather": _WMO_CODES.get(wmo, f"未知({wmo})"),
				"temp_max": round(temps_max[i], 1) if i < len(temps_max) else None,
				"temp_min": round(temps_min[i], 1) if i < len(temps_min) else None,
				"precipitation_probability": precip[i] if i < len(precip) else None,
				"wind_max_kmh": round(wind[i], 1) if i < len(wind) else None,
			})

		return json.dumps({
			"city": name,
			"date_range": f"{start.isoformat()} ~ {end.isoformat()}",
			"forecast": forecast,
		}, ensure_ascii=False, indent=2)


	def to_tool_def(self) -> ToolDef:
		"""生成 ToolDef 注册描述。"""
		return ToolDef(
			name="weather_query",
			description=(
				"查询城市天气预报，返回每日天气、最高/最低温度、降水概率、风速等。"
				"基于 Open-Meteo 免费 API，数据可靠。"
			),
			parameters={
				"city": {
					"type": "string",
					"description": "城市名称（中文），如'成都'、'北京'",
				},
				"date_range": {
					"type": "string",
					"description": "日期或日期范围，单日如'2026-05-01'，范围如'2026-05-01~2026-05-07'",
				},
			},
			required=["city"],
			func=self.query,
		)


if __name__ == "__main__":
	print("=" * 60)
	print("  WeatherQuery 演示")
	print("=" * 60)

	tool: WeatherQuery = WeatherQuery()

	print('\n🌤️  query(city="成都", date_range="2026-07-20")')
	result: str = tool.query("成都", "2026-07-20")
	print(f"   {result[:500]}...")

	print('\n🌤️  query(city="北京", date_range="2026-07-20~2026-07-22")')
	result = tool.query("北京", "2026-07-20~2026-07-22")
	print(f"   {result[:500]}...")

	print("\n" + "=" * 60)
	print("  演示完成")
	print("=" * 60)
