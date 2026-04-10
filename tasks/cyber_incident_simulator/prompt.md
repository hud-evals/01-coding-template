# Task: Cybersecurity Incident Response Simulator

Build the algorithmic backend engine for an Autonomous Security Operations Center (SOC) Simulator.

The simulator must expose a single-file codebase named exactly `soc_simulator.py`. The engine must process raw unstructured SIEM logs, use stateful time-window correlation heuristics to detect APTs (Advanced Persistent Threats), isolate compromised vertices in a network topology abstract graph without compromising critical infrastructure, and generate Markdown incident reports.

## Core Requirements

In `soc_simulator.py`, you must implement:

### 1. `SecurityEvent` and `Alert`
- Define `SecurityEvent` as a standard python dataclass containing: `timestamp` (datetime), `source_ip` (str), `target` (str), `action` (str), `status` (str), and `raw_log` (str).
- Define `Alert` as a dataclass containing: `alert_type` (str), `severity` (str: LOW, MEDIUM, HIGH, CRITICAL), `events` (List[SecurityEvent]), and `trigger_time` (datetime).

### 2. `LogIngester`
A class that parses raw unstructured log arrays.
- Implements `parse_log_stream(log_lines: list[str]) -> list[SecurityEvent]`.
- The log format strictly follows: `[YYYY-MM-DDTHH:MM:SS] [SRC_IP] -> [TARGET] : [ACTION] ([STATUS])`.
- Automatically rejects invalid formatted logs gently.
- Returns a list sorted by `timestamp` chronologically.

### 3. `CorrelationEngine`
A class that detects specific APT attack chains through sliding time windows.
- Intializes with `time_window_minutes` integer. Uses a `timedelta` of that length.
- Maintains state of events ingested via `ingest_event(event: SecurityEvent)`.
- Implements `detect_brute_force()`: Detects 5 or more failed "AUTH" attempts from the exact same source IP, followed by a "SUCCESS" status "AUTH" action to the same or different target, all strictly within the trailing time window limit relative to the exact `SUCCESS` timestamp. Returns an independent `Alert` with `alert_type="BRUTE_FORCE_SUCCESS"` and `severity="CRITICAL"`. The alert events must include the failures and the success event.
- Implements `detect_lateral_movement()`: Target of a successful "AUTH" initiates an "SSH" with "SUCCESS" status to another host strictly within the `time_window_minutes` timeframe relative to the exact `AUTH` timestamp. Returns an `Alert` with `alert_type="LATERAL_MOVEMENT"`, `severity="HIGH"`. Include both events.

### 4. `ContainmentGraph`
A class that utilizes a Directed Graph representation of a network. 
- Implements `add_edge(u, v, bidirectional=True)`.
- Implements `mark_critical(node)` to register a vertex as Critical Infrastructure.
- Implements `get_blast_radius(source_node: str, steps: int = 2) -> set[str]`. This performs a graph traversal returning all unique node names within `steps` distance.
- Implements `calculate_isolation_plan(compromised_node: str) -> list[tuple[str, str]]`. Returns all direct edges attached to the compromised node in order to sever them. **CRITICAL REQUIREMENT:** The engine MUST protect the structural integrity of critical nodes. If isolating the compromised node destroys the ONLY connection path between ANY two critical nodes in the graph (i.e. fragments the graph among the critical set), it must immediately raise a `ValueError` with exactly the substring `"fragments critical node"`.
- Implements `execute_isolation(edges_to_sever: list[tuple[str, str]])` to irrevocably remove the edges from the graph.

### 5. `SOCSimulator`
The master orchestrator class.
- Initializes internal instances of `LogIngester`, `CorrelationEngine` (with 15 min window), and `ContainmentGraph`.
- Implements `generate_report(alerts: list[Alert], isolation_plan: list[tuple[str, str]]) -> str`.
- Generating deterministic reports strictly conforming to:
  - Header: `# Incident Report`
  - Zero threats: If alerts list is empty, return exactly: `# Incident Report\n\nNo threats detected.`
  - Severity line: `**Max Severity:** <SEVERITY>` (Using CRITICAL > HIGH > MEDIUM > LOW weighting to extract max).
  - Details: Print line by line for each severed edge `SEVERED EDGE: u <=> v`.
  - Ensure the raw log actions are mentioned `AUTH [SUCCESS]` format within the report lines.

## Technical Constraints
- The solution MUST be implemented entirely within a single `soc_simulator.py` file.
- Absolutely NO external libraries outside standard `import re`, `datetime`, `dataclasses`, `typing`.
- Do not instantiate logging modules, use pure functional mapping.
