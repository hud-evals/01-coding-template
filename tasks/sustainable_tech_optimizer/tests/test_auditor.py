import pytest
from green_optimizer import CarbonAuditor, Datacenter, EnergyForecaster, WeatherData

def test_carbon_auditor_epoch():
    auditor = CarbonAuditor()
    fc = EnergyForecaster({}, {}) # No renewables
    dc1 = Datacenter("d1", "reg", 100.0, 10.0, 1.5, 400.0) # 10MW * 1.5 = 15MW = 15000kW * 400g = 6,000,000g
    
    em = auditor.audit_epoch([dc1], fc, {"reg": WeatherData("reg", 1.0, 10.0)})
    assert em == pytest.approx(6000000.0)
    assert auditor.total_emissions_g == pytest.approx(6000000.0)
