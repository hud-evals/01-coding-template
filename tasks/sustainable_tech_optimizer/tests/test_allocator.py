import pytest
from green_optimizer import ResourceAllocator, Datacenter, Workload

def test_allocation_success():
    alloc = ResourceAllocator()
    dc = Datacenter("dc1", "US-EAST", 100.0, 80.0, 1.5, 400.0)
    wl = Workload("w1", 15.0, 100.0, False)
    
    assert alloc.can_allocate(wl, dc) is True
    assert alloc.allocate(wl, dc) is True
    assert dc.current_load == 95.0
    
def test_allocation_failure():
    alloc = ResourceAllocator()
    dc = Datacenter("dc1", "US-EAST", 100.0, 90.0, 1.5, 400.0)
    wl = Workload("w1", 15.0, 100.0, False)
    
    assert alloc.can_allocate(wl, dc) is False
    assert alloc.allocate(wl, dc) is False
    assert dc.current_load == 90.0
