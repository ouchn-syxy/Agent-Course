"""写作工作室角色模型。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RoleIOContract(BaseModel):
	"""角色输入约束。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	required: list[str] = Field(default_factory=list, description="必需输入字段")
	optional: list[str] = Field(default_factory=list, description="可选输入字段")


class RoleOutputContract(BaseModel):
	"""角色输出约束。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	format: str = Field(default="json", description="输出格式（json / markdown / text）")
	schema_file: str | None = Field(default=None, description="JSON Schema 文件名（相对于 schemas/ 目录）")


class StudioRole(BaseModel):
	"""写作工作室角色定义。"""

	model_config = ConfigDict(extra="forbid", validate_assignment=True)

	id: str = Field(description="角色唯一标识符")
	name: str = Field(description="角色中文名称")
	role: str = Field(description="角色职责描述")
	responsibilities: list[str] = Field(default_factory=list, description="角色主要职责列表")
	input_contract: RoleIOContract = Field(default_factory=RoleIOContract, description="输入约束")
	output_contract: RoleOutputContract = Field(default_factory=RoleOutputContract, description="输出约束")
	quality_focus: list[str] = Field(default_factory=list, description="质量关注点")
	system_prompt: str = Field(description="角色系统提示词")
	metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")
