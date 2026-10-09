"""SAL HTTP 客户端 — 封装对后端服务的 HTTP 请求。

提供统一的 GET / POST 方法，自动拼接 Base URL。
"""

from __future__ import annotations

import requests


class APIClient:
	"""后端 API HTTP 客户端。

	用法：
		cfg = Config.from_yaml()
		client = APIClient(cfg.backend.host)
		client.get("/api/customers")
	"""


	def __init__(self, host: str) -> None:
		self._host: str = host.rstrip("/")


	def get(self, path: str) -> dict | list:
		"""发送 GET 请求。

		Args:
			path: API 路径，如 "/api/customers"。

		Returns:
			JSON 解析后的响应数据。

		Raises:
			requests.HTTPError: 非 2xx 响应。
		"""
		url: str = f"{self._host}{path}"
		resp: requests.Response = requests.get(url, timeout=10)
		resp.raise_for_status()
		return resp.json()


	def post(self, path: str, body: dict) -> dict | list:
		"""发送 POST 请求。

		Args:
			path: API 路径，如 "/api/chat/cust_001/send"。
			body: 请求体 JSON。

		Returns:
			JSON 解析后的响应数据。

		Raises:
			requests.HTTPError: 非 2xx 响应。
		"""
		url: str = f"{self._host}{path}"
		resp: requests.Response = requests.post(url, json=body, timeout=30)
		resp.raise_for_status()
		return resp.json()
