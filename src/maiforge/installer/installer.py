"""
Installer – injects maiforge bootstrap into the host application startup.
Mirrors Forge's installer that patches the vanilla launcher profile.
"""
from __future__ import annotations

import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("maiforge.installer")

BOOTSTRAP_CODE = '''
# === MAIFORGE BOOTSTRAP (auto-generated, do not edit) ===
import sys
from pathlib import Path

_maiforge_path = Path(__file__).resolve().parent.parent / "maiforge" / "src"
if _maiforge_path.exists() and str(_maiforge_path) not in sys.path:
    sys.path.insert(0, str(_maiforge_path))

try:
    from maiforge.core.forge import MaiForge
    _forge = MaiForge()
    _forge.initialize()
    _forge.load_mods()
    print(f"[MaiForge] Loaded {len(_forge.loader.mods)} mod(s)")
except Exception as _e:
    print(f"[MaiForge] Bootstrap failed: {_e}")
# === END MAIFORGE BOOTSTRAP ===
'''


class Installer:
    """Handles first-time injection and full uninstall."""

    def __init__(self, host_dir: Path) -> None:
        self.host_dir = Path(host_dir)
        self._bootstrap_file = self.host_dir / "maiforge_bootstrap.py"
        self._backup_file = self.host_dir / "maiforge_bootstrap.py.bak"

    @property
    def is_installed(self) -> bool:
        return self._bootstrap_file.exists()

    def install(self) -> bool:
        """Write the bootstrap file and inject the import into the host entrypoint."""
        if self.is_installed:
            logger.info("MaiForge is already installed")
            return True

        # 1. Write bootstrap module
        self._bootstrap_file.write_text(BOOTSTRAP_CODE, encoding="utf-8")
        logger.info("Bootstrap written to %s", self._bootstrap_file)

        # 2. Inject import into the main bot.py
        try:
            self._inject_into_main()
        except Exception as exc:
            logger.warning("Could not auto-inject into main script: %s", exc)
            logger.info(
                "Please add this line near the top of your main entrypoint:\n"
                "    import maiforge_bootstrap"
            )

        logger.info("MaiForge installed successfully")
        return True

    def _inject_into_main(self) -> None:
        """Insert `import maiforge_bootstrap` at the top of bot.py if not present."""
        candidates = ["bot.py", "main.py", "app.py", "run.py"]
        for name in candidates:
            target = self.host_dir / name
            if not target.exists():
                continue
            lines = target.read_text("utf-8").splitlines(True)
            if any("maiforge_bootstrap" in line for line in lines):
                logger.info("Bootstrap already imported in %s", name)
                return

            # Backup
            shutil.copy2(target, str(target) + ".bak")
            # Insert after the docstring / first imports
            insert_at = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped == "":
                    continue
                if stripped.startswith("import ") or stripped.startswith("from "):
                    insert_at = i + 1
                    continue
                insert_at = i
                break
            lines.insert(insert_at, "import maiforge_bootstrap  # MaiForge auto-injection\n")
            target.write_text("".join(lines), encoding="utf-8")
            logger.info("Injected bootstrap import into %s", name)
            return

    def uninstall(self) -> bool:
        """Remove the bootstrap file and restore the original entrypoint."""
        if not self.is_installed:
            return True

        # 1. Remove bootstrap file
        self._bootstrap_file.unlink(missing_ok=True)
        logger.info("Removed %s", self._bootstrap_file)

        # 2. Restore original entrypoint
        for name in ["bot.py", "main.py", "app.py", "run.py"]:
            target = self.host_dir / name
            backup = self.host_dir / (name + ".bak")
            if backup.exists():
                shutil.move(str(backup), str(target))
                logger.info("Restored original %s", name)
                break
            if target.exists():
                lines = target.read_text("utf-8").splitlines(True)
                filtered = [l for l in lines if "maiforge_bootstrap" not in l]
                target.write_text("".join(filtered), encoding="utf-8")
                logger.info("Removed bootstrap import from %s", name)
                break

        # 3. Remove maiforge source directory
        forge_dir = self.host_dir.parent / "maiforge"
        if forge_dir.exists():
            shutil.rmtree(forge_dir)
            logger.info("Removed %s", forge_dir)

        logger.info("MaiForge uninstalled successfully")
        return True
