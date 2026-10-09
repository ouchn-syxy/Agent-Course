"""VLM 视觉分析领域模型 — 截图分析、元素定位等场景的 Pydantic DTO。"""

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """矩形边界框（像素坐标，相对于截图图片原点）。"""

    x: int = Field(description="左上角 X 坐标（像素）")
    y: int = Field(description="左上角 Y 坐标（像素）")
    width: int = Field(description="宽度（像素）")
    height: int = Field(description="高度（像素）")


class UIElement(BaseModel):
    """可交互的 UI 元素。"""

    name: str = Field(description="元素名称，如'发送按钮'、'消息输入框'、'客户列表中张三的条目'")
    bbox: BoundingBox = Field(description="元素的边界框")
    center_x: int = Field(description="元素中心点 X 坐标（像素）")
    center_y: int = Field(description="元素中心点 Y 坐标（像素）")
    description: str = Field(default="", description="元素补充描述")


class UIRegion(BaseModel):
    """功能区域（客户列表区、聊天区、信息面板区等）。"""

    name: str = Field(description="区域名称，如'客户列表区'、'聊天区'、'右侧信息面板区'")
    bbox: BoundingBox = Field(description="区域的边界框")
    elements: list[UIElement] = Field(default_factory=list, description="该区域内的可交互元素")


class CustomerMessage(BaseModel):
    """从聊天区提取的单条客户消息。"""

    customer_name: str = Field(description="客户名称或昵称")
    content: str = Field(description="消息文本内容")
    has_unread: bool = Field(default=False, description="是否为未读消息（有红点/加粗等视觉标识）")


class ScreenAnalysis(BaseModel):
    """截图分析的完整结果。"""

    regions: list[UIRegion] = Field(description="识别到的 UI 功能区域列表")
    messages: list[CustomerMessage] = Field(default_factory=list, description="从聊天区提取的消息列表")
    active_customer: str = Field(default="", description="当前活跃（正在对话中）的客户名称")
    raw_text: str = Field(default="", description="截图中的全部可见文本（用于调试和验证）")


class ElementLocation(BaseModel):
    """元素定位结果（坐标已转换为屏幕绝对坐标）。"""

    element_name: str = Field(description="被定位的元素名称")
    center_x: int = Field(description="元素中心点 X 坐标（屏幕绝对坐标）")
    center_y: int = Field(description="元素中心点 Y 坐标（屏幕绝对坐标）")
    bbox: BoundingBox = Field(description="元素的边界框（图片坐标，未加窗口偏移）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="定位置信度 0-1")
