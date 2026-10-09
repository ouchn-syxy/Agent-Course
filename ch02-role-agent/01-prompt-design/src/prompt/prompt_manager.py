"""Prompt 模板管理器 — 基于 Jinja2 加载、缓存和渲染 Prompt 模板。

职责：
- 按 agent 分类管理 Prompt 模板文件
- 通过 Jinja2 Environment + FileSystemLoader 加载模板
- 提供一步到位的 load + render 接口，支持变量注入
- 内建模板缓存（Jinja2 默认行为），避免重复解析

"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template


class PromptManager:
	"""Jinja2 模板管理器 — 按子目录加载 Prompt 模板。

	template_name 为基于 templates_dir 的相对路径（如 "profile/system.j2"）。

	用法：
		pm = PromptManager("/path/to/src/prompts")
		text = pm.render("profile/system.j2", name="张三", ...)
		tpl = pm.load("polish/system.j2")
	"""


	def __init__(self, templates_dir: Path) -> None:
		"""
		Args:
			templates_dir: 模板根目录（如 src/prompts/），模板名基于此目录的相对路径。
		"""
		self._templates_dir: Path = templates_dir
		self._env: Environment = Environment(
			loader=FileSystemLoader(str(self._templates_dir)),
			autoescape=False,  # Prompt 不需要 HTML 转义
			trim_blocks=True,  # 自动去除块标签后的首行空白
			lstrip_blocks=True,  # 自动去除块标签前的空白
		)
		# 注册 model_dump 过滤器 — 在模板中调用 Pydantic 模型的 .model_dump() 方法
		self._env.filters["model_dump"] = lambda v: v.model_dump() if hasattr(v, "model_dump") else v


	def load(self, template_name: str) -> Template:
		"""加载模板文件。

		模板路径为 {templates_dir}/{template_name}。
		Jinja2 内建模板缓存，重复调用不会重复解析文件。

		Args:
			template_name: 基于 templates_dir 的相对路径（如 "profile/system.j2"）。

		Returns:
			已编译的 Jinja2 Template 对象。

		Raises:
			jinja2.TemplateNotFound: 模板文件不存在。
		"""
		return self._env.get_template(template_name)


	def render(self, template_name: str, **variables: Any) -> str:
		"""一步加载并渲染模板。

		Args:
			template_name: 基于 templates_dir 的相对路径（如 "dm/system.j2"）。
			**variables: 模板变量键值对。

		Returns:
			渲染后的完整 Prompt 文本。

		Raises:
			jinja2.TemplateNotFound: 模板文件不存在。
			jinja2.UndefinedError: 模板引用了未传递的变量。
		"""
		tpl: Template = self.load(template_name)
		return tpl.render(**variables)


	@property
	def templates_dir(self) -> Path:
		"""模板根目录路径。"""
		return self._templates_dir


if __name__ == "__main__":
	from utils.path import get_prj_root
	import yaml

	pm: PromptManager = PromptManager(get_prj_root() / "prompts")

	# 1) 查看模板根目录
	print(f"模板根目录: {pm.templates_dir}\n")

	# 2) load — 只加载不渲染
	tpl = pm.load("profile.j2")
	print(f"已加载模板: {tpl.name}\n")

	# 3) render — 加载角色 YAML 并渲染
	profile_path = get_prj_root() / "data" / "profiles" / "luxun.yaml"
	with open(profile_path, encoding="utf-8") as f:
		profile = yaml.safe_load(f)

	rendered = pm.render("profile.j2", profile=profile, user_name="来访者")
	print(f"渲染结果:\n{rendered}")
