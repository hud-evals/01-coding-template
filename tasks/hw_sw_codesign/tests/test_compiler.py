import pytest
import sys
sys.path.insert(0, "/home/ubuntu/workspace")
from codesign_engine import (
    Program, CompilerOptimizerAgent, ArchitectureExplorerAgent
)

def test_validate_valid_program():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    compiler = CompilerOptimizerAgent()

    prog = Program("test")
    prog.add("ADD", ["R1", "R2", "R3"])
    prog.add("SUB", ["R4", "R1", "R3"])
    prog.add("HALT", [])

    result = compiler.validate_program(prog, isa)
    assert result["valid"] is True
    assert len(result["errors"]) == 0

def test_validate_invalid_opcode():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    compiler = CompilerOptimizerAgent()

    prog = Program("bad")
    prog.add("FAKE_OP", ["R1"])

    result = compiler.validate_program(prog, isa)
    assert result["valid"] is False
    assert len(result["errors"]) == 1

def test_dead_code_elimination():
    compiler = CompilerOptimizerAgent()
    prog = Program("nop_test")
    prog.add("ADD", ["R1", "R2", "R3"])
    prog.add("NOP", [])
    prog.add("NOP", [])
    prog.add("SUB", ["R4", "R1", "R3"])

    optimized = compiler.dead_code_elimination(prog)
    assert optimized.length() == 2
    assert optimized.instructions[0].opcode == "ADD"
    assert optimized.instructions[1].opcode == "SUB"

def test_strength_reduction():
    compiler = CompilerOptimizerAgent()
    prog = Program("strength_test")
    prog.add("MUL", ["R1", "R2", "2"])
    prog.add("DIV", ["R3", "R4", "1"])

    reduced = compiler.strength_reduction(prog)
    assert reduced.instructions[0].opcode == "ADD"
    assert reduced.instructions[0].operands == ["R1", "R2", "R2"]
    assert reduced.instructions[1].opcode == "ADD"

def test_full_optimize():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    compiler = CompilerOptimizerAgent()

    prog = Program("full_opt")
    prog.add("ADD", ["R1", "R2", "R3"])
    prog.add("NOP", [])
    prog.add("MUL", ["R4", "R5", "2"])
    prog.add("HALT", [])

    optimized, report = compiler.optimize(prog, isa)
    assert report["original_length"] == 4
    assert report["eliminated_nops"] == 1
    assert optimized.length() == 3
