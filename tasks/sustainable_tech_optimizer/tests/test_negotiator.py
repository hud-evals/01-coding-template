import pytest
from green_optimizer import TradeoffNegotiator, OptimizerNetwork, Datacenter, Workload, WeatherData

def test_negotiator_sla_filtering():
    net = OptimizerNetwork(
        [
            Datacenter("far_cheap", "reg1", 100.0, 0.0, 1.0, 100.0),
            Datacenter("close_expensive", "reg2", 100.0, 0.0, 1.0, 500.0)
        ], {}, {}
    )
    
    wl = Workload("w1", 10.0, 40.0, False)
    weathers = {}
    latencies = {"far_cheap": 100.0, "close_expensive": 10.0} # far_cheap violates SLA 40ms
    
    best_dc = net.negotiator.negotiate_placement(wl, list(net.datacenters.values()), weathers, latencies)
    assert best_dc == "close_expensive"

def test_process_workload_batch():
    net = OptimizerNetwork(
        [
            Datacenter("dc_a", "regA", 50.0, 40.0, 1.0, 100.0), # 10 rem
            Datacenter("dc_b", "regB", 50.0, 20.0, 1.0, 200.0)  # 30 rem
        ], {}, {}
    )
    
    wls = [
        Workload("w_heavy", 20.0, 100.0, True),
        Workload("w_light", 5.0, 100.0, True)
    ]
    
    # Both DCs are within latency for both workloads
    lat_matrix = {"w_heavy": {"dc_a": 10, "dc_b": 10}, "w_light": {"dc_a": 10, "dc_b": 10}}
    assignments = net.process_workload_batch(wls, {}, lat_matrix)
    
    # w_light can fit in dc_a (cleanest). w_heavy cannot fit in dc_a, must go to dc_b.
    assert assignments.get("w_light") == "dc_a"
    assert assignments.get("w_heavy") == "dc_b"
