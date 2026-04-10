"""
Cybersecurity Incident Response Simulator
Extreme Difficulty HUD Evaluation Task

Implements:
1. Unstructured Log Parsing
2. Stateful Temporal Threat Correlation
3. Graph-Based Network Containment algorithms
4. Deterministic reporting engine
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple

@dataclass
class SecurityEvent:
    timestamp: datetime
    source_ip: str
    target: str
    action: str
    status: str
    raw_log: str

@dataclass
class Alert:
    alert_type: str
    severity: str
    events: List[SecurityEvent]
    trigger_time: datetime

class LogIngester:
    """Parses raw unstructured logs into SecurityEvents."""
    
    # Expected format: [YYYY-MM-DDTHH:MM:SS] [SRC_IP] -> [TARGET] : [ACTION] ([STATUS])
    LOG_PATTERN = re.compile(
        r"\[(.*?)\] \[(.*?)\] -> \[(.*?)\] : \[(.*?)\] \(\[(.*?)\]\)"
    )

    def parse_log_stream(self, log_lines: List[str]) -> List[SecurityEvent]:
        events = []
        for line in log_lines:
            match = self.LOG_PATTERN.search(line)
            if not match:
                continue
            
            try:
                ts_str, src_ip, target, action, status = match.groups()
                ts = datetime.fromisoformat(ts_str)
                events.append(SecurityEvent(
                    timestamp=ts,
                    source_ip=src_ip,
                    target=target,
                    action=action,
                    status=status,
                    raw_log=line.strip()
                ))
            except ValueError:
                # Invalid timestamp format
                continue
        return sorted(events, key=lambda x: x.timestamp)


class CorrelationEngine:
    """Stateful detector of Advanced Persistent Threats (APTs) via temporal correlation."""
    
    def __init__(self, time_window_minutes: int = 5):
        self.time_window = timedelta(minutes=time_window_minutes)
        self.event_stream: List[SecurityEvent] = []

    def ingest_event(self, event: SecurityEvent):
        self.event_stream.append(event)
        self.event_stream.sort(key=lambda e: e.timestamp)

    def detect_brute_force(self) -> List[Alert]:
        """Detects 5+ failed logins from same IP followed by a successful login within window."""
        alerts = []
        
        # Group by source IP
        events_by_ip: Dict[str, List[SecurityEvent]] = {}
        for event in self.event_stream:
            if event.action == "AUTH":
                events_by_ip.setdefault(event.source_ip, []).append(event)
                
        for ip, auth_events in events_by_ip.items():
            for i in range(len(auth_events)):
                current_event = auth_events[i]
                if current_event.status == "SUCCESS":
                    # Look back for failures within the window
                    window_start = current_event.timestamp - self.time_window
                    failures = [
                        e for e in auth_events[:i]
                        if e.status == "FAILED" and window_start <= e.timestamp < current_event.timestamp
                    ]
                    if len(failures) >= 5:
                        alerts.append(Alert(
                            alert_type="BRUTE_FORCE_SUCCESS",
                            severity="CRITICAL",
                            events=failures + [current_event],
                            trigger_time=current_event.timestamp
                        ))
                    
        return alerts

    def detect_lateral_movement(self) -> List[Alert]:
        """
        Detects lateral movement:
        Target of a successful auth initiates an SSH connection to another host within the time window.
        """
        alerts = []
        for i, first_event in enumerate(self.event_stream):
            if first_event.action == "AUTH" and first_event.status == "SUCCESS":
                compromised_host = first_event.target
                window_end = first_event.timestamp + self.time_window
                
                # Check subsequent events
                for second_event in self.event_stream[i+1:]:
                    if second_event.timestamp > window_end:
                        break # Out of window
                    
                    if second_event.source_ip == compromised_host and second_event.action == "SSH" and second_event.status == "SUCCESS":
                        alerts.append(Alert(
                            alert_type="LATERAL_MOVEMENT",
                            severity="HIGH",
                            events=[first_event, second_event],
                            trigger_time=second_event.timestamp
                        ))
        return alerts


class ContainmentGraph:
    """
    Network topology director capable of calculating minimum edge cuts 
    to isolate compromised nodes without disconnecting critical infrastructure.
    """
    def __init__(self):
        self.edges: Dict[str, Set[str]] = {}
        self.critical_nodes: Set[str] = set()

    def add_edge(self, u: str, v: str, bidirectional: bool = True):
        self.edges.setdefault(u, set()).add(v)
        if bidirectional:
            self.edges.setdefault(v, set()).add(u)

    def mark_critical(self, node: str):
        self.critical_nodes.add(node)

    def get_blast_radius(self, source_node: str, steps: int = 2) -> Set[str]:
        """Returns all nodes within N steps of source."""
        if source_node not in self.edges:
            return set()
            
        visited = {source_node}
        queue = [(source_node, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            if depth >= steps:
                continue
                
            for neighbor in self.edges.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
                    
        return visited

    def calculate_isolation_plan(self, compromised_node: str) -> List[Tuple[str, str]]:
        """
        Calculates the edges to remove to completely isolate the compromised node.
        Raises an exception if isolation breaks connectivity between any two critical nodes 
        (if they were connected before). 
        For simplicity in this simulation, we strictly sever direct edges to the compromised node,
        but only if dropping those edges doesn't fragment the remaining critical infrastructure.
        """
        if compromised_node not in self.edges:
            return []

        # Find direct edges to sever
        edges_to_sever = []
        for neighbor in list(self.edges[compromised_node]):
            edges_to_sever.append((compromised_node, neighbor))
            
        # Verify critical cluster connectivity
        if len(self.critical_nodes) > 1:
            # Create a clone of graph without the compromised edges
            safe_graph = {k: set(v) for k, v in self.edges.items()}
            for u, v in edges_to_sever:
                if u in safe_graph and v in safe_graph[u]:
                    safe_graph[u].remove(v)
                if v in safe_graph and u in safe_graph[v]:
                    safe_graph[v].remove(u)
                    
            # Check components
            crit_list = list(self.critical_nodes)
            start = crit_list[0]
            
            # BFS from one critical node
            visited = {start}
            queue = [start]
            while queue:
                current = queue.pop(0)
                for neighbor in safe_graph.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        
            # If any critical node is missing from visited, it's fragmented
            for crit in crit_list:
                if crit not in visited and crit != compromised_node:
                    raise ValueError(f"Isolation of {compromised_node} fragments critical node {crit}")

        return edges_to_sever

    def execute_isolation(self, edges_to_sever: List[Tuple[str, str]]):
        for u, v in edges_to_sever:
            if u in self.edges and v in self.edges[u]:
                self.edges[u].remove(v)
            if v in self.edges and u in self.edges[v]:
                self.edges[v].remove(u)


class SOCSimulator:
    """Orchestrator for the entire pipeline."""
    
    def __init__(self):
        self.ingester = LogIngester()
        self.correlation = CorrelationEngine(time_window_minutes=15)
        self.network = ContainmentGraph()
        
    def generate_report(self, alerts: List[Alert], isolation_plan: List[Tuple[str, str]]) -> str:
        """Deterministically generates a Markdown report of incidents."""
        if not alerts:
            return "# Incident Report\n\nNo threats detected."
            
        lines = ["# Incident Report"]
        
        # Determine highest severity
        severity_rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
        highest_severity = max(alerts, key=lambda a: severity_rank.get(a.severity, 0)).severity
        lines.append(f"\n**Max Severity:** {highest_severity}")
        
        lines.append("\n## Detected Alerts")
        for i, alert in enumerate(sorted(alerts, key=lambda a: a.trigger_time)):
            lines.append(f"\n### Exception {i+1}: {alert.alert_type} ({alert.severity})")
            lines.append(f"Triggered at: {alert.trigger_time.isoformat()}")
            lines.append("Evidence Window:")
            for ev in alert.events:
                lines.append(f" - {ev.timestamp.isoformat()} | {ev.source_ip} -> {ev.target} | {action_fmt(ev)}")
                
        lines.append("\n## Containment Actions")
        if isolation_plan:
            for u, v in sorted(isolation_plan):
                lines.append(f" - SEVERED EDGE: {u} <=> {v}")
        else:
            lines.append("No network isolation required.")
            
        return "\n".join(lines)
        
def action_fmt(ev: SecurityEvent) -> str:
    return f"{ev.action} [{ev.status}]"
