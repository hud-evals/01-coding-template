"""
Sustainable Tech Optimizer Network
Golden Standard Solution

Architecture:
1. Datatypes: Datacenter, Workload
2. EnergyForecaster
3. ResourceAllocator
4. CarbonAuditor
5. TradeoffNegotiator
6. OptimizerNetwork
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import math

@dataclass
class Datacenter:
    id: str
    region: str
    max_compute_capacity: float # MW
    current_load: float # MW
    pue: float # Power Usage Effectiveness (1.0 to 3.0)
    base_carbon_intensity: float # gCO2eq/kWh
    
    @property
    def remaining_capacity(self) -> float:
        return max(0.0, self.max_compute_capacity - self.current_load)

@dataclass
class Workload:
    id: str
    required_compute: float # MW
    max_latency_ms: float
    is_flexible: bool # Can it be delayed or strictly real-time?

@dataclass
class WeatherData:
    region: str
    solar_irradiance: float # 0.0 to 1.0
    wind_speed: float # m/s

class EnergyForecaster:
    """Predicts renewable energy availability reducing the carbon intensity."""
    
    def __init__(self, solar_capacity_mw: Dict[str, float], wind_capacity_mw: Dict[str, float]):
        self.solar_capacity = solar_capacity_mw
        self.wind_capacity = wind_capacity_mw

    def forecast_renewable_out(self, weather: WeatherData) -> float:
        """
        Calculates renewable MW generated in a region.
        Solar: capacity * irradiance * 0.2 (efficiency factor)
        Wind: capacity * (wind_speed/10) capped at capacity.
        """
        solar_mw = self.solar_capacity.get(weather.region, 0.0) * weather.solar_irradiance * 0.2
        
        wind_factor = min(1.0, weather.wind_speed / 10.0) if weather.wind_speed > 0 else 0.0
        wind_mw = self.wind_capacity.get(weather.region, 0.0) * wind_factor
        
        return solar_mw + wind_mw

    def calculate_effective_intensity(self, dc: Datacenter, weather: WeatherData) -> float:
        """
        Returns adjusted gCO2eq/kWh. If renewable power > dc load, intensity drops.
        Simplified: 
        renewable_ratio = min(1.0, renewable_mw / (dc.current_load * dc.pue + 0.1))
        effective_intensity = base_intensity * (1.0 - renewable_ratio)
        """
        ren_mw = self.forecast_renewable_out(weather)
        total_power_needed = dc.current_load * dc.pue
        if total_power_needed <= 0:
            return dc.base_carbon_intensity
            
        ratio = min(1.0, ren_mw / total_power_needed)
        return dc.base_carbon_intensity * (1.0 - ratio)


class ResourceAllocator:
    """Handles constraints for packing workloads into datacenters."""
    
    def can_allocate(self, wl: Workload, dc: Datacenter) -> bool:
        """Check if capacity permits."""
        return dc.remaining_capacity >= wl.required_compute

    def allocate(self, wl: Workload, dc: Datacenter) -> bool:
        if self.can_allocate(wl, dc):
            dc.current_load += wl.required_compute
            return True
        return False
        
    def deallocate(self, wl: Workload, dc: Datacenter):
        dc.current_load = max(0.0, dc.current_load - wl.required_compute)


class CarbonAuditor:
    """Tracks emissions."""
    
    def __init__(self):
        self.total_emissions_g = 0.0
        
    def audit_epoch(self, datacenters: List[Datacenter], forecaster: EnergyForecaster, weathers: Dict[str, WeatherData]):
        """
        Calculates emissions for a 1-hour epoch.
        emissions = Power (MW) * 1000 (kW/MW) * 1h * effective_intensity (g/kWh)
        """
        epoch_emissions = 0.0
        for dc in datacenters:
            weather = weathers.get(dc.region, WeatherData(dc.region, 0.0, 0.0))
            intensity = forecaster.calculate_effective_intensity(dc, weather)
            power_kw = (dc.current_load * dc.pue) * 1000.0
            epoch_emissions += power_kw * intensity
            
        self.total_emissions_g += epoch_emissions
        return epoch_emissions


class TradeoffNegotiator:
    """Multi-Objective Optimizer Agent"""
    
    def __init__(self, allocator: ResourceAllocator, forecaster: EnergyForecaster):
        self.allocator = allocator
        self.forecaster = forecaster

    def negotiate_placement(
        self, 
        workload: Workload, 
        datacenters: List[Datacenter], 
        weathers: Dict[str, WeatherData],
        network_latencies_ms: Dict[str, float] # DC id -> latency
    ) -> Optional[str]:
        """
        Finds the datacenter that minimizes effective carbon intensity.
        Must respect SLA (max_latency_ms) and Capacity bounds.
        Returns the ID of the optimal Datacenter.
        """
        best_dc = None
        min_intensity = float('inf')
        
        for dc in datacenters:
            latency = network_latencies_ms.get(dc.id, float('inf'))
            if latency > workload.max_latency_ms:
                continue
                
            if not self.allocator.can_allocate(workload, dc):
                continue
                
            # Simulate what-if intensity
            weather = weathers.get(dc.region, WeatherData(dc.region, 0.0, 0.0))
            # Test if we placed it
            simulated_load = dc.current_load + workload.required_compute
            simulated_pow = simulated_load * dc.pue
            ren_mw = self.forecaster.forecast_renewable_out(weather)
            ratio = min(1.0, ren_mw / simulated_pow) if simulated_pow > 0 else 0.0
            eff_intensity = dc.base_carbon_intensity * (1.0 - ratio)
            
            if eff_intensity < min_intensity:
                min_intensity = eff_intensity
                best_dc = dc.id
                
        return best_dc


class OptimizerNetwork:
    """Master Multi-Agent Orchestrator"""
    
    def __init__(self, dcs: List[Datacenter], solar_cap: Dict[str, float], wind_cap: Dict[str, float]):
        self.datacenters = {dc.id: dc for dc in dcs}
        self.forecaster = EnergyForecaster(solar_cap, wind_cap)
        self.allocator = ResourceAllocator()
        self.auditor = CarbonAuditor()
        self.negotiator = TradeoffNegotiator(self.allocator, self.forecaster)
        
    def process_workload_batch(
        self, 
        workloads: List[Workload], 
        weathers: Dict[str, WeatherData],
        latency_matrix: Dict[str, Dict[str, float]] # wl_id -> dc_id -> latency
    ) -> Dict[str, str]:
        """
        Attempts to greedily place workloads minimizing carbon.
        Returns mapped assignments: wl.id -> dc.id
        """
        assignments = {}
        # Sort workloads: strict latency first, then flexible
        sorted_wls = sorted(workloads, key=lambda w: (w.is_flexible, w.max_latency_ms))
        
        for wl in sorted_wls:
            best_dc_id = self.negotiator.negotiate_placement(
                wl, 
                list(self.datacenters.values()), 
                weathers, 
                latency_matrix.get(wl.id, {})
            )
            
            if best_dc_id:
                self.allocator.allocate(wl, self.datacenters[best_dc_id])
                assignments[wl.id] = best_dc_id
                
        return assignments
