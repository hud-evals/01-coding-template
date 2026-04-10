import pytest
from soc_simulator import ContainmentGraph

def test_blast_radius():
    graph = ContainmentGraph()
    graph.add_edge("compromised_host", "switch_a")
    graph.add_edge("switch_a", "server_1")
    graph.add_edge("server_1", "router")
    
    radius = graph.get_blast_radius("compromised_host", steps=2)
    assert "compromised_host" in radius
    assert "switch_a" in radius
    assert "server_1" in radius
    assert "router" not in radius

def test_isolation_plan_success():
    """Compromised host has one link, no critical infrastructure fragmentation."""
    graph = ContainmentGraph()
    graph.add_edge("critical_db", "main_switch")
    graph.add_edge("critical_api", "main_switch")
    graph.add_edge("compromised_endpoint", "main_switch")
    
    graph.mark_critical("critical_db")
    graph.mark_critical("critical_api")
    
    plan = graph.calculate_isolation_plan("compromised_endpoint")
    assert len(plan) == 1
    
    # Execute should remove the edge
    graph.execute_isolation(plan)
    assert "main_switch" not in graph.edges.get("compromised_endpoint", set())

def test_isolation_causes_fragmentation():
    """
    If isolating the node removes the ONLY bridge between 
    two critical nodes, it should raise ValueError.
    """
    graph = ContainmentGraph()
    # Topology where compromised is the bridge
    graph.add_edge("critical_subnet_A", "legacy_bridge_router")
    graph.add_edge("critical_subnet_B", "legacy_bridge_router")
    
    graph.mark_critical("critical_subnet_A")
    graph.mark_critical("critical_subnet_B")
    
    with pytest.raises(ValueError, match="fragments critical node"):
        graph.calculate_isolation_plan("legacy_bridge_router")
