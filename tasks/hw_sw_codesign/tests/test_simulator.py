import pytest
import sys
sys.path.insert(0, "/home/ubuntu/workspace")
from codesign_engine import (
    Program, SimulatorAgent, ArchitectureExplorerAgent
)

def test_simple_add_simulation():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("add_test")
    prog.add("ADD", ["R1", "R2", "5"])
    prog.add("ADD", ["R3", "R1", "10"])
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["halted"] is True
    assert result["registers"]["R1"] == 5
    assert result["registers"]["R3"] == 15
    assert result["cycles"] > 0

def test_mul_div_simulation():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("mul_div")
    prog.add("ADD", ["R1", "R0", "12"])
    prog.add("ADD", ["R2", "R0", "3"])
    prog.add("MUL", ["R3", "R1", "R2"])
    prog.add("DIV", ["R4", "R3", "R2"])
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["halted"] is True
    assert result["registers"]["R3"] == 36
    assert result["registers"]["R4"] == 12

def test_energy_tracking():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("energy")
    prog.add("ADD", ["R1", "R0", "1"])
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["energy_mj"] > 0.0
    assert result["instructions_executed"] == 2

def test_div_by_zero():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("div_zero")
    prog.add("DIV", ["R1", "R2", "R0"])
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["registers"]["R1"] == 0  # Should not crash

def test_branch_beq():
    """BEQ should skip instructions when operands are equal."""
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("branch_test")
    prog.add("ADD", ["R1", "R0", "5"])   # R1 = 5
    prog.add("ADD", ["R2", "R0", "5"])   # R2 = 5
    prog.add("BEQ", ["R1", "R2", "2"])   # R1==R2, skip 2 ahead (pc+2)
    prog.add("ADD", ["R3", "R0", "99"])  # SHOULD BE SKIPPED
    prog.add("ADD", ["R4", "R0", "42"])  # land here
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["registers"]["R3"] == 0, "BEQ failed: skipped instruction was executed"
    assert result["registers"]["R4"] == 42

def test_store_load_memory():
    """STORE and LOAD must use memory dict correctly."""
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("mem_test")
    prog.add("ADD", ["R1", "R0", "777"])
    prog.add("STORE", ["R1", "100"])
    prog.add("LOAD", ["R2", "100"])
    prog.add("HALT", [])

    result = sim.execute_program(prog)
    assert result["registers"]["R2"] == 777, f"LOAD/STORE failed: R2={result['registers']['R2']}"

def test_max_cycles_timeout():
    """Infinite loop should be caught by max_cycles."""
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    sim = SimulatorAgent(isa)

    prog = Program("infinite")
    prog.add("ADD", ["R1", "R0", "1"])
    prog.add("BEQ", ["R0", "R0", "-1"])  # always true, jump back forever

    result = sim.execute_program(prog, max_cycles=100)
    assert result["timed_out"] is True
