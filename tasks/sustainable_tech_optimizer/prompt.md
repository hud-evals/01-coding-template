# Task: Sustainable Tech Optimizer Network

Build the algorithmic backend engine for a Sustainable Multi-Agent Data Center Optimizer.

The engine must expose a single-file codebase named exactly `green_optimizer.py`. This system models multiple "agents" acting collaboratively to shift compute workloads across Datacenters minimizing carbon footprint while strictly enforcing latency SLAs.

## Core Requirements

In `green_optimizer.py`, implement the following strictly in standard library python:

### 1. Data Structures
- **Datacenter** (dataclass): `id` (str), `region` (str), `max_compute_capacity` (float in MW), `current_load` (float in MW), `pue` (Power Usage Effectiveness, float), `base_carbon_intensity` (float gCO2eq/kWh). Provide a property `remaining_capacity` restricting load from passing max capacity.
- **Workload** (dataclass): `id` (str), `required_compute` (float MW), `max_latency_ms` (float), `is_flexible` (bool).
- **WeatherData** (dataclass): `region` (str), `solar_irradiance` (float 0.0-1.0), `wind_speed` (float m/s).

### 2. EnergyForecaster
- Initializes with `solar_capacity_mw` (Dict[str, float]) and `wind_capacity_mw` (Dict[str, float]).
- `forecast_renewable_out(weather: WeatherData) -> float`: Calculates generated MW. Solar MW = regional capacity * irradiance * 0.2. Wind MW = regional capacity * min(1.0, wind_speed / 10.0). Return the sum.
- `calculate_effective_intensity(dc: Datacenter, weather: WeatherData) -> float`: Calculates resulting carbon intensity. `total_power_needed` = `dc.current_load * dc.pue`. If `total_power_needed <= 0`, return `base_carbon_intensity`. Else, calculate the reneweable ratio: `min(1.0, ren_mw / total_power_needed)`. Return `base_carbon_intensity * (1.0 - ratio)`.

### 3. ResourceAllocator
- `can_allocate(wl: Workload, dc: Datacenter) -> bool`: Checks if DC has remaining capacity for the workload.
- `allocate(wl, dc) -> bool`: Mutates DC if `can_allocate` is true and returns True, else False.
- `deallocate(wl, dc)`: Subtracts compute from DC `current_load` (clamped to 0).

### 4. CarbonAuditor
- Computes total emissions across all Datacenters. Maintain a state `total_emissions_g`.
- `audit_epoch(datacenters: list[Datacenter], forecaster: EnergyForecaster, weathers: dict[str, WeatherData]) -> float`: Iterates DCs. Computes `power_kw` = `(dc.current_load * pue) * 1000.0`. Calculates region specific effective intensity from forecaster. Epoch emissions = sum(`power_kw * effective_intensity`). Add to `total_emissions_g` and return the epoch value.

### 5. TradeoffNegotiator
- `negotiate_placement(workload, datacenters, weathers, network_latencies_ms: dict[str, float]) -> str | None`: Simulates placing the workload across all DCs. Finds the DC that satisfies `network_latencies_ms[dc.id] <= workload.max_latency_ms` and has sufficient capacity, which produces the absolute MINIMUM `effective_intensity` (simulating `current_load + workload` temporarily). Returns the optimal `dc.id` or None.

### 6. OptimizerNetwork
- Main Orchestrator holding instances of the 4 agents above.
- Initializes with list of Datacenters, solar caps, and wind caps dicts.
- `process_workload_batch(workloads, weathers, latency_matrix) -> dict[str, str]`: Accepts matrix mappings `wl.id -> dc.id -> latency`. Sorts workloads placing the strictest SLAs first (`is_flexible == False` priority, then lower `max_latency_ms`). For each, calls the Negotiator. If optimal DC found, `allocate` via Allocator and record assignment in dict. Returns assignments `wl.id -> dc.id`.

### Technical constraints
- No extra libraries! Use dataclasses and typing.
