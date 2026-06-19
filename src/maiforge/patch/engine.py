"""
PatchEngine – non-invasive function hooking for the host application.

Provides:
- Monkey-patch arbitrary functions without editing source
- Pre/post hooks (before / after the original call)
- Full replacement (override)
- Patches are reversible (uninstall restores originals)

Usage (mod side):
    from maiforge.api import patch

    @patch("bot.src.some_module.some_func")
    def my_override(original, *args, **kwargs):
        # do something before
        result = original(*args, **kwargs)
        # do something after
        return result
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("maiforge.patch")


class PatchPoint:
    """Represents a single hook on a target callable."""

    def __init__(
        self,
        target_path: str,
        hook: Callable,
        *,
        mode: str = "wrap",  # wrap / before / after / replace
    ) -> None:
        self.target_path = target_path
        self.hook = hook
        self.mode = mode
        self._original: Optional[Callable] = None
        self._module_name, self._attr_name = target_path.rsplit(".", 1)

    def apply(self) -> bool:
        """Install the hook.  Returns True on success."""
        try:
            module = importlib.import_module(self._module_name)
        except ImportError:
            logger.error("Cannot import %s", self._module_name)
            return False
        self._original = getattr(module, self._attr_name, None)
        if self._original is None:
            logger.error("Attribute %s not found on %s", self._attr_name, self._module_name)
            return False

        original = self._original

        if self.mode == "replace":
            setattr(module, self._attr_name, self.hook)
        elif self.mode == "before":

            def _before(*args: Any, **kwargs: Any) -> Any:
                self.hook(*args, **kwargs)
                return original(*args, **kwargs)

            setattr(module, self._attr_name, _before)
        elif self.mode == "after":

            def _after(*args: Any, **kwargs: Any) -> Any:
                result = original(*args, **kwargs)
                self.hook(result, *args, **kwargs)
                return result

            setattr(module, self._attr_name, _after)
        else:  # wrap

            def _wrap(*args: Any, **kwargs: Any) -> Any:
                return self.hook(original, *args, **kwargs)

            setattr(module, self._attr_name, _wrap)

        logger.info("Patched %s (mode=%s)", self.target_path, self.mode)
        return True

    def revert(self) -> bool:
        """Restore the original function.  Returns True on success."""
        if self._original is None:
            return False
        try:
            module = importlib.import_module(self._module_name)
            setattr(module, self._attr_name, self._original)
            logger.info("Reverted %s", self.target_path)
            return True
        except ImportError:
            return False


class PatchEngine:
    """Manages a collection of PatchPoints."""

    def __init__(self) -> None:
        self._patches: list[PatchPoint] = []

    def add(self, target: str, hook: Callable, *, mode: str = "wrap") -> PatchPoint:
        pp = PatchPoint(target, hook, mode=mode)
        self._patches.append(pp)
        return pp

    def apply_all(self) -> int:
        """Apply all registered patches.  Returns count of successful applications."""
        count = 0
        for pp in self._patches:
            if pp.apply():
                count += 1
        return count

    def revert_all(self) -> int:
        """Revert all patches.  Returns count of successful reversions."""
        count = 0
        for pp in self._patches:
            if pp.revert():
                count += 1
        return count

    def clear(self) -> None:
        self._patches.clear()
