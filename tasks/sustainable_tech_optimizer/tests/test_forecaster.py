import pytest
from green_optimizer import EnergyForecaster, WeatherData, Datacenter

def test_forecast_renewable_out():
    forecaster = EnergyForecaster(solar_capacity_mw={"US-EAST": 100.0}, wind_capacity_mw={"US-EAST": 50.0})
    weather = WeatherData("US-EAST", solar_irradiance=0.8, wind_speed=5.0)
    
    # Solar: 100 * 0.8 * 0.2 = 16.0
    # Wind: 50 * (5/10) = 25.0
    # Total: 41.0
    out = forecaster.forecast_renewable_out(weather)
    assert out == pytest.approx(41.0)
    
def test_calculate_effective_intensity():
    forecaster = EnergyForecaster(solar_capacity_mw={"EU-WEST": 200.0}, wind_capacity_mw={"EU-WEST": 0.0})
    weather = WeatherData("EU-WEST", solar_irradiance=1.0, wind_speed=0.0) # 40 MW renew
    dc = Datacenter("dc1", "EU-WEST", 100.0, 50.0, 1.2, 500.0) # total power = 60.0 MW
    
    # ratio: 40 / 60 = 0.6666
    # effective: 500 * (1 - 0.6666) -> approx 166.66
    intensity = forecaster.calculate_effective_intensity(dc, weather)
    assert intensity == pytest.approx(166.66666666)
