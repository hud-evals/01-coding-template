import pytest
from datetime import datetime
from soc_simulator import CorrelationEngine, SecurityEvent

def create_auth_event(ts: str, ip: str, target: str, status: str) -> SecurityEvent:
    return SecurityEvent(
        timestamp=datetime.fromisoformat(ts),
        source_ip=ip, target=target, action="AUTH", status=status, raw_log=""
    )

def normalize_alerts(res):
    if isinstance(res, list):
        return res
    if res is None:
        return []
    return [res]

def test_detect_brute_force():
    engine = CorrelationEngine(time_window_minutes=5)
    
    engine.ingest_event(create_auth_event("2023-01-01T10:00:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:01:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:02:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:03:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:04:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:04:30", "1.1.1.1", "hostA", "SUCCESS"))
    
    res = engine.detect_brute_force()
    alerts = normalize_alerts(res)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "BRUTE_FORCE_SUCCESS"
    assert alerts[0].severity == "CRITICAL"
    assert len(alerts[0].events) == 6

def test_brute_force_out_of_window():
    engine = CorrelationEngine(time_window_minutes=5)
    # Failures spread over 10 minutes shouldn't trigger
    engine.ingest_event(create_auth_event("2023-01-01T10:00:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:02:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:04:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:06:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:08:00", "1.1.1.1", "hostA", "FAILED"))
    engine.ingest_event(create_auth_event("2023-01-01T10:09:00", "1.1.1.1", "hostA", "SUCCESS"))
    
    res = engine.detect_brute_force()
    alerts = normalize_alerts(res)
    assert len(alerts) == 0

def test_lateral_movement():
    engine = CorrelationEngine(time_window_minutes=15)
    engine.ingest_event(SecurityEvent(
        timestamp=datetime.fromisoformat("2023-01-01T12:00:00"),
        source_ip="external_ip", target="web_server", action="AUTH", status="SUCCESS", raw_log=""
    ))
    # Then web_server connects to db_server via SSH 5 mins later
    engine.ingest_event(SecurityEvent(
        timestamp=datetime.fromisoformat("2023-01-01T12:05:00"),
        source_ip="web_server", target="db_server", action="SSH", status="SUCCESS", raw_log=""
    ))
    
    res = engine.detect_lateral_movement()
    alerts = normalize_alerts(res)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "LATERAL_MOVEMENT"
    assert alerts[0].severity == "HIGH"
