"""
ModContainer – an individual mod loaded from a ZIP (maiforge package).

Mirrors net.minecraftforge.fml.ModContainer.
"""
from __future__ import annotations

import json
import zipfile
import importlib.util
from pathlib import Path
from typing import Any, Callable, Optional


class ModInfo:
    """Metadata parsed from mod.toml inside the mod ZIP."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.mod_id: str = str(raw.get("modId") or raw.get("mod_id") or "")
        self.name: str = str(raw.get("name") or self.mod_id)
        self.version: str = str(raw.get("version") or "0.0.0")
        self.author: str = str(raw.get("author") or "unknown")
        self.description: str = str(raw.get("description") or "")
        self.entrypoint: str = str(raw.get("entrypoint") or "mod.MaiMod")
        self.dependencies: dict[str, str] = {
            str(k): str(v)
            for k, v in (raw.get("dependencies") or {}).items()
        }
        self.maiforge_api: str = str(raw.get("maiforgeApi") or "*")

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> "ModInfo":
        return cls(manifest.get("modInfo") or manifest)


class ModContainer:
    """Loaded mod instance.  Holds the ZIP, the entry module and lifecycle hooks."""

    def __init__(self, zip_path: Path, info: ModInfo) -> None:
        self.zip_path = zip_path
        self.info = info
        self._zip: Optional[zipfile.ZipFile] = None
        self._entry_module: Any = None
        self._state = "constructed"  # constructed → loaded → active → disabled

    # ------------------------------------------------------------------
    # lifecycle (called by ModLoader)
    # ------------------------------------------------------------------

    def load(self) -> None:
        self._zip = zipfile.ZipFile(self.zip_path, "r")
        # Import the entry module from inside the zip
        # We inject the zip into sys.path so imports work
        import sys
        sys.path.insert(0, str(self.zip_path))
        try:
            spec = importlib.util.find_spec(
                self.info.entrypoint.replace(".", "/") + ".py"
            )
            if spec is None:
                # Fallback: load by scanning zip contents
                entry_path = self.info.entrypoint.replace(".", "/") + ".py"
                try:
                    self._zip.getinfo(entry_path)
                    # Use zipimport
                    import zipimport
                    importer = zipimport.zipimporter(str(self.zip_path))
                    self._entry_module = importer.load_module(
                        self.info.entrypoint.split(".")[0]
                    )
                except KeyError:
                    raise ImportError(
                        f"Entrypoint {self.info.entrypoint} not found in {self.zip_path}"
                    )
            else:
                self._entry_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self._entry_module)  # type: ignore[union-attr]
            self._state = "loaded"
        finally:
            sys.path.pop(0)

    def enable(self, forge) -> None:
        """Call the mod's on_enable() if defined."""
        self._state = "active"
        if self._entry_module and hasattr(self._entry_module, "on_enable"):
            self._entry_module.on_enable(forge)

    def disable(self) -> None:
        """Call on_disable() and clean up."""
        if self._state == "disabled":
            return
        if self._entry_module and hasattr(self._entry_module, "on_disable"):
            try:
                self._entry_module.on_disable()
            except Exception:
                pass
        self._state = "disabled"
        if self._zip:
            self._zip.close()
            self._zip = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mod_id": self.info.mod_id,
            "name": self.info.name,
            "version": self.info.version,
            "author": self.info.author,
            "description": self.info.description,
            "state": self._state,
        }
