# 输入模拟工具（Input Tool）

跨平台（macOS / Windows / Linux）键盘鼠标模拟工具，基于 pynput。提供 CLI 和 Python API。

## 依赖安装

```bash
pip install pynput
```

## macOS 权限设置

macOS 需要授予**辅助功能**权限才能模拟键盘鼠标输入。

1. **系统设置 → 隐私与安全性 → 辅助功能**
2. 勾选运行 Python 的应用（如 **Visual Studio Code**、**终端**、**iTerm**）
3. **重启该应用**后生效

> 验证：运行 `python -m tools.input mouse pos`，无报错则权限已生效。

## CLI 使用

在 `ch04-service-agent/` 目录下执行：

### 鼠标

```bash
# 获取当前位置
python -m tools.input mouse pos

# 移动到指定坐标
python -m tools.input mouse move --to 100 200
python -m tools.input mouse move --to 100 200 -d 0.5    # 0.5 秒缓动

# 相对移动
python -m tools.input mouse move --rel 50 -30

# 点击
python -m tools.input mouse click                        # 当前位置
python -m tools.input mouse click --pos 300 400          # 指定坐标

# 双击 / 右键
python -m tools.input mouse dclick --pos 300 400
python -m tools.input mouse rclick --pos 300 400

# 拖拽
python -m tools.input mouse drag 100 100 500 500
python -m tools.input mouse drag 100 100 500 500 -d 1.0  # 1 秒完成

# 滚轮
python -m tools.input mouse scroll --dy -3               # 向上滚动
python -m tools.input mouse scroll --dy 3                # 向下滚动
python -m tools.input mouse scroll --dx 3                # 向右滚动
```

### 键盘

```bash
# 输入文本
python -m tools.input keyboard type "hello world"

# 按下单个键
python -m tools.input keyboard tap enter
python -m tools.input keyboard tap esc
python -m tools.input keyboard tap tab
python -m tools.input keyboard tap a                      # 普通字符

# 组合键
python -m tools.input keyboard hotkey cmd c               # macOS 复制
python -m tools.input keyboard hotkey cmd v               # macOS 粘贴
python -m tools.input keyboard hotkey ctrl c              # Windows 复制
python -m tools.input keyboard hotkey alt tab             # 切换窗口
```

### 剪切板

```bash
# 读取剪切板
python -m tools.input clipboard read

# 写入剪切板
python -m tools.input clipboard write "要粘贴的文本"

# 在光标处粘贴剪切板内容（读取剪切板 → 逐字键入）
python -m tools.input clipboard paste
```

## Python API

```python
from tools.input import Mouse, Keyboard, Clipboard
from tools.input import LEFT, RIGHT, MIDDLE        # 鼠标按钮
from tools.input import ENTER, ESC, TAB, CMD, CTRL # 键盘按键

# ── 鼠标 ──
m = Mouse()

# 位置
print(m.position)                         # (x, y) 当前坐标
m.move_to(100, 200)                       # 移到绝对坐标
m.move_to(100, 200, duration=0.5)         # 0.5 秒缓动
m.move_rel(50, -30)                       # 相对移动

# 点击
m.click()                                 # 当前位置左键单击
m.click(x=300, y=400)                     # 指定坐标单击
m.double_click(300, 400)                  # 双击
m.right_click(300, 400)                   # 右键

# 拖拽
m.drag(100, 100, 500, 500)                # 从 (100,100) 拖到 (500,500)
m.drag(100, 100, 500, 500, duration=1.0)  # 1 秒完成

# 滚轮
m.scroll(dy=-3)                           # 向上 3 步
m.scroll(dy=3)                            # 向下 3 步
m.scroll_up(5)                            # 向上 5 步
m.scroll_down(5)                          # 向下 5 步

# ── 键盘 ──
kb = Keyboard()

# 文本输入
kb.type("hello world")

# 单键
kb.tap(ENTER)                             # 按回车
kb.tap(TAB)                               # 按 Tab
kb.tap("a")                               # 按字符 a

# 组合键
kb.hotkey("cmd", "c")                     # macOS 复制
kb.hotkey("ctrl", "v")                    # Windows 粘贴
kb.hotkey("cmd", "shift", "4")            # macOS 截图
kb.hotkey("ctrl", "shift", "esc")         # Windows 任务管理器

# ── 剪切板 ──
cb = Clipboard()

# 读写
cb.write("要粘贴到光标处的文本")
text = cb.read()                          # 读取剪切板内容

# 粘贴（读取剪切板，逐字键入到光标处）
cb.paste()
```

## 配合截图工具使用

```python
from tools.screenshot import create_screenshot_tool
from tools.input import Mouse

# 1. 截图找坐标
tool = create_screenshot_tool()
img = tool.capture_window(title="网店客服工作台")
# 查看截图确定按钮坐标...

# 2. 移动鼠标并点击
m = Mouse()
m.move_to(500, 300, duration=0.3)
m.click()
```

## 文件结构

```
tools/input/
├── __init__.py            # 包导出
├── __main__.py            # python -m tools.input 入口
├── mouse.py               # 鼠标模拟（pynput.mouse.Controller）
├── keyboard.py            # 键盘模拟（pynput.keyboard.Controller）
├── clipboard.py           # 剪切板读写（pyperclip）
├── cli.py                 # 命令行解析（argparse）
└── README.md
```

## 可用键名

### 功能键

`enter` `esc` `tab` `space` `backspace` `delete`
`f1` `f2` `f3` `f4` `f5` `f6` `f7` `f8` `f9` `f10` `f11` `f12`

### 方向键

`up` `down` `left` `right` `home` `end` `pageup` `pagedown`

### 修饰键

`cmd` / `command`　　 `ctrl` / `control`　　 `alt` / `option`　　 `shift`
