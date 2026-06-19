"""
MaiForge – the central orchestrator.  Holds the ModLoader, EventBus, PatchEngine, Installer.

One singleton per process (like FML's FMLCommonHandler).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .event import EventBus, Event, CancelableEvent
from .loader import ModLoader
from ..mod.container import ModContainer
from ..patch.engine import PatchEngine
from ..installer.installer import Installer

logger = logging.getLogger("maiforge")


# ---- Lifecycle Events ----

class ForgeInitializeEvent(Event):
    """Fired before mods are loaded."""


class ForgeModsLoadedEvent(Event):
    """Fired after all mods have been loaded and enabled."""


class ForgeShutdownEvent(Event):
    """Fired when maiforge is shutting down."""


class ModEnabledEvent(Event):
    """Fired when a mod is enabled."""

    def __init__(self, mod: ModContainer) -> None:
        super().__init__()
        self.mod = mod


class ModDisabledEvent(Event):
    """Fired when a mod is disabled."""

    def __init__(self, mod: ModContainer) -> None:
        super().__init__()
        self.mod = mod


# ---- WebUI Events ----

class WebUIRegisterNavEvent(Event):
    """Fired to let mods register custom nav items.

    Usage:
        event.add_nav("模组设置", "/mods/settings", icon="settings")
    """

    def __init__(self) -> None:
        super().__init__()
        self.nav_items: list[dict] = []

    def add_nav(self, label: str, path: str, *, icon: str = "box") -> None:
        self.nav_items.append({"label": label, "path": path, "icon": icon})


class WebUIModifyPageEvent(Event):
    """Fired when a WebUI page is rendered.  Allows mods to inject HTML/JS/CSS."""

    def __init__(self, page_id: str) -> None:
        super().__init__()
        self.page_id = page_id
        self.head_html: list[str] = []
        self.body_html: list[str] = []
        self.scripts: list[str] = []

    def inject_head(self, html: str) -> None:
        self.head_html.append(html)

    def inject_body(self, html: str) -> None:
        self.body_html.append(html)

    def inject_script(self, js: str) -> None:
        self.scripts.append(js)


# ---------------------------------------------------------------------------


class MaiForge:
    """Root object – akin to net.minecraftforge.fml.ModLoader (the runtime)."""

    _instance: Optional["MaiForge"] = None

    def __init__(self) -> None:
        self._initialized = False
        # Resolve paths relative to the bot project directory
        self._bot_dir = self._resolve_bot_dir()
        self.mods_dir = self._bot_dir / "mods"
        self.data_dir = self._bot_dir / "data" / "maiforge"

        self.event_bus = EventBus()
        self.patcher = PatchEngine()
        self.loader = ModLoader(self.mods_dir)
        self.installer = Installer(self._bot_dir)

        MaiForge._instance = self

    @staticmethod
    def _resolve_bot_dir() -> Path:
        import sys
        cwd = Path.cwd()
        # If called from within maiforge, go up
        if cwd.name == "maiforge" or (cwd / "bot.py").exists():
            return cwd
        # Try parent
        if (cwd.parent / "bot.py").exists():
            return cwd.parent
        return cwd

    # ---- lifecycle ----

    def initialize(self) -> None:
        """Initialize Maiforge core systems."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        self.event_bus.post(ForgeInitializeEvent())
        logger.info("MaiForge %s initialized", self.version)

    def load_mods(self) -> None:
        """Load and enable all discovered mods."""
        self.loader.load_all()
        for mod in self.loader.get_all_mods():
            try:
                mod.enable(self)
                self.event_bus.post(ModEnabledEvent(mod))
            except Exception as exc:
                logger.error("Error enabling mod %s: %s", mod.info.mod_id, exc)
        self.patcher.apply_all()
        self.event_bus.post(ForgeModsLoadedEvent())

    def shutdown(self) -> None:
        """Graceful shutdown: disable mods, revert patches, clear bus."""
        self.event_bus.post(ForgeShutdownEvent())
        self.patcher.revert_all()
        self.loader.unload_all()
        self.event_bus.clear()
        self._initialized = False

    # ---- helpers ----

    @property
    def version(self) -> str:
        from .. import VERSION
        return VERSION

    @property
    def is_installed(self) -> bool:
        return self.installer.is_installed

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def get_all_mod_list(self) -> list[dict]:
        return [m.to_dict() for m in self.loader.get_all_mods()]

    @classmethod
    def get_instance(cls) -> Optional["MaiForge"]:
        return cls._instance
