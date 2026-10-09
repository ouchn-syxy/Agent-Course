# 截图工具（Screenshot Tool）

跨平台（macOS / Windows）屏幕截图工具，支持全屏、区域、窗口三种模式，提供 CLI 和 Python API。

## 依赖安装

```bash
pip install mss Pillow

# macOS 额外依赖（窗口枚举）
pip install pyobjc-framework-Quartz

# Windows 额外依赖（窗口枚举）
pip install pywin32
```

## macOS 权限设置

macOS 需要授予**屏幕录制**权限，否则截图只能拍到壁纸和菜单栏。

1. **系统设置 → 隐私与安全性 → 屏幕录制**
2. 勾选运行 Python 的应用（如 **Visual Studio Code**、**终端**、**iTerm**）
3. **重启该应用**后生效

> 验证：运行 `python -m tools.screenshot list-windows`，若能列出 Chrome、VS Code 等应用窗口则说明权限已生效。

## CLI 使用

在 `ch04-service-agent/` 目录下执行：

```bash
# 全屏截图
python -m tools.screenshot fullscreen
python -m tools.screenshot fullscreen -m 2                # 第 2 个显示器
python -m tools.screenshot fullscreen -o /tmp/my.png      # 指定路径
python -m tools.screenshot fullscreen -p "客服工作台"      # 文件名前缀

# 区域截图
python -m tools.screenshot region <x> <y> <width> <height>
python -m tools.screenshot region 100 200 800 600 -p "聊天区"

# 窗口截图
python -m tools.screenshot window -t "Chrome"              # 按标题子串匹配
python -m tools.screenshot window --id 47291               # 按窗口 ID 精确匹配

# 查看窗口列表
python -m tools.screenshot list-windows                    # 所有可见窗口
python -m tools.screenshot list-windows -f "客服"          # 按标题过滤
```

### 全局选项

| 选项 | 说明 |
|------|------|
| `-o, --output <path>` | 指定输出文件路径 |
| `-p, --prefix <str>` | 自动生成文件名前缀（默认 `screenshot`） |

截图默认保存到 `tools/screenshot/output/` 目录。

## Python API

```python
from tools.screenshot import create_screenshot_tool

tool = create_screenshot_tool()  # 自动适配 macOS / Windows

# 全屏截图
img = tool.capture_fullscreen()

# 区域截图
img = tool.capture_region(x=100, y=200, width=400, height=300)

# 窗口截图（按标题）
img = tool.capture_window(title="Chrome")

# 窗口截图（按 ID）
img = tool.capture_window(window_id=47291)

# 枚举窗口
windows = tool.list_windows()
for w in windows:
    print(w.id, w.title, w.x, w.y, w.width, w.height)

# 保存
tool.save(img)                            # 自动时间戳文件名
tool.save(img, prefix="kefu")             # 自定义前缀
tool.save(img, path="/tmp/screen.png")    # 指定路径
```

## 文件结构

```
tools/screenshot/
├── __init__.py            # 包导出
├── __main__.py            # python -m tools.screenshot 入口
├── base.py                # 抽象基类 + WindowInfo
├── cli.py                 # 命令行解析（argparse）
├── factory.py             # 平台自动检测
├── platform_darwin.py     # macOS 实现（MSS + Quartz）
├── platform_win32.py      # Windows 实现（MSS + win32gui）
├── utils.py               # 文件名生成等工具函数
├── output/                # 截图保存目录
└── README.md
```

## 平台差异

| 功能 | macOS | Windows |
|------|:-----:|:-------:|
| 全屏截图 | ✅ MSS (CoreGraphics) | ✅ MSS (GDI) |
| 区域截图 | ✅ MSS | ✅ MSS |
| 窗口枚举 | ✅ Quartz (CGWindowList) | ✅ win32gui (EnumWindows) |
| 窗口截图 | ✅ 按标题 / ID | ✅ 按标题 / ID |
