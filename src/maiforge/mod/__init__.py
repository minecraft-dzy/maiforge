"""
Mod – 模组模块入口，重新导出 Container、Info 等供外部使用。
"""
from .container import ModContainer, ModInfo

__all__ = ["ModContainer", "ModInfo"]
