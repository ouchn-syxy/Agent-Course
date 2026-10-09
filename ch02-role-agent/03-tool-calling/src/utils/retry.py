"""重试装饰器 — 为临时性错误（网络抖动、API 限流等）提供指数退避自动重试。

与 Agent 层面"LLM 看到错误字符串后自主重试"不同，这里是工具内部的工程化重试——
处理网络层面的瞬时故障，对 LLM 透明。

设计要点：
  - @retry() 装饰器模式，一行代码启用重试
  - ignore_exceptions 排除逻辑错误（类似 ValueError/TypeError），命中后立即抛出
  - 固定延迟退避（delay_s 秒），简单直观，适合教学场景

用法：
    @retry(max_retries=3, delay_s=2.0)
    def call_api():
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Iterable, TypeVar

_MAX_RETRIES: int = 3
_RETRY_DELAY: float = 2.0

_F = TypeVar("_F", bound=Callable[..., Any])


def retry(
		max_retries: int = _MAX_RETRIES,
		delay_s: float | int = _RETRY_DELAY,
		ignore_exceptions: Iterable[type[Exception]] | None = None,
) -> Callable[[_F], _F]:
	"""装饰器工厂：在临时性错误上最多重试 max_retries 次，每次间隔 delay_s 秒。

	Args:
		max_retries: 最大重试次数（不含首次），默认 3。
		delay_s: 每次重试前的固定等待秒数，默认 2.0。
		ignore_exceptions: 不重试的异常类型，命中后直接抛出。
						   例：ignore_exceptions=[ValueError, TypeError]

	Returns:
		装饰器函数。

	用法：
		@retry(max_retries=5, delay_s=1.0)
		def my_func():
			...
	"""
	_ignore: tuple[type[Exception], ...] = tuple(ignore_exceptions or ())


	def decorator(func: _F) -> _F:
		@wraps(func)
		def wrapper(*args: Any, **kwargs: Any) -> Any:
			last_exc: Exception = RuntimeError("未知错误")
			for attempt in range(max_retries):
				try:
					return func(*args, **kwargs)
				except _ignore:
					raise
				except Exception as e:
					last_exc = e
					if attempt < max_retries - 1:
						print(f"  🔄 [{func.__name__}] 第 {attempt + 1}/{max_retries} 次失败，{delay_s}s 后重试：{e}")
						time.sleep(delay_s)
			print(f"  ❌ [{func.__name__}] 已重试 {max_retries} 次，全部失败：{last_exc}")
			raise last_exc


		return wrapper


	return decorator
