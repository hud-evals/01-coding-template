import pytest
import threading
import sys
sys.path.insert(0, "/home/ubuntu/workspace")
from codesign_engine import (
    MessageBus, CoDesignOrchestrator, Program
)

def test_message_bus_thread_safety():
    bus = MessageBus()
    def writer(topic, n):
        for i in range(n):
            bus.publish(topic, {"val": i})

    threads = [
        threading.Thread(target=writer, args=("t1", 50)),
        threading.Thread(target=writer, args=("t1", 50)),
        threading.Thread(target=writer, args=("t2", 30)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(bus.get_history("t1")) == 100
    assert len(bus.get_history("t2")) == 30

def test_orchestrator_risc_pipeline():
    orch = CoDesignOrchestrator()
    prog = Program("bench")
    prog.add("ADD", ["R1", "R0", "10"])
    prog.add("MUL", ["R2", "R1", "R1"])
    prog.add("HALT", [])

    result = orch.run_pipeline(arch_type="risc", program=prog, process_node="14nm", budget=5.0)
    assert result["architecture"]["name"] == "RISC-Lite"
    assert result["simulation"]["halted"] is True
    assert result["benchmark"]["grade"] in ("A", "B", "C", "F")
    assert result["fabrication"]["estimate"]["process_node"] == "14nm"

def test_orchestrator_no_program():
    orch = CoDesignOrchestrator()
    result = orch.run_pipeline(arch_type="neuromorphic", process_node="7nm", budget=2.0)
    assert result["architecture"]["name"] == "NeuroCore-v1"
    assert result["simulation"] is None
    assert result["benchmark"] is None
    assert result["fabrication"]["estimate"]["process_node"] == "7nm"
