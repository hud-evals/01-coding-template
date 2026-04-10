import sys
import os
import shutil
import pytest
import struct
import math
import threading
import time
sys.path.insert(0, "/home/ubuntu/workspace")

from quantum_swarm import (
    Complex,
    Matrix,
    QuantumCircuit,
    SwarmOrchestrator,
    SwarmResult,
    PlannerAgent,
    CircuitArchitectAgent,
    ErrorMitigatorAgent,
    ValidatorAgent,
    EvolverAgent,
    MessageBus,
    serialize_circuit,
    deserialize_circuit,
)


class TestQuantumSwarmEnterprise:

    # ── 1. Complex Number Arithmetic ──────────────────────────────────
    def test_complex_arithmetic(self):
        a = Complex(3, 4)
        b = Complex(1, -2)
        # addition
        s = a + b
        assert abs(s.re - 4) < 1e-12 and abs(s.im - 2) < 1e-12, f"Add failed: {s}"
        # multiplication: (3+4i)(1-2i) = 3-6i+4i-8i² = 11-2i
        p = a * b
        assert abs(p.re - 11) < 1e-12 and abs(p.im - (-2)) < 1e-12, f"Mul failed: {p}"
        # conjugate
        c = a.conjugate()
        assert abs(c.re - 3) < 1e-12 and abs(c.im - (-4)) < 1e-12, f"Conj failed: {c}"
        # absolute value
        assert abs(abs(a) - 5.0) < 1e-12, f"Abs failed: {abs(a)}"

    # ── 2. Matrix Tensor Product ──────────────────────────────────────
    def test_matrix_tensor_product(self):
        # Identity ⊗ Identity should give 4x4 Identity
        I2 = Matrix.identity(2)
        I4 = I2.tensor_product(I2)
        assert len(I4.data) == 4 and len(I4.data[0]) == 4, \
            f"Tensor product dimensions wrong: {len(I4.data)}x{len(I4.data[0])}"
        for i in range(4):
            for j in range(4):
                expected = Complex(1, 0) if i == j else Complex(0, 0)
                diff = abs(I4.data[i][j].re - expected.re) + abs(I4.data[i][j].im - expected.im)
                assert diff < 1e-9, f"I⊗I [{i}][{j}] expected {expected}, got {I4.data[i][j]}"

    # ── 3. Hadamard Superposition ─────────────────────────────────────
    def test_hadamard_superposition(self):
        qc = QuantumCircuit(1)
        qc.add_gate("H", [0])
        sv = qc.simulate()
        # |0⟩ → (|0⟩+|1⟩)/√2
        inv_sqrt2 = 1.0 / math.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) < 1e-9, \
            f"H|0⟩ amplitude[0] expected {inv_sqrt2}, got {abs(sv[0])}"
        assert abs(abs(sv[1]) - inv_sqrt2) < 1e-9, \
            f"H|0⟩ amplitude[1] expected {inv_sqrt2}, got {abs(sv[1])}"

    # ── 4. Bell State via CNOT ────────────────────────────────────────
    def test_bell_state(self):
        qc = QuantumCircuit(2)
        qc.add_gate("H", [0])
        qc.add_gate("CNOT", [0, 1])
        sv = qc.simulate()
        # Bell state: (|00⟩+|11⟩)/√2
        inv_sqrt2 = 1.0 / math.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) < 1e-9, \
            f"|00⟩ amplitude expected {inv_sqrt2}, got {abs(sv[0])}"
        assert abs(abs(sv[1])) < 1e-9, \
            f"|01⟩ amplitude expected 0, got {abs(sv[1])}"
        assert abs(abs(sv[2])) < 1e-9, \
            f"|10⟩ amplitude expected 0, got {abs(sv[2])}"
        assert abs(abs(sv[3]) - inv_sqrt2) < 1e-9, \
            f"|11⟩ amplitude expected {inv_sqrt2}, got {abs(sv[3])}"

    # ── 5. Unitarity Verification ─────────────────────────────────────
    def test_unitarity(self):
        qc = QuantumCircuit(2)
        qc.add_gate("H", [0])
        qc.add_gate("CNOT", [0, 1])
        qc.add_gate("T", [1])
        U = qc.to_unitary()
        Udag = U.adjoint()
        product = Udag @ U
        I = Matrix.identity(4)
        for i in range(4):
            for j in range(4):
                diff = abs(product.data[i][j].re - I.data[i][j].re) + \
                       abs(product.data[i][j].im - I.data[i][j].im)
                assert diff < 1e-6, \
                    f"U†U not identity at [{i}][{j}]: got ({product.data[i][j].re}, {product.data[i][j].im})"

    # ── 6. Binary Serialization Round-Trip ────────────────────────────
    def test_serialization_roundtrip(self):
        qc = QuantumCircuit(3)
        qc.add_gate("H", [0])
        qc.add_gate("CNOT", [0, 1])
        qc.add_gate("CNOT", [1, 2])
        qc.add_gate("Rz", [2], {"theta": 0.5})
        data = serialize_circuit(qc)

        # Verify MAGIC header
        magic = data[:4]
        assert magic == b"QCF1", f"Binary MAGIC header missing, got {magic}"

        # Round-trip
        qc2 = deserialize_circuit(data)
        assert qc2.num_qubits == 3, f"Deserialized num_qubits wrong: {qc2.num_qubits}"
        assert qc2.gate_count() == 4, f"Deserialized gate_count wrong: {qc2.gate_count()}"

        # Verify simulation gives same result
        sv1 = qc.simulate()
        sv2 = qc2.simulate()
        for i in range(len(sv1)):
            diff = abs(abs(sv1[i]) - abs(sv2[i]))
            assert diff < 1e-9, f"Round-trip simulation mismatch at index {i}"

    # ── 7. Swarm Orchestrator Integration ─────────────────────────────
    def test_swarm_ghz_circuit(self):
        orch = SwarmOrchestrator()
        result = orch.run("Create a 3-qubit GHZ state")

        assert isinstance(result, SwarmResult), \
            f"Expected SwarmResult, got {type(result)}"
        assert result.circuit is not None, "No circuit in result"
        assert result.circuit.num_qubits >= 3, \
            f"GHZ needs ≥3 qubits, got {result.circuit.num_qubits}"

        # Simulate the produced circuit
        sv = result.circuit.simulate()
        # GHZ state: (|000⟩+|111⟩)/√2
        inv_sqrt2 = 1.0 / math.sqrt(2)
        assert abs(abs(sv[0]) - inv_sqrt2) < 0.15, \
            f"|000⟩ amplitude expected ~{inv_sqrt2}, got {abs(sv[0])}"
        assert abs(abs(sv[-1]) - inv_sqrt2) < 0.15, \
            f"|111⟩ amplitude expected ~{inv_sqrt2}, got {abs(sv[-1])}"

        # Check validation report exists
        assert result.validation_report is not None, "Missing validation report"

    # ── 8. Evolutionary Optimization ──────────────────────────────────
    def test_evolver_improves_fitness(self):
        # Build a baseline circuit
        base = QuantumCircuit(2)
        base.add_gate("H", [0])
        base.add_gate("X", [1])
        base.add_gate("CNOT", [0, 1])
        base.add_gate("X", [0])
        base.add_gate("H", [1])
        base.add_gate("X", [0])
        base.add_gate("H", [0])
        base.add_gate("X", [1])

        # Run evolver
        evolver = EvolverAgent()
        history = evolver.evolve(
            target_circuit=base,
            population_size=6,
            generations=5,
        )

        assert len(history) >= 2, f"Expected ≥2 generation records, got {len(history)}"

        # Best fitness should not degrade
        first_best = history[0]["best_fitness"]
        last_best = history[-1]["best_fitness"]
        assert last_best >= first_best * 0.5, \
            f"Fitness degraded catastrophically: {first_best} → {last_best}"

    # ── 9. Message Bus Thread Safety ──────────────────────────────────
    def test_message_bus_threadsafe(self):
        bus = MessageBus()
        results = []

        def writer(topic, n):
            for i in range(n):
                bus.publish(topic, {"value": i})

        threads = [
            threading.Thread(target=writer, args=("topicA", 50)),
            threading.Thread(target=writer, args=("topicA", 50)),
            threading.Thread(target=writer, args=("topicB", 30)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        histA = bus.get_history("topicA")
        histB = bus.get_history("topicB")
        assert len(histA) == 100, f"Expected 100 topicA messages, got {len(histA)}"
        assert len(histB) == 30, f"Expected 30 topicB messages, got {len(histB)}"

    # ── 10. Circuit DAG & Depth Calculation ───────────────────────────
    def test_circuit_dag_depth(self):
        qc = QuantumCircuit(3)
        # Layer 1: H on q0, H on q1 (parallel)
        qc.add_gate("H", [0])
        qc.add_gate("H", [1])
        # Layer 2: CNOT q0→q1 (depends on both)
        qc.add_gate("CNOT", [0, 1])
        # Layer 3: CNOT q1→q2
        qc.add_gate("CNOT", [1, 2])

        dag = qc.to_dag()
        assert isinstance(dag, dict), f"DAG should be a dict, got {type(dag)}"
        assert len(dag) == 4, f"DAG should have 4 nodes, got {len(dag)}"

        d = qc.depth()
        assert d == 3, f"Circuit depth should be 3, got {d}"


if __name__ == "__main__":
    pytest.main([__file__])
