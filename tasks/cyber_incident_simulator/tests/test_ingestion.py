import pytest
from datetime import datetime
from soc_simulator import LogIngester, SecurityEvent

def test_parse_valid_logs():
    ingester = LogIngester()
    logs = [
        "[2023-10-01T12:00:00] [192.168.1.5] -> [10.0.0.1] : [AUTH] ([FAILED])",
        "[2023-10-01T12:01:00] [192.168.1.5] -> [10.0.0.1] : [AUTH] ([SUCCESS])",
        "INVALID FORMAT LOG LINE THAT SHOULD BE SKIPPED",
        "[2023-10-01T12:02:00] [10.0.0.1] -> [10.0.0.2] : [SSH] ([SUCCESS])"
    ]
    
    events = ingester.parse_log_stream(logs)
    
    assert len(events) == 3
    assert events[0].source_ip == "192.168.1.5"
    assert events[0].target == "10.0.0.1"
    assert events[0].action == "AUTH"
    assert events[0].status == "FAILED"
    
    # Check ordering
    assert events[0].timestamp < events[1].timestamp < events[2].timestamp
