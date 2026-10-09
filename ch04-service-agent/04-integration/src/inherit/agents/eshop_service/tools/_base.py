"""工具模块共享的子进程调用辅助。

所有 tools 通过此函数统一调用 ``python -m tools.xxx`` CLI，
共享 PYTHONPATH 注入和超时设置。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from inherit.utils.path import get_prj_root


def run_tool_cli(
		module: str,
		*args: str,
		timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
	"""调用 tools 子进程。

	Args:
		module: tools 模块名，如 ``"input"`` / ``"screenshot"``。
		*args: 传给模块的 CLI 参数。
		timeout: 超时秒数（默认 15）。

	Returns:
		subprocess.CompletedProcess，含 stdout / stderr / returncode。
	"""
	# tools/ 所在父目录（ch04-service-agent/），用于 PYTHONPATH
	tools_dir: Path = get_prj_root() / ".." / "tools"
	tools_dir = tools_dir.resolve()

	cmd: list[str] = [sys.executable, "-m", module, *args]
	env: dict[str, str] = {**os.environ, "PYTHONPATH": str(tools_dir)}
	return subprocess.run(
		cmd,
		capture_output=True,
		text=True,
		timeout=timeout,
		env=env,
		cwd=tools_dir,
	)
