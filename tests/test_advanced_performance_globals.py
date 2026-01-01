from __future__ import annotations


def test_advanced_performance_globals_lazy_init_and_shutdown():
    from src.utils.advanced_performance import (
        get_preloader,
        get_task_queue,
        shutdown_global_performance_tools,
    )

    p1 = get_preloader()
    p2 = get_preloader()
    assert p1 is p2

    q1 = get_task_queue()
    q2 = get_task_queue()
    assert q1 is q2

    shutdown_global_performance_tools()
    shutdown_global_performance_tools()  # idempotent

    p3 = get_preloader()
    assert p3 is not p1

    q3 = get_task_queue()
    assert q3 is not q1

    shutdown_global_performance_tools()
