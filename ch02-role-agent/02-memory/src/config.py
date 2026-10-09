"""应用配置 — 基于 Pydantic v2，支持从 config.yaml 加载。

职责：定义和管理项目运行所需的全部配置项，通过 config.yaml 文件持久化。
所有配置模型禁止额外字段，启用赋值时校验。

配置文件结构参照 config.yaml.example：
  llm:        API 密钥、地址、模型
  generation: 温度、Top-P、max_tokens 等生成参数
  profile:  角色相关配置
  memory:     短期记忆配置
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
	base_url: str = Field(description="API 基础地址（如 https://api.deepseek.com）")
	model: str = Field(description="默认模型名（如 deepseek-v4-flash）")
	api_key_env: str = Field(description="API 密钥（如 sk-xxx）")


class GenerationConfig(BaseModel):
	"""生成参数配置 — 控制 LLM 输出的随机性、长度、重复度。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度（0-2），越高越随机")
	top_p: float | None = Field(default=None, ge=0.0, le=1.0, description="核采样阈值")
	max_tokens: int | None = Field(default=None, ge=1, description="最大输出 token 数")


class ProfileConfig(BaseModel):
	"""角色配置 — 默认角色文件名等。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	default: str = Field(description="默认角色文件名（位于 data/profiles/ 下）")
	user_name_placeholder: str = Field(default="来访者", description="系统提示词中 {user_name} 占位的默认值")


class MemoryConfig(BaseModel):
	"""记忆配置 — 滑动窗口与摘要压缩阈值。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	max_turns: int = Field(default=20, ge=1, description="滑动窗口最大保留轮数")
	max_tokens: int = Field(default=3000, ge=1, description="触发摘要压缩的 token 阈值")


class Config(BaseModel):
	"""应用根配置模型 — 聚合 llm / generation / profile 子配置。

	从 config.yaml 反序列化，校验所有字段类型和完整性，
	未知字段将被拒绝（extra="forbid"）。
	"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	llm: LLMConfig = Field(description="LLM 连接配置")
	generation: GenerationConfig = Field(default_factory=GenerationConfig, description="生成参数")
	profile: ProfileConfig = Field(default_factory=ProfileConfig, description="角色配置")
	memory: MemoryConfig = Field(default_factory=MemoryConfig, description="记忆配置")


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
