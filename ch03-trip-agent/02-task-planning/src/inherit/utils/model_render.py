"""Pydantic 模型 → 声明代码生成。

从 BaseModel 的 Field(description=...) 递归生成 Pydantic 类定义代码，
注入 Jinja2 Prompt 模板，使 LLM 看到完整字段名、类型、描述和嵌套结构。
"""

from __future__ import annotations

import types
import typing
from enum import Enum, IntEnum, StrEnum
from typing import Any, Annotated, get_args, get_origin

from pydantic import BaseModel


def _type_str(annotation: Any) -> str:
	"""将类型标注转回源码级字符串，Annotated 剥到内层类型。"""
	# Annotated[T, ...] → T
	origin = get_origin(annotation)
	if origin is Annotated:
		return _type_str(get_args(annotation)[0])

	if annotation is str:
		return "str"
	if annotation is bool:
		return "bool"
	if annotation is int:
		return "int"
	if annotation is float:
		return "float"
	if annotation is type(None):
		return "None"

	# 字符串形式的前向引用（from __future__ import annotations）
	if isinstance(annotation, str):
		return annotation

	# UnionType → T1 | T2 | ...
	if origin is types.UnionType:
		return " | ".join(_type_str(a) for a in get_args(annotation))

	# list[T] / dict[K, V]
	if origin is list:
		args = get_args(annotation)
		return f"list[{_type_str(args[0])}]" if args else "list"
	if origin is dict:
		args = get_args(annotation)
		k = _type_str(args[0]) if args else "str"
		v = _type_str(args[1]) if len(args) > 1 else "Any"
		return f"dict[{k}, {v}]"

	# Pydantic 模型 / StrEnum 枚举 → 类名
	if isinstance(annotation, type):
		return annotation.__name__

	return str(annotation)


def _collect_models(annotation: Any, into: set[type[BaseModel]]) -> None:
	"""递归收集类型标注中所有 Pydantic 子模型（去重）。

	支持直接嵌套模型、list[T]、dict[K,V]、Optional[T]、Annotated[T,...]。
	:param annotation: 已解析的类型标注（非字符串）
	:param into: 收集结果集
	"""
	if isinstance(annotation, str):
		return  # 未解析的前向引用，跳过

	if isinstance(annotation, type) and issubclass(annotation, BaseModel) and annotation is not BaseModel:
		into.add(annotation)
		return

	# 泛型容器 → 向下钻取类型参数
	origin = get_origin(annotation)
	args = get_args(annotation)

	if origin is Annotated:
		for a in args[:1]:
			_collect_models(a, into)
	elif origin is types.UnionType:
		for a in args:
			if a is not type(None):
				_collect_models(a, into)
	elif origin in (list, dict):
		for a in args:
			_collect_models(a, into)


def _collect_enums(annotation: Any, into: set[type]) -> None:
	"""递归收集类型标注中所有 Enum 子类（去重）。

	支持直接嵌套、list[T]、dict[K,V]、Optional[T]、Annotated[T,...]。
	排除 Enum / IntEnum / StrEnum 基类自身及 BaseModel 子类。
	"""
	if isinstance(annotation, str):
		return

	if isinstance(annotation, type) and issubclass(annotation, Enum):
		if not issubclass(annotation, BaseModel) and annotation not in (Enum, IntEnum, StrEnum):
			into.add(annotation)
		return

	origin = get_origin(annotation)
	args = get_args(annotation)

	if origin is Annotated:
		for a in args[:1]:
			_collect_enums(a, into)
	elif origin is types.UnionType:
		for a in args:
			if a is not type(None):
				_collect_enums(a, into)
	elif origin in (list, dict):
		for a in args:
			_collect_enums(a, into)


def _render_enum(enum_cls: type, indent: int = 0) -> str:
	"""将枚举类渲染为代码定义字符串。"""
	pfx: str = "    " * indent
	if issubclass(enum_cls, str):
		base: str = "StrEnum"
	elif issubclass(enum_cls, int):
		base = "IntEnum"
	else:
		base = "Enum"

	lines: list[str] = [f"{pfx}class {enum_cls.__name__}({base}):"]
	for member in enum_cls:
		v = member.value
		vs: str = f'"{v}"' if isinstance(v, str) else str(v)
		lines.append(f"{pfx}    {member.name} = {vs}")
	return "\n".join(lines)


def _render_model(
		model_cls: type[BaseModel],
		resolved: dict[str, Any],
		indent: int = 0,
		rendered: set[int] | None = None,
) -> str:
	"""将单个 Pydantic 模型递归渲染为类定义代码。

	嵌套 Pydantic 子模型及 Enum 子类以 inline class 展开在字段定义之后，
	枚举定义优先于模型定义输出。
	:param resolved: typing.get_type_hints() 解析后的字段类型映射
	:param rendered: 已渲染的类型 id 集合，避免重复展开
	"""
	if rendered is None:
		rendered = set()
	rendered.add(id(model_cls))

	pfx = "    " * indent
	lines: list[str] = [f"{pfx}class {model_cls.__name__}(BaseModel):"]

	# 收集所有嵌套子模型和枚举（去重，排除自身和已渲染）
	nested_models: set[type[BaseModel]] = set()
	nested_enums: set[type] = set()
	for anno in resolved.values():
		_collect_models(anno, nested_models)
		_collect_enums(anno, nested_enums)
	nested_models.difference_update({m for m in nested_models if id(m) in rendered})
	nested_enums.difference_update({e for e in nested_enums if id(e) in rendered})
	for e in nested_enums:
		rendered.add(id(e))

	for name, info in model_cls.model_fields.items():
		anno = resolved.get(name, info.annotation)
		ts = _type_str(anno)
		desc = info.description or ""

		field_args: list[str] = []
		if desc:
			field_args.append(f'description="{desc.replace(chr(34), chr(92) + chr(34))}"')

		# Optional 且无默认值 → default=None
		origin = get_origin(anno)
		if origin is types.UnionType and type(None) in get_args(anno):
			if info.default is None and not info.default_factory:
				field_args.insert(0, "default=None")

		if field_args:
			lines.append(f"{pfx}    {name}: {ts} = Field({', '.join(field_args)})")
		else:
			lines.append(f"{pfx}    {name}: {ts}")

	# 先渲染枚举定义，再渲染嵌套模型
	for e in sorted(nested_enums, key=lambda c: c.__name__):
		lines.append(f"\n{_render_enum(e, indent + 1)}")

	for m in sorted(nested_models, key=lambda c: c.__name__):
		sub = _render_model(m, _resolve_annotations(m), indent + 1, rendered)
		lines.append(f"\n{sub}")

	return "\n".join(lines)


def _resolve_annotations(model_cls: type[BaseModel]) -> dict[str, Any]:
	"""解析模型字段类型标注，处理 __future__.annotations 字符串前向引用。"""
	model_cls.model_rebuild()
	return typing.get_type_hints(model_cls, include_extras=False)


def render_model_code(model_cls: type[BaseModel]) -> str:
	"""从 Pydantic 模型生成声明代码字符串。

	输出完整的 Pydantic 类定义（含嵌套子模型），可直接注入 Jinja2 模板。
	"""
	return _render_model(model_cls, _resolve_annotations(model_cls))


if __name__ == "__main__":
	from pydantic import BaseModel, Field


	class Address(BaseModel):
		"""地址"""

		city: str = Field(description="城市名")
		street: str | None = Field(default=None, description="街道地址")


	class Person(BaseModel):
		"""人物信息"""

		name: str = Field(description="姓名")
		age: int | None = Field(default=None, description="年龄")
		address: Address | None = Field(default=None, description="地址")
		tags: list[str] = Field(default_factory=list, description="标签")


	print(render_model_code(Person))
