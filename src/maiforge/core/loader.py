"""
ModLoader – scans the mods directory, validates ZIP packages, loads ModContainers.

Mirrors net.minecraftforge.fml.ModLoader.
"""
from __future__ import annotations

import json
import zipfile
import logging
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Optional

from ..mod.container import ModContainer, ModInfo
from .. import VERSION as MAIFORGE_VERSION

logger = logging.getLogger("maiforge.loader")


def _parse_version(ver: str) -> tuple:
    """Parse semver string into comparable tuple."""
    try:
        return tuple(int(x) for x in str(ver).lstrip("v").split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


class ModLoadingException(Exception):
    """Raised when a mod cannot be loaded."""


class ModLoader:
    """Discovers, validates and loads mod ZIPs."""

    REQUIRED_MANIFEST_KEYS = {"modId", "name", "version"}

    def __init__(self, mods_dir: Path) -> None:
        self.mods_dir = Path(mods_dir)
        self.mods: dict[str, ModContainer] = {}

    def discover(self) -> list[Path]:
        """Return list of .zip files in the mods directory."""
        if not self.mods_dir.exists():
            self.mods_dir.mkdir(parents=True, exist_ok=True)
            return []
        return sorted(self.mods_dir.glob("*.zip"))

    def validate_manifest(self, manifest: dict[str, Any]) -> ModInfo:
        """Validate mod.toml / manifest.json content.  Returns ModInfo on success."""
        # Check required fields
        for key in self.REQUIRED_MANIFEST_KEYS:
            if key not in manifest:
                raise ModLoadingException(f"Missing required field: {key}")

        info = ModInfo.from_manifest(manifest)

        # Version validation
        if info.maiforge_api != "*":
            required = info.maiforge_api.lstrip("v")
            if required > MAIFORGE_VERSION:
                raise ModLoadingException(
                    f"Mod {info.mod_id} requires maiforge API {info.maiforge_api} "
                    f"but maiforge is {MAIFORGE_VERSION}"
                )

        return info

    def load_mod(self, zip_path: Path) -> ModContainer:
        """Load a single mod ZIP.  Returns the ModContainer."""
        archive = zipfile.ZipFile(zip_path, "r")

        # Attempt to load manifest
        manifest = None
        for candidate in ("mod.toml", "mod.json", "manifest.json"):
            try:
                with archive.open(candidate) as fh:
                    text = fh.read().decode("utf-8")
                    manifest = json.loads(text)
                    break
            except KeyError:
                continue

        if manifest is None:
            raise ModLoadingException(
                f"No mod.toml / mod.json / manifest.json found in {zip_path.name}"
            )

        info = self.validate_manifest(manifest)

        # Check duplicates — prefer newer version, skip older
        if info.mod_id in self.mods:
            existing = self.mods[info.mod_id]
            existing_ver = _parse_version(existing.info.version)
            new_ver = _parse_version(info.version)
            if new_ver <= existing_ver:
                logger.warning(
                    "Skipping %s (v%s): already have newer v%s",
                    zip_path.name, info.version, existing.info.version,
                )
                return None  # skip, don't error
            # Newer — unload old, load new
            logger.info(
                "Replacing %s v%s with v%s",
                info.mod_id, existing.info.version, info.version,
            )
            existing.disable()
            del self.mods[info.mod_id]

        container = ModContainer(zip_path, info)
        container.load()
        self.mods[info.mod_id] = container
        logger.info("Loaded mod: %s v%s (%s)", info.name, info.version, info.mod_id)
        return container

    def load_all(self) -> dict[str, ModContainer]:
        """Discover and load all mods in the mods directory."""
        for zip_path in self.discover():
            try:
                self.load_mod(zip_path)
            except Exception as exc:
                logger.error("Failed to load %s: %s", zip_path.name, exc)
        return self.mods

    def unload_mod(self, mod_id: str) -> bool:
        """Unload and remove a mod.  Returns True if the mod was found."""
        container = self.mods.pop(mod_id, None)
        if container is None:
            return False
        container.disable()
        logger.info("Unloaded mod: %s", mod_id)
        return True

    def unload_all(self) -> None:
        """Unload all mods."""
        for mod_id in list(self.mods.keys()):
            self.unload_mod(mod_id)

    def get_mod(self, mod_id: str) -> Optional[ModContainer]:
        return self.mods.get(mod_id)

    def get_all_mods(self) -> list[ModContainer]:
        return list(self.mods.values())
