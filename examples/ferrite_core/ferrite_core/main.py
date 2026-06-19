"""铁氧体磁芯 (Ferrite Core) — MaiBot 内存优化模组 v1.2

功能：
1. GC 调优 — 降低阈值，及时回收
2. 内存监控 — 控制台 + WebUI 面板 + 侧边栏
3. WebUI 注入 — 自动在左侧导航栏添加「模组管理」
4. 垃圾回收触发器 — 定时 + 超阈值回收
目标：300-400MB → 100-150MB
"""
from __future__ import annotations

import gc
import sys
import time
import threading
import logging
from typing import Any, Optional

logger = logging.getLogger("ferrite_core")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[ferrite_core] %(message)s"))
    logger.addHandler(_h)

CONFIG = {
    "gc_threshold": (300, 5, 5),
    "gc_interval_seconds": 60,
    "memory_report_interval": 60,
    "memory_warning_mb": 300,
    "enable_malloc_trim": True,
    "startup_report_mb": 100,
}


class MemoryMonitor:
    def __init__(self) -> None:
        self._peak_mb = 0.0
        self._current_mb = 0.0
        self._start_time = time.time()
        self._freed_total_mb = 0.0

    def get_current_mb(self) -> float:
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1048576.0
        except Exception:
            pass
        try:
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        except Exception:
            pass
        return 0.0

    def record(self) -> float:
        mb = self.get_current_mb()
        self._current_mb = mb
        if mb > self._peak_mb:
            self._peak_mb = mb
        return mb

    @property
    def peak_mb(self) -> float:
        return self._peak_mb

    @property
    def current_mb(self) -> float:
        return self._current_mb

    def report(self) -> str:
        return (
            f"[铁氧体磁芯] 内存: {self._current_mb:.0f}MB | "
            f"峰值: {self._peak_mb:.0f}MB | "
            f"GC: {gc.get_count()}"
        )


class GCTuner:
    def __init__(self, monitor: MemoryMonitor) -> None:
        self._monitor = monitor
        self._original_threshold = gc.get_threshold()
        self._last_full_gc = 0.0

    def apply(self) -> None:
        gc.set_threshold(*CONFIG["gc_threshold"])

    def restore(self) -> None:
        gc.set_threshold(*self._original_threshold)

    def maybe_collect(self) -> None:
        now = time.time()
        if now - self._last_full_gc >= CONFIG["gc_interval_seconds"]:
            self._last_full_gc = now
            before = self._monitor.get_current_mb()
            gc.collect()
            after = self._monitor.get_current_mb()
            freed = before - after
            if freed > 0:
                self._monitor._freed_total_mb += freed
            return
        if self._monitor.get_current_mb() > CONFIG["memory_warning_mb"]:
            before = self._monitor.get_current_mb()
            gc.collect()
            after = self._monitor.get_current_mb()
            freed = before - after
            if freed > 1:
                self._monitor._freed_total_mb += freed
                logger.info(f"⚠ 内存告警回收: {before:.0f}MB → {after:.0f}MB | 释放 {freed:.1f}MB")
            return
        gc.collect(0)


# 全局状态
_monitor: Optional[MemoryMonitor] = None
_tuner: Optional[GCTuner] = None
_stop_flag: Optional[threading.Event] = None


def on_enable(forge) -> None:
    global _monitor, _tuner, _stop_flag

    _monitor = MemoryMonitor()
    _tuner = GCTuner(_monitor)
    _stop_flag = threading.Event()
    _tuner.apply()

    before = _monitor.record()
    gc.collect()
    after = _monitor.record()

    logger.info("=" * 50)
    logger.info(f"[铁氧体磁芯] 已启用 | 当前: {after:.0f}MB | GC阈值: {CONFIG['gc_threshold']}")
    if before - after > 5:
        logger.info(f"[铁氧体磁芯] 初始回收: {before-after:.0f}MB")
    logger.info("=" * 50)

    if CONFIG["enable_malloc_trim"] and sys.platform == "linux":
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    def _gc_loop():
        while not _stop_flag.is_set():
            try:
                _tuner.maybe_collect()
            except Exception:
                pass
            _stop_flag.wait(10)
    threading.Thread(target=_gc_loop, daemon=True, name="ferrite-gc").start()

    def _report_loop():
        _stop_flag.wait(30)
        while not _stop_flag.is_set():
            mb = _monitor.record()
            logger.info(_monitor.report())
            _stop_flag.wait(CONFIG["memory_report_interval"])
    threading.Thread(target=_report_loop, daemon=True, name="ferrite-report").start()

    # 注入侧边栏脚本
    _inject_sidebar_script()


def _inject_sidebar_script() -> None:
    """在 dashboard index.html 中注入侧边栏脚本"""
    try:
        import maibot_dashboard
        dist = maibot_dashboard.get_dist_path()
        idx = dist / "index.html"
        if not idx.exists():
            return

        content = idx.read_text("utf-8")
        if "ferrite-sidebar" in content:
            return

        bak = dist / "index.html.bak"
        if not bak.exists():
            idx.rename(bak)
        else:
            idx.write_text(bak.read_text("utf-8"), "utf-8")
            content = bak.read_text("utf-8")

        injected = content.replace("</body>", _SIDEBAR_JS + "\n</body>")
        if injected == content:
            injected = content + "\n" + _SIDEBAR_JS
        idx.write_text(injected, "utf-8")
        logger.info("[铁氧体磁芯] 侧边栏脚本已注入")
    except Exception as exc:
        logger.warning(f"[铁氧体磁芯] 侧边栏注入失败: {exc}")


def on_disable() -> None:
    global _stop_flag
    if _stop_flag:
        _stop_flag.set()
    if _tuner:
        _tuner.restore()
    if _monitor:
        logger.info(f"[铁氧体磁芯] 已关闭 | 峰值: {_monitor.peak_mb:.0f}MB")
    try:
        import maibot_dashboard
        dist = maibot_dashboard.get_dist_path()
        bak = dist / "index.html.bak"
        idx = dist / "index.html"
        if bak.exists():
            idx.unlink(missing_ok=True)
            bak.rename(idx)
    except Exception:
        pass


_SIDEBAR_JS = """<script>
(function(){
if(window.__ferrite_done)return;window.__ferrite_done=true;
var tries=0;
function findNav(){
  return document.querySelector('nav')||document.querySelector('[class*=sidebar] ul')||document.querySelector('aside ul');
}
function inject(nav){
  if(document.getElementById('fm'))return true;
  var items=nav.querySelectorAll('li,a');
  var found=null;
  for(var i=0;i<items.length;i++){
    if((items[i].textContent||'').indexOf('插件')>-1){found=items[i];break}
  }
  var li=document.createElement('li');
  li.id='fm';
  li.innerHTML='<a href=\"/api/webui/maiforge/mods\" style=\"display:flex;align-items:center;gap:8px;text-decoration:none;color:inherit\">📦 模组管理</a>';
  if(found&&found.parentNode){
    found.parentNode.insertBefore(li,found.nextSibling);
    console.log('[铁氧体磁芯] sidebar injected');
    return true
  }
  nav.appendChild(li);
  return true
}
function go(){
  var n=findNav();
  if(n&&inject(n))return;
  tries++;
  if(tries<40)setTimeout(go,400);
  else new MutationObserver(function(){var n=findNav();if(n){inject(n);this.disconnect()}}).observe(document.body,{childList:true,subtree:true})
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);
else go();
})();
</script>
"""
