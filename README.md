# MaiForge

MaiBot 模组加载器 — 复刻 Minecraft Forge 设计哲学，为 MaiBot 提供无需修改主程序源码的模组加载能力。

## 理念

> 就像 Forge 让 Minecraft 能够加载模组而无需修改原版 jar，**MaiForge** 让 MaiBot 能够加载模组而无需修改主程序源码。

## 特性

- **ZIP 模组加载**：模组统一用 ZIP 格式打包，内含 `mod.json`/`mod.toml` 清单
- **函数钩子系统**：支持前置/后置/替换注入，不修改主程序代码
- **事件总线**：Forge 风格的 `@SubscribeEvent`，支持优先级与可取消事件
- **WebUI 集成**：独立模组管理页面，安装/启用/禁用/卸载一键操作
- **安装卸载**：一键安装注入启动引导，完整卸载后主程序恢复原状
- **隔离稳定**：单模组异常不影响主程序运行

## 快速开始

### 安装 MaiForge

```bash
# 将 maiforge 放到 MaiBot 项目根目录
cd /path/to/maibot
pip install -e /path/to/maiforge

# 运行安装器
python -m maiforge.install

# 启动 MaiBot，maiforge 将自动加载 mods/ 目录下的所有模组
```

### 卸载

在 WebUI 的模组管理页面右上角点击「卸载 MaiForge」，或直接：

```bash
python -c "from maiforge.core.forge import MaiForge; f=MaiForge(); f.installer.uninstall()"
```

## 开发模组

创建一个 ZIP 包：

```
my-mod.zip
├── mod.json          # 清单文件
└── mod/
    ├── __init__.py
    └── main.py       # 入口
```

`mod.json`:
```json
{
  "modId": "example_mod",
  "name": "示例模组",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "一个示例模组",
  "entrypoint": "mod.main",
  "maiforgeApi": "1.0"
}
```

`mod/main.py`:
```python
from maiforge.api import SubscribeEvent, ForgeModsLoadedEvent

def on_enable(forge):
    print("模组已加载!")

def on_disable():
    print("模组已卸载!")
```

详细文档见 [开发文档](docs/DEVELOPER_GUIDE.md)。

## 项目结构

```
maiforge/
├── src/maiforge/
│   ├── core/        # 核心加载器、事件总线
│   ├── mod/          # ModContainer
│   ├── patch/        # 函数钩子引擎
│   ├── installer/    # 安装/卸载
│   ├── webui/        # WebUI 集成
│   └── api/          # 开发者 API
├── docs/             # 文档
├── .github/          # CI
└── pyproject.toml
```

## 许可证

MIT
