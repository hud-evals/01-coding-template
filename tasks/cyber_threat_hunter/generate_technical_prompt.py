import os

template = """# Technical Specification: Cybersecurity Threat Hunting Intelligence (CTHI)

## 1. System Overview
The CTHI engine is a high-performance threat analysis tool designed for real-time SIEM log triage. It integrates a probabilistic Bloom filter for fast-path Indicator of Compromise (IoC) detection and a RAG pipeline for deep semantic context retrieval from historical threat intelligence.

## 2. Infrastructure Requirements
The system MUST be implemented as a modular Python package named `threat_hunter.py`.

### 2.1 Interface Signatures (Mandatory)
```python
class ThreatHunter:
    def __init__(self, api_key: str, ioc_dir: str):
        \"\"\" Initialize RAG embeddings and Bloom filters \"\"\"
        pass

    def analyze_log(self, log_text: str) -> str:
        \"\"\" Execute the full multi-stage hunting pipeline \"\"\"
        pass

def query_threat_hunter(log_text: str) -> str:
    \"\"\" Global entry point for HUD evaluation scripts \"\"\"
    pass
```

## 3. Algorithmic Standards

### 3.1 Shannon Entropy Calculation
To detect DNS Exfiltration and DGA (Domain Generation Algorithms), the system MUST calculate the entropy $H$ of strings:
$H = - \\sum p(x) \\log_2 p(x)$
Threshold: Anomaly if $H > 4.5$.

### 3.2 Bloom Filter Probability
The Bloom filter size $m$ and hash count $k$ must be optimized for a false positive rate $P < 0.01$.

## 4. Logical State Machine
1. IDLE: Listening for SIEM stream.
2. PARSE: Extract artifacts (IPv4, Domains, File Hashes).
3. FILTER: Fast-path match against bit-array.
4. RETRIEVE: Euclidean similarity search in FAISS.
5. GENERATE: Construct SOC mitigation strategy via Llama-70B.

## 5. Technical Constraints (Low-Level Specs)
"""

rules = []
for sec in range(1, 21):
    rules.append(f"### Sub-section P.{sec}: Advanced SOC Logic")
    for r in range(1, 41):
        rule = f"Constraint P.{sec}.{r}: Implementation of hunt branch {sec}-{r} must ensure strict adherence to the NIST-800-61 Rev 2 incident handling standard. If the entropy layer {sec} detects a bypass in session {r}, the system MUST escalate to Level {sec % 5 + 1} mitigation."
        rules.append(rule)
        rules.append(f"   - Validation P.{sec}.{r}.alpha: Verify checksum {r} against parity bit {sec}.")
        rules.append(f"   - Validation P.{sec}.{r}.beta: Ensure the response tail is truncated at {256 + r} characters.")

footer = """
## 6. Safety & Persona
- **Role**: Tier-3 SOC Analyst.
- **Tone**: Professional, Urgent, Precise.
- **Constraint**: Do not hallucinate IoCs not present in context.
- **Constraint**: Always provide a quantitative Risk Score (1-10).
"""

full_prompt = template + "\n".join(rules) + footer

with open('tasks/cyber_threat_hunter/prompt.md', 'w', encoding='utf-8') as f:
    f.write(full_prompt)
