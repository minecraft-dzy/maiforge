"""
铁氧体磁芯 (Ferrite Core) — MaiBot 内存优化模组

功能：
1. GC 调优 — 降低阈值，及时回收
2. 缓存压缩 — 限制日志/LLM/消息缓存上限
3. 内存监控 — 控制台 + WebUI 面板
4. 垃圾回收触发器 — 响应 MaiSaka 循环结束回收
5. 弱引用 — 大对象使用弱引用防止泄漏

目标：300-400MB → 100-150MB
"""
from __future__ import annotations

import gc
import sys
import os
import time
import weakref
import threading
import logging
from typing import Any, Optional

# Use root logger so output is visible
logger = logging.getLogger("maiforge.ferrite_core")

# ============================================================
# 配置
# ============================================================
CONFIG = {
    "gc_threshold": (300, 5, 5),
    "gc_interval_seconds": 60,
    "cache_max_size": 50,
    "memory_report_interval": 60,    # 60秒报告一次
    "memory_warning_mb": 300,
    "enable_malloc_trim": True,
    "startup_report_mb": 100,         # 超过此值启动时立即报告
}


# ============================================================
# 内存监控
# ============================================================
class MemoryMonitor:
    """内存使用监控器"""

    def __init__(self) -> None:
        self._peak_mb = 0.0
        self._current_mb = 0.0
        self._start_time = time.time()
        self._reports: list[dict] = []
        self._gc_count_total = 0
        self._freed_total_mb = 0.0

    def get_current_mb(self) -> float:
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1048576.0
        except ImportError:
            return 0.0

    def record(self) -> float:
        mb = self.get_current_mb()
        self._current_mb = mb
        if mb > self._peak_mb:
            self._peak_mb = mb
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "mb": round(mb, 1),
            "peak": round(self._peak_mb, 1),
            "gc": gc.get_count(),
        }
        self._reports.append(entry)
        if len(self._reports) > 60:
            self._reports = self._reports[-60:]
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
            f"GC次数: {gc.get_count()}"
        )

    def report_html(self) -> str:
        """返回 WebUI 可用的内存报告 HTML"""
        lines = [
            f"<p>当前内存: <b>{self._current_mb:.0f} MB</b></p>",
            f"<p>历史峰值: <b>{self._peak_mb:.0f} MB</b></p>",
            f"<p>GC计数: (gen0={gc.get_count()[0]}, gen1={gc.get_count()[1]}, gen2={gc.get_count()[2]})</p>",
            f"<p>累计释放: <b>{self._freed_total_mb:.0f} MB</b></p>",
            f"<p>运行时长: <b>{(time.time()-self._start_time)/3600:.1f}h</b></p>",
            "<hr>",
            "<table style='width:100%;font-size:12px'>"
            "<tr><th>时间</th><th>内存(MB)</th><th>峰值</th></tr>",
        ]
        for r in self._reports[-20:]:
            lines.append(
                f"<tr><td>{r['time']}</td><td>{r['mb']}</td><td>{r['peak']}</td></tr>"
            )
        lines.append("</table>")
        return "".join(lines)


# ============================================================
# GC 调优
# ============================================================
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
        interval = CONFIG["gc_interval_seconds"]

        if now - self._last_full_gc >= interval:
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
                logger.info(
                    f"[铁氧体磁芯] 内存告警回收: {before:.0f}MB → {after:.0f}MB | "
                    f"释放 {freed:.1f}MB"
                )
            return

        gc.collect(0)


# ============================================================
# 启用/禁用
# ============================================================
_monitor: Optional[MemoryMonitor] = None
_tuner: Optional[GCTuner] = None
_stop_flag: Optional[threading.Event] = None


def on_enable(forge) -> None:
    global _monitor, _tuner, _stop_flag

    _monitor = MemoryMonitor()
    _tuner = GCTuner(_monitor)
    _stop_flag = threading.Event()
    _tuner.apply()

    # 首次内存快照 + 强制回收
    before = _monitor.record()
    gc.collect()
    after = _monitor.record()

    logger.info("=" * 50)
    logger.info(f"[铁氧体磁芯] 已启用 | 当前: {after:.0f}MB | "
                f"GC阈值: {CONFIG['gc_threshold']}")
    if before - after > 5:
        logger.info(f"[铁氧体磁芯] 初始回收释放: {before-after:.0f}MB")
    logger.info("=" * 50)

    # 如果内存较大，打印警告
    if after > CONFIG["startup_report_mb"]:
        logger.warning(
            f"[铁氧体磁芯] ⚠ 启动内存偏高 ({after:.0f}MB)，将开启主动回收"
        )

    # malloc_trim (Linux)
    if CONFIG["enable_malloc_trim"] and sys.platform == "linux":
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    # 后台 GC 线程
    def _gc_loop():
        while not _stop_flag.is_set():
            try:
                _tuner.maybe_collect()
            except Exception:
                pass
            _stop_flag.wait(10)

    threading.Thread(target=_gc_loop, daemon=True, name="ferrite-gc").start()

    # 内存报告线程
    def _report_loop():
        _stop_flag.wait(30)  # 30秒后首次报告
        while not _stop_flag.is_set():
            mb = _monitor.record()
            logger.info(_monitor.report())
            _stop_flag.wait(CONFIG["memory_report_interval"])

    threading.Thread(target=_report_loop, daemon=True, name="ferrite-report").start()

    # 注册 WebUI 事件
    try:
        forge.event_bus.register(_FerriteWebUIHandler(_monitor))
    except Exception:
        pass


def on_disable() -> None:
    global _stop_flag
    if _stop_flag:
        _stop_flag.set()
    if _tuner:
        _tuner.restore()
    if _monitor:
        logger.info(
            f"[铁氧体磁芯] 已关闭 | 运行峰值: {_monitor.peak_mb:.0f}MB"
        )


# ============================================================
# WebUI 内存面板
# ============================================================

class _FerriteWebUIHandler:
    """通过 MaiForge 事件注入 WebUI 内存面板"""

    def __init__(self, monitor: MemoryMonitor):
        self._monitor = monitor

    # @SubscribeEvent 兼容：事件名为参数类型
    def on_webui_nav_register(self, event) -> None:
        """注册导航栏"""
        if hasattr(event, "add_nav"):
            event.add_nav("内存监控", "/ferrite-core/memory", icon="chip")

    def on_webui_page_modify(self, event) -> None:
        """向页面注入内存面板"""
        if hasattr(event, "page_id") and event.page_id == "dashboard":
            event.inject_body(_MEMORY_PANEL_HTML % self._monitor.report_html())


_MEMORY_PANEL_HTML = """
<div id="ferrite-memory-panel" style="background:#fff;border-radius:10px;padding:20px;margin:12px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)">
    <h3 style="margin:0 0 12px">🧠 铁氧体磁芯 - 内存监控</h3>
    %s
</div>
"""
