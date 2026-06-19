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

        # Resolve entrypoint: "ferrite_core.main" → ("ferrite_core", "main")
        parts = self.info.entrypoint.rsplit(".", 1)
        if len(parts) == 2:
            pkg_name, mod_name = parts
        else:
            pkg_name = self.info.entrypoint
            mod_name = "__init__"

        # Try zipimport first (most reliable)
        import zipimport
        try:
            importer = zipimport.zipimporter(str(self.zip_path))
            self._entry_module = importer.load_module(pkg_name)
        except zipimport.ZipImportError:
            # Fallback: add to sys.path and try importlib
            import sys
            sys.path.insert(0, str(self.zip_path))
            try:
                import importlib
                self._entry_module = importlib.import_module(
                    self.info.entrypoint.replace("/", ".")
                )
            except ImportError:
                # Last resort: exec source from zip
                entry_path = self.info.entrypoint.replace(".", "/") + ".py"
                try:
                    source = self._zip.read(entry_path).decode("utf-8")
                    mod = type(sys)("ferrite_mod")
                    mod.__file__ = str(self.zip_path)
                    exec(compile(source, entry_path, "exec"), mod.__dict__)
                    self._entry_module = mod
                except KeyError:
                    raise ImportError(
                        f"Entrypoint {self.info.entrypoint} not found in {self.zip_path}"
                    )
            finally:
                sys.path.pop(0)

        self._state = "loaded"

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
