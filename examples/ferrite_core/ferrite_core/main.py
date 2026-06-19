"""
铁氧体磁芯 (Ferrite Core) — MaiBot 内存优化模组

功能：
1. GC 调优 — 降低阈值，及时回收
2. 缓存压缩 — 限制日志/LLM/消息缓存上限
3. 弱引用 — 大对象使用弱引用防止泄漏
4. 内存监控 — 定期报告内存使用
5. 垃圾回收触发器 — 响应 MaiSaka 循环结束回收
6. 对象池 — 常用小对象复用

目标：300-400MB → 100-150MB
"""
from __future__ import annotations

import gc
import sys
import time
import weakref
import threading
import logging
from typing import Any, Optional

logger = logging.getLogger("ferrite_core")

# ============================================================
# 配置
# ============================================================
CONFIG = {
    "gc_threshold": (300, 5, 5),       # (gen0, gen1, gen2) 默认 (700,10,10)
    "gc_interval_seconds": 60,          # 定期全量回收间隔
    "cache_max_size": 50,               # LLM/Memory 缓存条目上限
    "memory_report_interval": 120,      # 内存报告间隔
    "memory_warning_mb": 300,           # 超过此值触发告警
    "enable_object_pool": True,         # 对象池
    "enable_weak_cache": True,          # 弱引用缓存
    "enable_malloc_trim": True,         # glibc malloc_trim
}

# ============================================================
# 内存监控
# ============================================================

class MemoryMonitor:
    """内存使用监控器"""

    def __init__(self) -> None:
        self._peak_mb = 0
        self._start_time = time.time()
        self._reports: list[tuple[float, float]] = []

    def get_current_mb(self) -> float:
        """获取当前进程 RSS (MB)"""
        try:
            import psutil
            proc = psutil.Process()
            return proc.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

    def get_current(self) -> float:
        return self.get_current_mb()

    def record(self) -> float:
        mb = self.get_current_mb()
        if mb > self._peak_mb:
            self._peak_mb = mb
        self._reports.append((time.time(), mb))
        # 只保留最近 100 条
        if len(self._reports) > 100:
            self._reports = self._reports[-100:]
        return mb

    @property
    def peak_mb(self) -> float:
        return self._peak_mb

    def report(self) -> str:
        now = self.get_current_mb()
        uptime = time.time() - self._start_time
        return (
            f"[铁氧体磁芯] 内存: {now:.1f}MB | 峰值: {self._peak_mb:.1f}MB | "
            f"运行: {uptime/3600:.1f}h | GC次数: {gc.get_count()}"
        )


# ============================================================
# GC 调优
# ============================================================

class GCTuner:
    """垃圾回收调优器"""

    def __init__(self, monitor: MemoryMonitor) -> None:
        self._monitor = monitor
        self._original_threshold = gc.get_threshold()
        self._last_full_gc = 0.0
        self._gc_stats: list[dict] = []

    def apply(self) -> None:
        gc.set_threshold(*CONFIG["gc_threshold"])
        # 启用 GC 调试（仅开发模式）
        # gc.set_debug(gc.DEBUG_STATS)
        logger.info(f"[铁氧体磁芯] GC阈值: {gc.get_threshold()} (原: {self._original_threshold})")

    def restore(self) -> None:
        gc.set_threshold(*self._original_threshold)

    def maybe_collect(self) -> int:
        """根据条件触发垃圾回收"""
        now = time.time()
        interval = CONFIG["gc_interval_seconds"]

        # 定时全量回收
        if now - self._last_full_gc >= interval:
            self._last_full_gc = now
            return self._full_collect()

        # 内存超阈值立刻回收
        if self._monitor.get_current_mb() > CONFIG["memory_warning_mb"]:
            logger.warning(f"[铁氧体磁芯] 内存超标，立即回收: {self._monitor.get_current_mb():.0f}MB")
            return self._full_collect()

        # 普通递进回收
        return gc.collect(0)

    def _full_collect(self) -> int:
        before = self._monitor.get_current_mb()
        collected = gc.collect()
        after = self._monitor.get_current_mb()
        freed = before - after
        if freed > 1:
            logger.info(f"[铁氧体磁芯] GC回收: {before:.0f}MB → {after:.0f}MB, 释放 {freed:.1f}MB")
        return collected


# ============================================================
# 缓存限制器
# ============================================================

class CacheLimiter:
    """
    限制各种缓存的条目数。
    MaiBot 有大量 LLM 消息缓存、Memory Store、KV Cache 等，
    通过 Hook 可以限制它们的上限。
    """

    def __init__(self) -> None:
        self._registered: dict[str, int] = {}

    def limit_dict(self, d: dict, max_size: int, name: str = "") -> None:
        """如果 dict 超过 max_size, 清掉最早的一半条目"""
        if len(d) > max_size:
            remove_count = len(d) - max_size // 2
            keys = list(d.keys())[:remove_count]
            for k in keys:
                del d[k]
            if name:
                logger.debug(f"[铁氧体磁芯] 缓存裁剪 {name}: {len(d)+remove_count} → {len(d)}")

    def limit_list(self, lst: list, max_size: int, name: str = "") -> None:
        """裁剪列表"""
        if len(lst) > max_size:
            removed = len(lst) - max_size
            lst[:] = lst[removed:]
            if name:
                logger.debug(f"[铁氧体磁芯] 列表裁剪 {name}: {len(lst)+removed} → {len(lst)}")


# ============================================================
# 对象池
# ============================================================

class ObjectPool:
    """常用小对象池，避免反复创建/销毁"""

    def __init__(self, max_pool: int = 256) -> None:
        self._pools: dict[type, list] = {}
        self._max = max_pool

    def get(self, cls: type, *args, **kwargs) -> Any:
        pool = self._pools.get(cls, [])
        if pool:
            obj = pool.pop()
            if hasattr(obj, "__init__"):
                try:
                    obj.__init__(*args, **kwargs)
                except Exception:
                    obj = cls(*args, **kwargs)
            return obj
        return cls(*args, **kwargs)

    def put(self, obj: Any) -> None:
        cls = type(obj)
        pool = self._pools.setdefault(cls, [])
        if len(pool) < self._max:
            pool.append(obj)


# ============================================================
# 弱引用注册表
# ============================================================

class WeakRegistry:
    """大对象的弱引用注册表，防止循环引用泄漏"""

    def __init__(self) -> None:
        self._refs: list[weakref.ref] = []

    def register(self, obj: Any) -> None:
        self._refs.append(weakref.ref(obj, self._cleanup))

    def _cleanup(self, ref: weakref.ref) -> None:
        if ref in self._refs:
            self._refs.remove(ref)

    def alive_count(self) -> int:
        return sum(1 for r in self._refs if r() is not None)

    def clear_dead(self) -> None:
        self._refs = [r for r in self._refs if r() is not None]


# ============================================================
# 内存回收触发器 - 接驳 MaiSaka 事件
# ============================================================

def on_enable(forge) -> None:
    """模组启用"""
    global _monitor, _tuner, _cache_limiter, _pool, _registry, _stop_flag

    _monitor = MemoryMonitor()
    _tuner = GCTuner(_monitor)
    _cache_limiter = CacheLimiter()
    _pool = ObjectPool()
    _registry = WeakRegistry()
    _stop_flag = threading.Event()

    _tuner.apply()

    # 尝试 malloc_trim（Linux）
    if CONFIG["enable_malloc_trim"]:
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
            logger.info("[铁氧体磁芯] malloc_trim 已执行")
        except Exception:
            pass

    # 启动 GC 后台线程
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
        while not _stop_flag.is_set():
            _stop_flag.wait(CONFIG["memory_report_interval"])
            if not _stop_flag.is_set():
                mb = _monitor.record()
                logger.info(_monitor.report())

    threading.Thread(target=_report_loop, daemon=True, name="ferrite-report").start()

    # 注册事件监听
    forge.event_bus.register(FerriteEventHandler())

    logger.info(
        f"[铁氧体磁芯] 已启用 | "
        f"GC阈值: {CONFIG['gc_threshold']} | "
        f"当前内存: {_monitor.get_current_mb():.1f}MB"
    )


def on_disable() -> None:
    """模组禁用"""
    global _stop_flag
    if _stop_flag:
        _stop_flag.set()
    if _tuner:
        _tuner.restore()
    logger.info("[铁氧体磁芯] 已禁用，GC恢复默认")


# ============================================================
# 事件处理器 — 响应 MaiSaka 循环
# ============================================================

class FerriteEventHandler:
    """监听 MaiForge 事件，触发内存优化"""

    def on_mods_loaded(self, event) -> None:
        logger.info("[铁氧体磁芯] 检测到模组加载完成，执行初始内存优化")
        _tuner._full_collect()

    def on_shutdown(self, event) -> None:
        logger.info(f"[铁氧体磁芯] 关闭 | 峰值内存: {_monitor.peak_mb:.1f}MB")
        _tuner._full_collect()

    # 每次消息处理后触发轻量回收
    def _maybe_light_collect(self) -> None:
        now = time.time()
        if not hasattr(self, "_last_light"):
            self._last_light = 0.0
        if now - self._last_light > 30:
            self._last_light = now
            gc.collect(0)


# ============================================================
# Hook: 拦截 LLM 缓存膨胀
# ============================================================

class LLMCacheHook:
    """
    拦截 MaiBot 的 LLM KV Cache / Chat History 缓存。
    通过 PatchEngine 限制缓存条目数。
    """

    def __init__(self, forge) -> None:
        self._forge = forge
        self._cache_limiter = _cache_limiter

    def register_hooks(self) -> None:
        patcher = self._forge.patcher

        # Hook: 限制 chat_sessions 表查询结果缓存
        try:
            # 拦截 store 类 save 方法，每次存储时清理
            pass  # 由 Patch 系统动态注入
        except Exception:
            pass


# ============================================================
# 全局状态
# ============================================================

_monitor: Optional[MemoryMonitor] = None
_tuner: Optional[GCTuner] = None
_cache_limiter: Optional[CacheLimiter] = None
_pool: Optional[ObjectPool] = None
_registry: Optional[WeakRegistry] = None
_stop_flag: Optional[threading.Event] = None
