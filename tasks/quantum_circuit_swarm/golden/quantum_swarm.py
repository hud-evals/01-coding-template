"""
QuantumSwarm: Multi-Agent Quantum Circuit Designer — Golden Solution
Pure Python 3.10 stdlib only.
"""
import math
import struct
import json
import threading
import random
import copy
from typing import List, Dict, Optional, Callable, Any


# ============================================================================
# 1. COMPLEX NUMBER ENGINE
# ============================================================================
class Complex:
    __slots__ = ("re", "im")

    def __init__(self, re: float = 0.0, im: float = 0.0):
        self.re = float(re)
        self.im = float(im)

    def __add__(self, o):
        if isinstance(o, (int, float)):
            return Complex(self.re + o, self.im)
        return Complex(self.re + o.re, self.im + o.im)

    def __radd__(self, o):
        return self.__add__(o)

    def __sub__(self, o):
        if isinstance(o, (int, float)):
            return Complex(self.re - o, self.im)
        return Complex(self.re - o.re, self.im - o.im)

    def __mul__(self, o):
        if isinstance(o, (int, float)):
            return Complex(self.re * o, self.im * o)
        return Complex(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )

    def __rmul__(self, o):
        return self.__mul__(o)

    def __truediv__(self, o):
        if isinstance(o, (int, float)):
            return Complex(self.re / o, self.im / o)
        d = o.re * o.re + o.im * o.im
        return Complex(
            (self.re * o.re + self.im * o.im) / d,
            (self.im * o.re - self.re * o.im) / d,
        )

    def __abs__(self):
        return math.sqrt(self.re * self.re + self.im * self.im)

    def conjugate(self):
        return Complex(self.re, -self.im)

    def __repr__(self):
        return f"Complex({self.re}, {self.im})"

    def __neg__(self):
        return Complex(-self.re, -self.im)


ZERO = Complex(0, 0)
ONE = Complex(1, 0)
IM = Complex(0, 1)


# ============================================================================
# 2. MATRIX ENGINE
# ============================================================================
class Matrix:
    def __init__(self, data: List[List[Complex]]):
        self.data = data
        self.rows = len(data)
        self.cols = len(data[0]) if data else 0

    @staticmethod
    def identity(n: int) -> "Matrix":
        d = [[Complex(1, 0) if i == j else Complex(0, 0) for j in range(n)] for i in range(n)]
        return Matrix(d)

    @staticmethod
    def zeros(r: int, c: int) -> "Matrix":
        return Matrix([[Complex(0, 0) for _ in range(c)] for _ in range(r)])

    def __matmul__(self, o: "Matrix") -> "Matrix":
        assert self.cols == o.rows
        res = Matrix.zeros(self.rows, o.cols)
        for i in range(self.rows):
            for j in range(o.cols):
                s = Complex(0, 0)
                for k in range(self.cols):
                    s = s + self.data[i][k] * o.data[k][j]
                res.data[i][j] = s
        return res

    def tensor_product(self, o: "Matrix") -> "Matrix":
        nr, nc = self.rows * o.rows, self.cols * o.cols
        res = Matrix.zeros(nr, nc)
        for i in range(self.rows):
            for j in range(self.cols):
                for k in range(o.rows):
                    for l in range(o.cols):
                        res.data[i * o.rows + k][j * o.cols + l] = self.data[i][j] * o.data[k][l]
        return res

    def adjoint(self) -> "Matrix":
        res = Matrix.zeros(self.cols, self.rows)
        for i in range(self.rows):
            for j in range(self.cols):
                res.data[j][i] = self.data[i][j].conjugate()
        return res

    def trace(self) -> Complex:
        s = Complex(0, 0)
        for i in range(min(self.rows, self.cols)):
            s = s + self.data[i][i]
        return s

    def __mul__(self, scalar):
        if isinstance(scalar, (int, float)):
            scalar = Complex(scalar, 0)
        return Matrix([[self.data[i][j] * scalar for j in range(self.cols)] for i in range(self.rows)])

    def __add__(self, o: "Matrix") -> "Matrix":
        return Matrix([[self.data[i][j] + o.data[i][j] for j in range(self.cols)] for i in range(self.rows)])


# ============================================================================
# 3. GATE LIBRARY
# ============================================================================
_inv_sqrt2 = 1.0 / math.sqrt(2)

GATE_MATRICES = {}

def _build_gates():
    global GATE_MATRICES
    s2 = Complex(_inv_sqrt2, 0)
    GATE_MATRICES["H"] = Matrix([
        [s2, s2],
        [s2, Complex(-_inv_sqrt2, 0)],
    ])
    GATE_MATRICES["X"] = Matrix([
        [ZERO, ONE], [ONE, ZERO],
    ])
    GATE_MATRICES["Y"] = Matrix([
        [ZERO, Complex(0, -1)], [Complex(0, 1), ZERO],
    ])
    GATE_MATRICES["Z"] = Matrix([
        [ONE, ZERO], [ZERO, Complex(-1, 0)],
    ])
    GATE_MATRICES["S"] = Matrix([
        [ONE, ZERO], [ZERO, IM],
    ])
    GATE_MATRICES["T"] = Matrix([
        [ONE, ZERO],
        [ZERO, Complex(math.cos(math.pi / 4), math.sin(math.pi / 4))],
    ])
    GATE_MATRICES["CNOT"] = Matrix([
        [ONE, ZERO, ZERO, ZERO],
        [ZERO, ONE, ZERO, ZERO],
        [ZERO, ZERO, ZERO, ONE],
        [ZERO, ZERO, ONE, ZERO],
    ])
    GATE_MATRICES["CZ"] = Matrix([
        [ONE, ZERO, ZERO, ZERO],
        [ZERO, ONE, ZERO, ZERO],
        [ZERO, ZERO, ONE, ZERO],
        [ZERO, ZERO, ZERO, Complex(-1, 0)],
    ])
    GATE_MATRICES["SWAP"] = Matrix([
        [ONE, ZERO, ZERO, ZERO],
        [ZERO, ZERO, ONE, ZERO],
        [ZERO, ONE, ZERO, ZERO],
        [ZERO, ZERO, ZERO, ONE],
    ])
    GATE_MATRICES["TOFFOLI"] = Matrix.identity(8)
    GATE_MATRICES["TOFFOLI"].data[6][6] = ZERO
    GATE_MATRICES["TOFFOLI"].data[6][7] = ONE
    GATE_MATRICES["TOFFOLI"].data[7][7] = ZERO
    GATE_MATRICES["TOFFOLI"].data[7][6] = ONE


_build_gates()


def _rotation_gate(axis: str, theta: float) -> Matrix:
    c = Complex(math.cos(theta / 2), 0)
    s = Complex(math.sin(theta / 2), 0)
    if axis == "x":
        return Matrix([
            [c, Complex(0, -math.sin(theta / 2))],
            [Complex(0, -math.sin(theta / 2)), c],
        ])
    elif axis == "y":
        return Matrix([
            [c, Complex(-math.sin(theta / 2), 0)],
            [Complex(math.sin(theta / 2), 0), c],
        ])
    else:  # z
        return Matrix([
            [Complex(math.cos(theta / 2), -math.sin(theta / 2)), ZERO],
            [ZERO, Complex(math.cos(theta / 2), math.sin(theta / 2))],
        ])


def get_gate_matrix(name: str, params: dict = None) -> Matrix:
    up = name.upper()
    if up in GATE_MATRICES:
        return GATE_MATRICES[up]
    if up in ("RX", "RY", "RZ"):
        theta = params.get("theta", 0) if params else 0
        return _rotation_gate(up[-1].lower(), theta)
    raise ValueError(f"Unknown gate: {name}")


# ============================================================================
# 4. QUANTUM CIRCUIT
# ============================================================================
class QuantumCircuit:
    def __init__(self, num_qubits: int):
        self.num_qubits = num_qubits
        self.gates: List[Dict] = []

    def add_gate(self, gate_name: str, target_qubits: list, params: dict = None):
        self.gates.append({
            "name": gate_name,
            "qubits": list(target_qubits),
            "params": params or {},
        })

    def gate_count(self) -> int:
        return len(self.gates)

    def depth(self) -> int:
        if not self.gates:
            return 0
        qubit_layers = [0] * self.num_qubits
        for g in self.gates:
            max_layer = max(qubit_layers[q] for q in g["qubits"])
            for q in g["qubits"]:
                qubit_layers[q] = max_layer + 1
        return max(qubit_layers)

    def to_dag(self) -> dict:
        dag = {}
        qubit_last = {}  # qubit -> last node_id that touched it
        for idx, g in enumerate(self.gates):
            deps = set()
            for q in g["qubits"]:
                if q in qubit_last:
                    deps.add(qubit_last[q])
            dag[idx] = {"gate": g["name"], "qubits": g["qubits"], "deps": list(deps)}
            for q in g["qubits"]:
                qubit_last[q] = idx
        return dag

    def _full_gate_matrix(self, gate_mat: Matrix, target_qubits: list) -> Matrix:
        n = self.num_qubits
        num_gate_qubits = len(target_qubits)

        if num_gate_qubits == 1:
            q = target_qubits[0]
            result = Matrix.identity(1)
            for i in range(n):
                if i == q:
                    result = result.tensor_product(gate_mat)
                else:
                    result = result.tensor_product(Matrix.identity(2))
            return result

        if num_gate_qubits == 2:
            q0, q1 = target_qubits
            dim = 2 ** n
            full = Matrix.identity(dim)
            for i in range(dim):
                for j in range(dim):
                    full.data[i][j] = Complex(0, 0)

            for i in range(dim):
                bits_i = [(i >> (n - 1 - k)) & 1 for k in range(n)]
                for j in range(dim):
                    bits_j = [(j >> (n - 1 - k)) & 1 for k in range(n)]
                    other_match = all(bits_i[k] == bits_j[k] for k in range(n) if k != q0 and k != q1)
                    if not other_match:
                        continue
                    gi = bits_i[q0] * 2 + bits_i[q1]
                    gj = bits_j[q0] * 2 + bits_j[q1]
                    full.data[i][j] = gate_mat.data[gi][gj]
            return full

        if num_gate_qubits == 3:
            q0, q1, q2 = target_qubits
            dim = 2 ** n
            full = Matrix.zeros(dim, dim)
            for i in range(dim):
                bits_i = [(i >> (n - 1 - k)) & 1 for k in range(n)]
                for j in range(dim):
                    bits_j = [(j >> (n - 1 - k)) & 1 for k in range(n)]
                    other_match = all(bits_i[k] == bits_j[k] for k in range(n) if k not in target_qubits)
                    if not other_match:
                        continue
                    gi = bits_i[q0] * 4 + bits_i[q1] * 2 + bits_i[q2]
                    gj = bits_j[q0] * 4 + bits_j[q1] * 2 + bits_j[q2]
                    full.data[i][j] = gate_mat.data[gi][gj]
            return full

        raise NotImplementedError(f"Gates on {num_gate_qubits} qubits not supported")

    def to_unitary(self) -> Matrix:
        dim = 2 ** self.num_qubits
        U = Matrix.identity(dim)
        for g in self.gates:
            gm = get_gate_matrix(g["name"], g["params"])
            fm = self._full_gate_matrix(gm, g["qubits"])
            U = fm @ U
        return U

    def simulate(self, initial_state=None) -> list:
        dim = 2 ** self.num_qubits
        if initial_state is None:
            sv = [Complex(0, 0)] * dim
            sv[0] = Complex(1, 0)
        else:
            sv = list(initial_state)
        U = self.to_unitary()
        result = [Complex(0, 0)] * dim
        for i in range(dim):
            s = Complex(0, 0)
            for j in range(dim):
                s = s + U.data[i][j] * sv[j]
            result[i] = s
        return result


# ============================================================================
# 5. BINARY SERIALIZATION (QCF FORMAT)
# ============================================================================
GATE_TYPE_MAP = {
    "H": 1, "X": 2, "Y": 3, "Z": 4, "S": 5, "T": 6,
    "RX": 7, "RY": 8, "RZ": 9,
    "CNOT": 10, "CZ": 11, "SWAP": 12, "TOFFOLI": 13,
}
GATE_TYPE_REV = {v: k for k, v in GATE_TYPE_MAP.items()}

QCF_MAGIC = 0x51434631  # "QCF1"


def serialize_circuit(circuit: QuantumCircuit) -> bytes:
    buf = bytearray()
    # Header placeholder (20 bytes)
    buf.extend(struct.pack(">5I", QCF_MAGIC, 1, circuit.num_qubits, circuit.gate_count(), 0))
    # Gate section
    for g in circuit.gates:
        gtype = GATE_TYPE_MAP.get(g["name"].upper(), 0)
        qubits = g["qubits"]
        params = g.get("params", {})
        param_vals = [v for v in params.values() if isinstance(v, (int, float))]
        buf.append(gtype)
        buf.append(len(qubits))
        for q in qubits:
            buf.append(q)
        buf.append(len(param_vals))
        for p in param_vals:
            buf.extend(struct.pack(">d", float(p)))
    # Metadata section
    meta_off = len(buf)
    meta = json.dumps({"num_qubits": circuit.num_qubits, "gate_count": circuit.gate_count()}).encode("utf-8")
    buf.extend(struct.pack(">I", len(meta)))
    buf.extend(meta)
    # Patch metadata offset in header
    struct.pack_into(">I", buf, 16, meta_off)
    return bytes(buf)


def deserialize_circuit(data: bytes) -> QuantumCircuit:
    magic, ver, nq, gc, meta_off = struct.unpack_from(">5I", data, 0)
    assert magic == QCF_MAGIC, f"Bad magic: {hex(magic)}"
    qc = QuantumCircuit(nq)
    pos = 20
    for _ in range(gc):
        gtype = data[pos]; pos += 1
        ntargets = data[pos]; pos += 1
        qubits = []
        for _ in range(ntargets):
            qubits.append(data[pos]); pos += 1
        nparams = data[pos]; pos += 1
        params = {}
        for pi in range(nparams):
            val = struct.unpack_from(">d", data, pos)[0]; pos += 8
            params["theta"] = val
        gate_name = GATE_TYPE_REV.get(gtype, "X")
        qc.add_gate(gate_name, qubits, params if params else None)
    return qc


# ============================================================================
# 6. MESSAGE BUS
# ============================================================================
class MessageBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._topics: Dict[str, List[dict]] = {}
        self._subs: Dict[str, List[Callable]] = {}

    def publish(self, topic: str, message: dict):
        with self._lock:
            self._topics.setdefault(topic, []).append(message)
            for cb in self._subs.get(topic, []):
                try:
                    cb(message)
                except Exception:
                    pass

    def subscribe(self, topic: str, callback: Callable):
        with self._lock:
            self._subs.setdefault(topic, []).append(callback)

    def get_history(self, topic: str) -> List[dict]:
        with self._lock:
            return list(self._topics.get(topic, []))


# ============================================================================
# 7. AGENTS
# ============================================================================
class PlannerAgent:
    def plan(self, goal: str) -> List[Dict]:
        goal_lower = goal.lower()
        tasks = []
        if "ghz" in goal_lower:
            # Extract qubit count
            n = 3
            for word in goal.split():
                if word.isdigit():
                    n = int(word)
                    break
            tasks = [
                {"task": f"Build {n}-qubit GHZ state circuit", "agent": "architect", "priority": 1},
                {"task": "Analyze noise on GHZ circuit", "agent": "mitigator", "priority": 2},
                {"task": "Validate GHZ entanglement properties", "agent": "validator", "priority": 3},
                {"task": "Optimize GHZ circuit via evolution", "agent": "evolver", "priority": 4},
            ]
        elif "bell" in goal_lower:
            tasks = [
                {"task": "Build Bell pair circuit", "agent": "architect", "priority": 1},
                {"task": "Validate Bell state", "agent": "validator", "priority": 2},
            ]
        elif "qft" in goal_lower or "fourier" in goal_lower:
            n = 3
            for word in goal.split():
                if word.isdigit():
                    n = int(word)
                    break
            tasks = [
                {"task": f"Build {n}-qubit QFT circuit", "agent": "architect", "priority": 1},
                {"task": "Analyze noise model", "agent": "mitigator", "priority": 2},
                {"task": "Validate unitarity", "agent": "validator", "priority": 3},
                {"task": "Evolve for depth reduction", "agent": "evolver", "priority": 4},
            ]
        else:
            tasks = [
                {"task": goal, "agent": "architect", "priority": 1},
                {"task": "Validate result", "agent": "validator", "priority": 2},
            ]
        return sorted(tasks, key=lambda t: t["priority"])


class CircuitArchitectAgent:
    def build(self, task_desc: str) -> QuantumCircuit:
        desc = task_desc.lower()
        if "ghz" in desc:
            n = 3
            for word in task_desc.split():
                if word.isdigit():
                    n = int(word)
                    break
            return self._ghz(n)
        elif "bell" in desc:
            return self._bell()
        elif "qft" in desc:
            n = 3
            for word in task_desc.split():
                if word.isdigit():
                    n = int(word)
                    break
            return self._qft(n)
        else:
            qc = QuantumCircuit(2)
            qc.add_gate("H", [0])
            qc.add_gate("CNOT", [0, 1])
            return qc

    def _ghz(self, n: int) -> QuantumCircuit:
        qc = QuantumCircuit(n)
        qc.add_gate("H", [0])
        for i in range(n - 1):
            qc.add_gate("CNOT", [i, i + 1])
        return qc

    def _bell(self) -> QuantumCircuit:
        qc = QuantumCircuit(2)
        qc.add_gate("H", [0])
        qc.add_gate("CNOT", [0, 1])
        return qc

    def _qft(self, n: int) -> QuantumCircuit:
        qc = QuantumCircuit(n)
        for i in range(n):
            qc.add_gate("H", [i])
            for j in range(i + 1, n):
                angle = math.pi / (2 ** (j - i))
                qc.add_gate("Rz", [j], {"theta": angle})
                qc.add_gate("CNOT", [i, j])
        return qc

    def revise(self, circuit: QuantumCircuit, feedback: str) -> QuantumCircuit:
        """Revise a circuit based on validator feedback."""
        return circuit  # In golden, the initial build is already correct


class ErrorMitigatorAgent:
    def analyze(self, circuit: QuantumCircuit, noise_prob: float = 0.01) -> dict:
        report = {
            "noise_probability": noise_prob,
            "gate_count": circuit.gate_count(),
            "estimated_fidelity": (1 - noise_prob) ** circuit.gate_count(),
            "zne_extrapolation": {},
            "per_layer_fidelity": [],
        }
        # ZNE: run at scales 1x, 2x, 3x
        for scale in [1, 2, 3]:
            effective_p = noise_prob * scale
            fid = max(0, (1 - effective_p) ** circuit.gate_count())
            report["zne_extrapolation"][f"{scale}x"] = fid

        # Simple Richardson extrapolation to 0-noise
        f1 = report["zne_extrapolation"]["1x"]
        f2 = report["zne_extrapolation"]["2x"]
        report["zne_extrapolation"]["0x_estimate"] = 2 * f1 - f2

        # Per-layer fidelity
        depth = circuit.depth()
        for layer in range(depth):
            report["per_layer_fidelity"].append((1 - noise_prob))

        return report


class ValidatorAgent:
    def validate(self, circuit: QuantumCircuit) -> dict:
        report = {"checks": {}, "passed": True}

        # 1. Unitarity check: U† U ≈ I
        U = circuit.to_unitary()
        Udag = U.adjoint()
        product = Udag @ U
        dim = 2 ** circuit.num_qubits
        I = Matrix.identity(dim)
        max_err = 0.0
        for i in range(dim):
            for j in range(dim):
                diff = abs(product.data[i][j].re - I.data[i][j].re) + \
                       abs(product.data[i][j].im - I.data[i][j].im)
                if diff > max_err:
                    max_err = diff
        unitary_pass = max_err < 1e-6
        report["checks"]["unitarity"] = {
            "passed": unitary_pass,
            "max_error": max_err,
        }
        if not unitary_pass:
            report["passed"] = False

        # 2. Norm preservation
        sv = circuit.simulate()
        norm_sq = sum(abs(a) ** 2 for a in sv)
        norm_pass = abs(norm_sq - 1.0) < 1e-6
        report["checks"]["norm_preservation"] = {
            "passed": norm_pass,
            "norm_squared": norm_sq,
        }
        if not norm_pass:
            report["passed"] = False

        # 3. Gate count
        report["checks"]["gate_count"] = {
            "value": circuit.gate_count(),
            "passed": True,
        }
        report["checks"]["depth"] = {
            "value": circuit.depth(),
            "passed": True,
        }

        return report


class EvolverAgent:
    def evolve(self, target_circuit: QuantumCircuit, population_size: int = 8, generations: int = 10) -> List[Dict]:
        history = []
        # Compute target statevector
        target_sv = target_circuit.simulate()

        # Create initial population from mutations of the target
        population = []
        for _ in range(population_size):
            c = self._mutate(copy.deepcopy(target_circuit))
            population.append(c)

        for gen in range(generations):
            scored = []
            for c in population:
                f = self._fitness(c, target_sv)
                scored.append((f, c))
            scored.sort(key=lambda x: -x[0])

            best_f = scored[0][0]
            avg_f = sum(s[0] for s in scored) / len(scored)
            history.append({
                "generation": gen,
                "best_fitness": best_f,
                "avg_fitness": avg_f,
            })

            # Selection + crossover + mutation
            new_pop = [scored[0][1]]  # elitism
            while len(new_pop) < population_size:
                p1 = self._tournament(scored)
                p2 = self._tournament(scored)
                child = self._crossover(p1, p2)
                child = self._mutate(child)
                new_pop.append(child)
            population = new_pop

        return history

    def _fitness(self, circuit: QuantumCircuit, target_sv: list) -> float:
        try:
            sv = circuit.simulate()
            # Fidelity: |<target|result>|^2
            overlap = Complex(0, 0)
            for i in range(len(target_sv)):
                overlap = overlap + target_sv[i].conjugate() * sv[i]
            fidelity = abs(overlap) ** 2
            depth = max(circuit.depth(), 1)
            gc = max(circuit.gate_count(), 1)
            return fidelity / (depth * gc) * 100
        except Exception:
            return 0.0

    def _tournament(self, scored: list, k: int = 3) -> QuantumCircuit:
        pool = random.sample(scored, min(k, len(scored)))
        return max(pool, key=lambda x: x[0])[1]

    def _crossover(self, p1: QuantumCircuit, p2: QuantumCircuit) -> QuantumCircuit:
        child = QuantumCircuit(p1.num_qubits)
        cut = random.randint(0, len(p1.gates))
        child.gates = copy.deepcopy(p1.gates[:cut]) + copy.deepcopy(p2.gates[cut:])
        # Fix qubit references
        for g in child.gates:
            g["qubits"] = [q % child.num_qubits for q in g["qubits"]]
        return child

    def _mutate(self, circuit: QuantumCircuit, rate: float = 0.3) -> QuantumCircuit:
        c = copy.deepcopy(circuit)
        if not c.gates:
            return c
        for i in range(len(c.gates)):
            if random.random() < rate:
                single_gates = ["H", "X", "Y", "Z", "S", "T"]
                c.gates[i]["name"] = random.choice(single_gates)
                c.gates[i]["qubits"] = [random.randint(0, c.num_qubits - 1)]
                c.gates[i]["params"] = {}
        return c


# ============================================================================
# 8. SWARM ORCHESTRATOR
# ============================================================================
class SwarmResult:
    def __init__(self):
        self.circuit: Optional[QuantumCircuit] = None
        self.noise_report: Optional[dict] = None
        self.validation_report: Optional[dict] = None
        self.evolution_history: List[dict] = []
        self.debate_log: List[str] = []


class SwarmOrchestrator:
    def __init__(self, llm_fn: Callable[[str], str] = None):
        self.llm_fn = llm_fn or (lambda x: x)
        self.bus = MessageBus()
        self.planner = PlannerAgent()
        self.architect = CircuitArchitectAgent()
        self.mitigator = ErrorMitigatorAgent()
        self.validator = ValidatorAgent()
        self.evolver = EvolverAgent()

    def run(self, goal: str) -> SwarmResult:
        result = SwarmResult()

        # Phase 1: Planning
        plan = self.planner.plan(goal)
        self.bus.publish("planning", {"goal": goal, "plan": plan})

        # Phase 2: Build circuit
        arch_task = next((t for t in plan if t["agent"] == "architect"), None)
        if arch_task:
            circuit = self.architect.build(arch_task["task"])
            self.bus.publish("architecture", {"circuit_gates": circuit.gate_count()})
        else:
            circuit = QuantumCircuit(2)
            circuit.add_gate("H", [0])

        # Phase 3: Debate loop (Validator ↔ Architect)
        for round_num in range(3):
            v_report = self.validator.validate(circuit)
            self.bus.publish("validation", {"round": round_num, "report": v_report})
            if v_report["passed"]:
                result.debate_log.append(f"Round {round_num}: PASSED")
                break
            else:
                feedback = f"Validation failed: {v_report}"
                result.debate_log.append(f"Round {round_num}: FAILED — revising")
                circuit = self.architect.revise(circuit, feedback)
                self.bus.publish("revision", {"round": round_num})

        result.circuit = circuit
        result.validation_report = v_report

        # Phase 4: Noise analysis
        mit_task = next((t for t in plan if t["agent"] == "mitigator"), None)
        if mit_task:
            result.noise_report = self.mitigator.analyze(circuit)
            self.bus.publish("mitigation", result.noise_report)

        # Phase 5: Evolution
        evo_task = next((t for t in plan if t["agent"] == "evolver"), None)
        if evo_task:
            result.evolution_history = self.evolver.evolve(circuit, population_size=6, generations=5)
            self.bus.publish("evolution", {"generations": len(result.evolution_history)})

        return result

    def get_message_history(self) -> list:
        all_msgs = []
        for topic in ["planning", "architecture", "validation", "revision", "mitigation", "evolution"]:
            for msg in self.bus.get_history(topic):
                all_msgs.append({"topic": topic, **msg})
        return all_msgs
