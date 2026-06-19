# MaiForge 模组开发文档

## 目录

1. [开发环境搭建](#开发环境搭建)
2. [模组项目结构](#模组项目结构)
3. [mod.json 清单规范](#modjson-清单规范)
4. [API 接口说明](#api-接口说明)
5. [事件系统](#事件系统)
6. [函数钩子 (Patch)](#函数钩子-patch)
7. [WebUI 扩展](#webui-扩展)
8. [模组打包规范](#模组打包规范)
9. [调试流程](#调试流程)
10. [发布要求](#发布要求)
11. [可修改能力清单](#可修改能力清单)

---

## 开发环境搭建

```bash
# 1. 克隆 maiforge
git clone https://github.com/minecraft-dzy/maiforge.git

# 2. 安装开发依赖
cd maiforge
pip install -e src/

# 3. 创建开发模组目录
mkdir -p dev_mods/example-mod/mod
```

## 模组项目结构

```
example-mod.zip          # 最终的模组分发包
├── mod.json             # 模组清单
└── mod/
    ├── __init__.py
    └── main.py          # 入口模块
```

## mod.json 清单规范

```json
{
  "modId": "example_mod",           // 必填：唯一标识符，使用 snake_case
  "name": "示例模组",                // 必填：显示名称
  "version": "1.0.0",               // 必填：SemVer 版本号
  "author": "Your Name",            // 必填：开发者名称
  "description": "一个示例模组",      // 可选：模组描述
  "entrypoint": "mod.main",         // 必填：Python 入口模块路径
  "dependencies": {                 // 可选：依赖的其他模组及版本
    "some_library": ">=1.0.0"
  },
  "maiforgeApi": "1.0"              // 必填：所需 maiforge API 版本，* 表示任意
}
```

## API 接口说明

### 生命周期

```python
# mod/main.py

def on_enable(forge: MaiForge):
    """模组启用时调用。forge 是 MaiForge 实例。"""
    print(f"MaiForge v{forge.version}")
    print(f"模组数量: {len(forge.loader.mods)}")

def on_disable():
    """模组禁用/卸载时调用。"""
    print("模组已禁用")
```

### 获取 Forge 实例

```python
from maiforge.api import MaiForge

forge = MaiForge.get_instance()
```

## 事件系统

MaiForge 提供 Forge 风格的事件总线：

```python
from maiforge.api import (
    SubscribeEvent,
    Event,
    CancelableEvent,
    ForgeModsLoadedEvent,
    ModEnabledEvent,
)

# 方式一：函数订阅
@SubscribeEvent
def on_mods_loaded(event: ForgeModsLoadedEvent):
    print("所有模组已加载！")

# 方式二：自定义事件
class MyCustomEvent(Event):
    def __init__(self, data: str):
        super().__init__()
        self.data = data

def on_enable(forge):
    # 发布事件
    evt = forge.event_bus.post(MyCustomEvent("hello"))
```

### 内置事件

| 事件类 | 触发时机 |
|--------|---------|
| `ForgeInitializeEvent` | MaiForge 初始化时 |
| `ForgeModsLoadedEvent` | 所有模组加载完成后 |
| `ForgeShutdownEvent` | MaiForge 关闭时 |
| `ModEnabledEvent` | 单个模组启用后 |
| `ModDisabledEvent` | 单个模组禁用后 |
| `WebUIRegisterNavEvent` | WebUI 导航注册时 |
| `WebUIModifyPageEvent` | WebUI 页面渲染时 |

### 事件优先级

```python
from maiforge.api import SubscribeEvent, EventPriority

@SubscribeEvent(priority=EventPriority.HIGHEST)
def handle_first(event: SomeEvent):
    pass

@SubscribeEvent(priority=EventPriority.LOWEST)
def handle_last(event: SomeEvent):
    pass
```

### 可取消事件

```python
class MyCancelableEvent(CancelableEvent):
    pass

@SubscribeEvent
def check_event(event: MyCancelableEvent):
    if some_condition:
        event.set_canceled(True)  # 阻止后续处理器执行
```

## 函数钩子 (Patch)

无需修改主程序代码即可拦截/替换任意函数：

```python
from maiforge.api import PatchEngine

def on_enable(forge):
    patcher = forge.patcher

    # 前置钩子：在目标函数执行前运行
    patcher.add(
        "bot.src.some_module.target_function",
        lambda *args, **kwargs: print(f"target_function called with {args}"),
        mode="before",
    )

    # 后置钩子：在目标函数执行后运行
    patcher.add(
        "bot.src.some_module.get_data",
        lambda result, *args, **kwargs: print(f"get_data returned {result}"),
        mode="after",
    )

    # 包装钩子：完全控制执行
    def my_wrapper(original, *args, **kwargs):
        print("before original")
        result = original(*args, **kwargs)
        print("after original")
        return result

    patcher.add(
        "bot.src.some_module.complex_logic",
        my_wrapper,
        mode="wrap",
    )

    # 替换钩子：完全替换原函数
    def my_replacement(*args, **kwargs):
        return "new result"

    patcher.add(
        "bot.src.some_module.old_function",
        my_replacement,
        mode="replace",
    )

    # 应用所有补丁
    count = patcher.apply_all()
    print(f"Applied {count} patches")

def on_disable():
    forge = MaiForge.get_instance()
    forge.patcher.revert_all()  # 模组卸载时自动恢复
```

## WebUI 扩展

### 添加导航栏

```python
from maiforge.api import SubscribeEvent, WebUIRegisterNavEvent

@SubscribeEvent
def register_nav(event: WebUIRegisterNavEvent):
    event.add_nav("我的模组页面", "/my-mod/page", icon="star")
```

### 注入页面内容

```python
from maiforge.api import SubscribeEvent, WebUIModifyPageEvent

@SubscribeEvent
def modify_page(event: WebUIModifyPageEvent):
    if event.page_id == "chat":
        event.inject_body('<div id="my-widget">Hello</div>')
        event.inject_script('document.querySelector("#my-widget").onclick = alert')
```

## 模组打包规范

```bash
# 进入模组开发目录
cd dev_mods/example-mod

# 打包为 ZIP (MaiForge 标准格式)
zip -r ../example-mod.zip mod.json mod/
```

注意事项：
- 模组文件必须是 ZIP 格式
- 根目录必须包含 `mod.json`（或 `mod.toml`, `manifest.json`）
- `entrypoint` 指向的模块必须存在
- 文件名建议使用 `{modId}-{version}.zip` 格式

## 调试流程

1. **启用 MaiForge 调试日志**:
```python
import logging
logging.getLogger("maiforge").setLevel(logging.DEBUG)
```

2. **查看已加载模组**:
访问 WebUI 的「模组管理」页面查看所有模组状态

3. **排查钩子冲突**:
```python
# 在 on_enable 中手动测试钩子
forge.patcher.add("target.func", test_hook, mode="wrap")
forge.patcher.apply_all()
# 手动调用目标函数验证
import target_module
target_module.target_func()
```

4. **模组隔离测试**:
将单个模组的 ZIP 放入 `mods/` 目录，启动 MaiBot 观察日志

## 发布要求

1. **版本号**必须遵循 [SemVer](https://semver.org/lang/zh-CN/)
2. **mod.json** 中的所有必填字段必须填写
3. 模组 ZIP **不应包含** `__pycache__` 或测试文件
4. 依赖声明在 `dependencies` 中，格式为 PyPI 包名
5. 测试通过后再发布

## 可修改能力清单

### 主程序函数注入列表

通过 `PatchEngine` 可注入主程序的**任意** Python 函数：

- 任何可被 `importlib.import_module` 加载的模块
- 任何模块级别的函数或类方法
- 任何全局变量

### WebUI 可定制元素

| 元素 | 方式 |
|------|------|
| 左侧导航栏 | `WebUIRegisterNavEvent.add_nav()` |
| 页面 HTML | `WebUIModifyPageEvent.inject_body()` |
| 页面 CSS/JS | `WebUIModifyPageEvent.inject_head()` |
| 自定义脚本 | `WebUIModifyPageEvent.inject_script()` |
| 模组管理页面 | 通过 `create_maiforge_plugin()` 自动注册 |

### 事件列表

参见 [事件系统](#事件系统) 章节的内置事件表。

---

## 示例模组

完整的示例模组参见 `examples/` 目录。
