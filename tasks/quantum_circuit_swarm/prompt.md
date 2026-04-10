# QuantumSwarm: Multi-Agent Quantum Circuit Designer

## Overview
- Project name: QuantumSwarm Circuit Designer

## Natural Language Instructions

Before you start:
- Create and edit the solution directly in `/home/ubuntu/workspace/quantum_swarm.py`.
- **CRITICAL**: Use ONLY the Python 3.10 standard library. No third-party packages allowed (no qiskit, cirq, numpy, etc.).
- You are building a production-grade, multi-agent swarm system for quantum circuit design, optimization, and error correction. This is a high-level distributed AI systems task.

### Architectural Requirements

#### 1. Quantum Circuit Representation (Pure Python Matrix Engine)
Implement a complete quantum computing simulation kernel from scratch.
- **Complex Number Engine**: Implement a `Complex` class with `__add__`, `__mul__`, `__sub__`, `__truediv__`, `__abs__`, `conjugate()`. All quantum math depends on this.
- **Matrix Engine**: Implement a `Matrix` class supporting:
  - `__matmul__` (matrix multiply)
  - `tensor_product(other)` (Kronecker product — critical for multi-qubit gates)
  - `adjoint()` (conjugate transpose)
  - `trace()` (sum of diagonal)
  - Static factory: `Matrix.identity(n)`, `Matrix.zeros(r, c)`
- **Gate Library**: Implement as `Matrix` objects:
  - Single-qubit: `H` (Hadamard), `X` (PauliX), `Y` (PauliY), `Z` (PauliZ), `T` (π/8), `S` (Phase), `Rx(θ)`, `Ry(θ)`, `Rz(θ)`
  - Multi-qubit: `CNOT`, `CZ`, `SWAP`, `Toffoli` (CCNOT)
  - Gate math must use `math.sqrt`, `math.cos`, `math.sin`, `math.pi`, `math.e` for exact values.
- **Circuit Class**: `QuantumCircuit(num_qubits)`
  - `.add_gate(gate_name, target_qubits, params=None)` — appends to an internal gate list
  - `.to_unitary()` — computes the full 2^n × 2^n unitary by composing gate matrices via tensor products
  - `.simulate(initial_state=None)` — returns the final statevector as a list of `Complex`
  - `.depth()` — returns circuit depth (layers of parallelizable gates)
  - `.gate_count()` — total number of gates
  - `.to_dag()` — returns a DAG (dict of node_id → {gate, qubits, deps}) for optimization passes

#### 2. Multi-Agent Swarm Architecture
Implement a cooperative multi-agent system where specialized agents collaborate:

- **`PlannerAgent`**: Takes a high-level goal string (e.g., "Create a 3-qubit GHZ state") and decomposes it into an ordered list of subtasks. Each subtask is a dict: `{"task": str, "agent": str, "priority": int}`.
- **`CircuitArchitectAgent`**: Receives subtask instructions and builds a `QuantumCircuit`. Must implement:
  - Template library: GHZ state, Bell pair, Quantum Fourier Transform (QFT), phase estimation skeleton.
  - Parametric circuit generation from textual descriptions.
- **`ErrorMitigatorAgent`**: Analyzes a `QuantumCircuit` and applies error mitigation:
  - Depolarizing noise model: applies a noise channel `ρ' = (1-p)ρ + p/3 (XρX + YρY + ZρZ)` to each gate.
  - Zero-Noise Extrapolation (ZNE): runs the circuit at noise scales [1x, 2x, 3x] and extrapolates to 0-noise using Richardson extrapolation (polynomial fit with Vandermonde matrix).
  - Returns a `NoiseReport` with fidelity estimates per gate layer.
- **`ValidatorAgent`**: Validates circuits against known properties:
  - Unitarity check: `U† U ≈ I` within tolerance `1e-9`.
  - Entanglement witness: computes partial trace and checks von Neumann entropy `S = -Tr(ρ log₂ ρ)` (eigenvalues via power iteration).
  - Gate decomposition verification: confirms Toffoli decomposes into ≤ 6 CNOT + single-qubit gates.
  - Returns `ValidationReport` with pass/fail per check and numerical results.
- **`EvolverAgent`**: Implements a genetic algorithm over circuit populations:
  - Chromosome: a `QuantumCircuit` instance.
  - Fitness: `fidelity * (1 / depth) * (1 / gate_count)` — balances accuracy vs. efficiency.
  - Crossover: swap gate subsequences between two parent circuits at a random cut point.
  - Mutation: randomly replace a gate with a different gate on the same qubits.
  - Selection: tournament selection with pool size 3.
  - Runs for configurable number of generations (default 10).

#### 3. Swarm Orchestrator & Message Bus
- **`SwarmOrchestrator`**: Central coordinator that:
  - Accepts a high-level goal string.
  - Routes tasks through agents in the correct pipeline: Planner → Architect → ErrorMitigator → Validator → Evolver.
  - Maintains a `MessageBus` (in-memory pub/sub) where agents post results.
  - Implements a **debate protocol**: if `ValidatorAgent` fails a circuit, it sends feedback to `CircuitArchitectAgent` for up to 3 revision rounds.
  - Returns a `SwarmResult` containing: final optimized circuit, noise report, validation report, evolution history.
- **`MessageBus`**: Thread-safe pub/sub system using `threading.Lock`:
  - `.publish(topic: str, message: dict)`
  - `.subscribe(topic: str, callback: Callable)`
  - `.get_history(topic: str) -> List[dict]`

#### 4. Binary Circuit Serialization (QCF Format)
Implement a compact binary format for circuit persistence:
- **Header (20 bytes)**: `MAGIC` (4B: `0x51434631` = "QCF1"), `Version` (4B: `1`), `NumQubits` (4B), `GateCount` (4B), `MetadataOffset` (4B).
- **Gate Section**: For each gate: `GateType` (1B enum), `NumTargets` (1B), `TargetQubits` (1B each), `NumParams` (1B), `Params` (8B double each).
- **Metadata Section**: JSON-encoded metadata as UTF-8 bytes, length-prefixed (4B).
- Implement `serialize_circuit(circuit) -> bytes` and `deserialize_circuit(data) -> QuantumCircuit`.

### API Specification

```python
class QuantumCircuit:
    def __init__(self, num_qubits: int)
    def add_gate(self, gate_name: str, target_qubits: list, params: dict = None)
    def to_unitary(self) -> Matrix
    def simulate(self, initial_state=None) -> list
    def depth(self) -> int
    def gate_count(self) -> int
    def to_dag(self) -> dict

class SwarmOrchestrator:
    def __init__(self, llm_fn: Callable[[str], str] = None)
    def run(self, goal: str) -> SwarmResult
    def get_message_history(self) -> list

class SwarmResult:
    circuit: QuantumCircuit
    noise_report: dict
    validation_report: dict
    evolution_history: list
    debate_log: list

def serialize_circuit(circuit: QuantumCircuit) -> bytes
def deserialize_circuit(data: bytes) -> QuantumCircuit
```

### Algorithmic Implementation Guide
To prevent complexity failures, you MUST use the following exact math implementations:
1. **Matrix Tensor Product (Kronecker):** Given `A` (r1 x c1) and `B` (r2 x c2), the resulting matrix `C` is (r1*r2) x (c1*c2). For each cell: `C[i * r2 + k][j * c2 + l] = A.data[i][j] * B.data[k][l]`.
2. **Circuit Depth:** Use simple array-tracking. Initialize an array `qubit_layer = [0] * num_qubits`. For each gate, compute `gate_layer = 1 + max(qubit_layer[q] for q in gate_targets)`. Then assign `qubit_layer[q] = gate_layer` for all targets. The `depth` is `max(qubit_layer)`.
3. **Evolver Fitness:** Calculate fitness securely via `fitness = fidelity / ((depth + 1) * (gate_count + 1))` to avoid zero-division exceptions.

### Locally Grading Test Requirement
You MUST implement a `test_quantum_swarm.py` suite (save to `/home/ubuntu/workspace/`) that verifies:
1. Complex number arithmetic accuracy.
2. Matrix tensor product correctness (2×2 ⊗ 2×2 = 4×4).
3. Hadamard gate produces equal superposition from |0⟩.
4. CNOT gate creates Bell state from H|0⟩⊗|0⟩.
5. Circuit unitary is actually unitary (U†U = I).
6. Binary serialization round-trip preserves circuit structure.
7. Swarm orchestrator produces a valid GHZ circuit.
8. Genetic algorithm improves fitness across generations.
