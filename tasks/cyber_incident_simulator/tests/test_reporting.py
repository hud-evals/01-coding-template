import pytest
from datetime import datetime
from soc_simulator import SOCSimulator, Alert, SecurityEvent

def test_report_generation():
    sim = SOCSimulator()
    ev = SecurityEvent(
        timestamp=datetime.fromisoformat("2023-10-01T12:00:00"),
        source_ip="1.2.3.4",
        target="web_server",
        action="AUTH",
        status="SUCCESS",
        raw_log=""
    )
    alert = Alert(
        alert_type="BRUTE_FORCE_SUCCESS",
        severity="CRITICAL",
        events=[ev],
        trigger_time=ev.timestamp
    )
    
    report = sim.generate_report([alert], [("web_server", "main_switch")])
    
    assert "# Incident Report" in report
    assert "**Max Severity:** CRITICAL" in report
    assert "SEVERED EDGE: web_server <=> main_switch" in report
    assert "AUTH [SUCCESS]" in report

def test_empty_report():
    sim = SOCSimulator()
    report = sim.generate_report([], [])
    assert "No threats detected." in report
