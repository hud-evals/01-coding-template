import pytest
import sys
sys.path.insert(0, "/home/ubuntu/workspace")
from codesign_engine import ISA, Instruction, ArchitectureExplorerAgent

def test_isa_add_and_count():
    isa = ISA("TestArch", word_size=32)
    isa.add_instruction(Instruction("ADD", ["rd", "rs1", "rs2"], 1, 0.5))
    isa.add_instruction(Instruction("SUB", ["rd", "rs1", "rs2"], 1, 0.5))
    assert isa.instruction_count() == 2
    assert isa.get_instruction("ADD") is not None
    assert isa.get_instruction("XOR") is None

def test_isa_avg_power():
    isa = ISA("PowerTest")
    isa.add_instruction(Instruction("A", [], 1, 1.0))
    isa.add_instruction(Instruction("B", [], 1, 3.0))
    assert abs(isa.avg_power() - 2.0) < 1e-9

def test_risc_architecture():
    explorer = ArchitectureExplorerAgent()
    risc = explorer.propose_risc()
    assert risc.name == "RISC-Lite"
    assert risc.word_size == 32
    assert risc.instruction_count() == 10
    assert risc.get_instruction("ADD") is not None
    assert risc.get_instruction("HALT") is not None

def test_neuromorphic_architecture():
    explorer = ArchitectureExplorerAgent()
    neuro = explorer.propose_neuromorphic()
    assert neuro.name == "NeuroCore-v1"
    assert neuro.word_size == 16
    assert neuro.register_count == 8
    assert neuro.get_instruction("SPIKE") is not None
    assert neuro.get_instruction("FIRE") is not None

def test_compare_architectures():
    explorer = ArchitectureExplorerAgent()
    risc = explorer.propose_risc()
    neuro = explorer.propose_neuromorphic()
    comparison = explorer.compare_architectures(risc, neuro)
    assert "recommendation" in comparison
    assert comparison["arch_a"] == "RISC-Lite"
    assert comparison["arch_b"] == "NeuroCore-v1"
    # Neuromorphic should be lower power
    assert comparison["avg_power_b"] < comparison["avg_power_a"]
