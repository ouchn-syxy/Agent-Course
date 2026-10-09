"""应用配置 — 基于 Pydantic v2，支持从 config.yaml 加载。

职责：定义和管理项目运行所需的全部配置项。

配置文件结构参照 config.yaml.example：
  llm:        API 密钥、地址、模型
  generation: 温度、Top-P、max_tokens 等生成参数
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from inherit.utils.path import get_prj_root

_DEFAULT_CONFIG_PATH: Path = get_prj_root() / "config.yaml"


class LLMConfig(BaseModel):
	"""LLM 连接配置 — API 密钥、地址、模型名称。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	provider: str = Field(description="模型提供商（deepseek / qwen / zhipu / openai）")
	base_url: str = Field(description="API 基础地址")
	model: str = Field(description="默认模型名")
	api_key_env: str = Field(description="API 密钥")


class GenerationConfig(BaseModel):
	"""生成参数配置 — 控制 LLM 输出的随机性、长度。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度（0-2），越高越随机")
	top_p: float | None = Field(default=None, ge=0.0, le=1.0, description="核采样阈值")
	max_tokens: int | None = Field(default=None, ge=1, description="最大输出 token 数")


class Config(BaseModel):
	"""应用根配置模型 — 聚合 llm / generation 子配置。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	llm: LLMConfig
	generation: GenerationConfig


	@classmethod
	def from_yaml(cls, path: str | Path | None = None) -> "Config":
		"""从 YAML 配置文件加载，默认读取项目根目录的 config.yaml。

		:param path: 配置文件路径，不传则用默认路径
		"""
		path = Path(path) if path else _DEFAULT_CONFIG_PATH
		if not path.exists():
			raise FileNotFoundError(
				f"配置文件不存在：{path}\n"
				"请复制 config.yaml.example 为 config.yaml 并填写 api_key_env。"
			)
		with open(path, encoding="utf-8") as f:
			raw = yaml.safe_load(f)
		return cls.model_validate(raw)
