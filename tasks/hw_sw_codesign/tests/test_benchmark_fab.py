import pytest
import sys
sys.path.insert(0, "/home/ubuntu/workspace")
from codesign_engine import (
    BenchmarkCriticAgent, FabricationAdvisorAgent, ArchitectureExplorerAgent
)

def test_benchmark_grading():
    critic = BenchmarkCriticAgent()
    sim_result = {
        "cycles": 10,
        "energy_mj": 0.005,
        "instructions_executed": 8,
        "halted": True,
        "timed_out": False,
    }
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    analysis = critic.analyze(sim_result, isa)

    assert "ipc" in analysis
    assert "ppa_score" in analysis
    assert "grade" in analysis
    assert analysis["ipc"] > 0.0
    assert analysis["grade"] in ("A", "B", "C", "F")

def test_benchmark_grade_f():
    """Very poor performance should get grade F."""
    critic = BenchmarkCriticAgent()
    sim_result = {
        "cycles": 10000,
        "energy_mj": 50.0,
        "instructions_executed": 5,
        "halted": True,
        "timed_out": False,
    }
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    analysis = critic.analyze(sim_result, isa)
    assert analysis["grade"] == "F"

def test_fabrication_estimate():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()

    est = fab.estimate_die_area(isa, "14nm")
    assert est["process_node"] == "14nm"
    assert est["transistor_count"] > 0
    assert est["die_area_mm2"] > 0.0
    assert est["cost_per_die_usd"] > 0.0

def test_fabrication_exact_transistor_count():
    """Transistor count must be exactly: instructions*50000 + registers*1000."""
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()
    
    est = fab.estimate_die_area(isa, "14nm")
    expected_transistors = isa.instruction_count() * 50000 + isa.register_count * 1000
    assert est["transistor_count"] == expected_transistors, \
        f"Expected {expected_transistors}, got {est['transistor_count']}"

def test_fabrication_invalid_node():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()

    with pytest.raises(ValueError):
        fab.estimate_die_area(isa, "3nm")

def test_fabrication_recommendation():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()

    rec = fab.recommend_node(isa, budget_per_die=10.0)
    assert rec["recommendation"] is not None

def test_fabrication_no_budget():
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()

    rec = fab.recommend_node(isa, budget_per_die=0.0000001)
    assert rec["recommendation"] is None

def test_fabrication_7nm_vs_28nm():
    """7nm should produce smaller die area than 28nm for the same ISA."""
    explorer = ArchitectureExplorerAgent()
    isa = explorer.propose_risc()
    fab = FabricationAdvisorAgent()

    est_7 = fab.estimate_die_area(isa, "7nm")
    est_28 = fab.estimate_die_area(isa, "28nm")
    assert est_7["die_area_mm2"] < est_28["die_area_mm2"]
