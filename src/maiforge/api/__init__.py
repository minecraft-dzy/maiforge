"""
Convenience API for mod developers.
Mimics the simplicity of Forge's @Mod / @SubscribeEvent.
"""
from .core.event import (
    Event,
    CancelableEvent,
    SubscribeEvent,
    EventBus,
    EventPriority,
)
from .core.forge import (
    MaiForge,
    ForgeInitializeEvent,
    ForgeModsLoadedEvent,
    ForgeShutdownEvent,
    ModEnabledEvent,
    ModDisabledEvent,
    WebUIRegisterNavEvent,
    WebUIModifyPageEvent,
)
from .patch.engine import PatchEngine

__all__ = [
    # Events
    "Event",
    "CancelableEvent",
    "SubscribeEvent",
    "EventBus",
    "EventPriority",
    # Forge lifecycle
    "MaiForge",
    "ForgeInitializeEvent",
    "ForgeModsLoadedEvent",
    "ForgeShutdownEvent",
    "ModEnabledEvent",
    "ModDisabledEvent",
    # WebUI
    "WebUIRegisterNavEvent",
    "WebUIModifyPageEvent",
    # Patching
    "PatchEngine",
]
