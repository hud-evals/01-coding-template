"""Hardware-Software Co-Design Collective Engine.

A multi-agent system that bridges chip design and software optimization.
Pure Python standard library only.
"""

import json
import math
import threading
from typing import Dict, List, Optional, Any, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ISA Definition & Architecture Explorer
# ═══════════════════════════════════════════════════════════════════════════════

class Instruction:
    """Represents a single ISA instruction."""
    def __init__(self, opcode: str, operands: List[str], latency_cycles: int,
                 power_mw: float, pipeline_stage: str = "execute"):
        self.opcode = opcode
        self.operands = operands
        self.latency_cycles = latency_cycles
        self.power_mw = power_mw
        self.pipeline_stage = pipeline_stage

    def to_dict(self) -> dict:
        return {
            "opcode": self.opcode,
            "operands": self.operands,
            "latency_cycles": self.latency_cycles,
            "power_mw": self.power_mw,
            "pipeline_stage": self.pipeline_stage,
        }


class ISA:
    """Instruction Set Architecture definition."""
    def __init__(self, name: str, word_size: int = 32):
        self.name = name
        self.word_size = word_size
        self.instructions: Dict[str, Instruction] = {}
        self.register_count = 16
        self.pipeline_stages = ["fetch", "decode", "execute", "memory", "writeback"]

    def add_instruction(self, instr: Instruction):
        self.instructions[instr.opcode] = instr

    def get_instruction(self, opcode: str) -> Optional[Instruction]:
        return self.instructions.get(opcode)

    def instruction_count(self) -> int:
        return len(self.instructions)

    def avg_power(self) -> float:
        if not self.instructions:
            return 0.0
        return sum(i.power_mw for i in self.instructions.values()) / len(self.instructions)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "word_size": self.word_size,
            "register_count": self.register_count,
            "instructions": {k: v.to_dict() for k, v in self.instructions.items()},
        }


class ArchitectureExplorerAgent:
    """Proposes novel hardware architectures."""

    def propose_risc(self) -> ISA:
        isa = ISA("RISC-Lite", word_size=32)
        base_instrs = [
            Instruction("ADD", ["rd", "rs1", "rs2"], 1, 0.5, "execute"),
            Instruction("SUB", ["rd", "rs1", "rs2"], 1, 0.5, "execute"),
            Instruction("MUL", ["rd", "rs1", "rs2"], 3, 1.2, "execute"),
            Instruction("DIV", ["rd", "rs1", "rs2"], 8, 1.8, "execute"),
            Instruction("LOAD", ["rd", "addr"], 4, 0.8, "memory"),
            Instruction("STORE", ["rs", "addr"], 4, 0.8, "memory"),
            Instruction("BEQ", ["rs1", "rs2", "offset"], 1, 0.3, "decode"),
            Instruction("BNE", ["rs1", "rs2", "offset"], 1, 0.3, "decode"),
            Instruction("NOP", [], 1, 0.1, "fetch"),
            Instruction("HALT", [], 0, 0.0, "fetch"),
        ]
        for instr in base_instrs:
            isa.add_instruction(instr)
        return isa

    def propose_neuromorphic(self) -> ISA:
        isa = ISA("NeuroCore-v1", word_size=16)
        isa.register_count = 8
        neuro_instrs = [
            Instruction("SPIKE", ["neuron_id", "weight"], 1, 0.2, "execute"),
            Instruction("ACCUM", ["rd", "rs1", "rs2"], 1, 0.3, "execute"),
            Instruction("THRESH", ["rd", "threshold"], 1, 0.15, "execute"),
            Instruction("SYNAPSE", ["src", "dst", "weight"], 2, 0.4, "execute"),
            Instruction("DECAY", ["rd", "factor"], 1, 0.1, "execute"),
            Instruction("FIRE", ["neuron_id"], 1, 0.25, "execute"),
            Instruction("INHIBIT", ["neuron_id"], 1, 0.15, "execute"),
            Instruction("NOP", [], 1, 0.05, "fetch"),
            Instruction("HALT", [], 0, 0.0, "fetch"),
        ]
        for instr in neuro_instrs:
            isa.add_instruction(instr)
        return isa

    def compare_architectures(self, arch_a: ISA, arch_b: ISA) -> Dict[str, Any]:
        return {
            "arch_a": arch_a.name,
            "arch_b": arch_b.name,
            "instr_count_a": arch_a.instruction_count(),
            "instr_count_b": arch_b.instruction_count(),
            "avg_power_a": round(arch_a.avg_power(), 4),
            "avg_power_b": round(arch_b.avg_power(), 4),
            "word_size_a": arch_a.word_size,
            "word_size_b": arch_b.word_size,
            "recommendation": arch_a.name if arch_a.avg_power() <= arch_b.avg_power() else arch_b.name,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Program Representation & Compiler Optimizer
# ═══════════════════════════════════════════════════════════════════════════════

class ProgramInstruction:
    """A single instruction in a program."""
    def __init__(self, opcode: str, operands: List[str]):
        self.opcode = opcode
        self.operands = operands

    def __repr__(self):
        return f"{self.opcode} {', '.join(self.operands)}"


class Program:
    """A list of instructions forming a program."""
    def __init__(self, name: str):
        self.name = name
        self.instructions: List[ProgramInstruction] = []

    def add(self, opcode: str, operands: List[str]):
        self.instructions.append(ProgramInstruction(opcode, operands))

    def length(self) -> int:
        return len(self.instructions)


class CompilerOptimizerAgent:
    """Adapts and optimizes code for a given ISA."""

    def validate_program(self, program: Program, isa: ISA) -> Dict[str, Any]:
        errors = []
        warnings = []
        for idx, instr in enumerate(program.instructions):
            isa_instr = isa.get_instruction(instr.opcode)
            if isa_instr is None:
                errors.append(f"Line {idx}: Unknown opcode '{instr.opcode}'")
            elif len(instr.operands) != len(isa_instr.operands):
                warnings.append(
                    f"Line {idx}: '{instr.opcode}' expects {len(isa_instr.operands)} "
                    f"operands, got {len(instr.operands)}"
                )
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "instruction_count": program.length(),
        }

    def dead_code_elimination(self, program: Program) -> Program:
        """Remove NOP instructions (simple dead code elimination)."""
        optimized = Program(program.name + "_optimized")
        for instr in program.instructions:
            if instr.opcode != "NOP":
                optimized.instructions.append(instr)
        return optimized

    def strength_reduction(self, program: Program) -> Program:
        """Replace expensive operations with cheaper equivalents.
        MUL rd, rs, 2 -> ADD rd, rs, rs
        DIV rd, rs, 1 -> copy (ADD rd, rs, R0 where R0=0)
        """
        optimized = Program(program.name + "_strength_reduced")
        for instr in program.instructions:
            if instr.opcode == "MUL" and len(instr.operands) >= 3 and instr.operands[2] == "2":
                optimized.instructions.append(
                    ProgramInstruction("ADD", [instr.operands[0], instr.operands[1], instr.operands[1]])
                )
            elif instr.opcode == "DIV" and len(instr.operands) >= 3 and instr.operands[2] == "1":
                optimized.instructions.append(
                    ProgramInstruction("ADD", [instr.operands[0], instr.operands[1], "R0"])
                )
            else:
                optimized.instructions.append(instr)
        return optimized

    def optimize(self, program: Program, isa: ISA) -> Tuple[Program, Dict[str, Any]]:
        """Full optimization pipeline."""
        p1 = self.dead_code_elimination(program)
        p2 = self.strength_reduction(p1)
        report = {
            "original_length": program.length(),
            "optimized_length": p2.length(),
            "eliminated_nops": program.length() - p1.length(),
            "strength_reductions": p1.length() - p2.length() if p1.length() != p2.length() else sum(
                1 for a, b in zip(p1.instructions, p2.instructions) if a.opcode != b.opcode
            ),
        }
        return p2, report


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Simulator Agent
# ═══════════════════════════════════════════════════════════════════════════════

class SimulatorAgent:
    """Runs high-fidelity emulations of hardware-software interactions."""

    def __init__(self, isa: ISA):
        self.isa = isa
        self.registers: Dict[str, int] = {f"R{i}": 0 for i in range(isa.register_count)}
        self.memory: Dict[int, int] = {}
        self.pc = 0
        self.cycle_count = 0
        self.energy_consumed_mj = 0.0
        self.halted = False
        self.execution_trace: List[Dict[str, Any]] = []

    def reset(self):
        self.registers = {f"R{i}": 0 for i in range(self.isa.register_count)}
        self.memory = {}
        self.pc = 0
        self.cycle_count = 0
        self.energy_consumed_mj = 0.0
        self.halted = False
        self.execution_trace = []

    def _resolve_operand(self, op: str) -> int:
        if op in self.registers:
            return self.registers[op]
        try:
            return int(op)
        except ValueError:
            return 0

    def execute_program(self, program: Program, max_cycles: int = 10000) -> Dict[str, Any]:
        self.reset()
        while self.pc < program.length() and not self.halted and self.cycle_count < max_cycles:
            instr = program.instructions[self.pc]
            isa_instr = self.isa.get_instruction(instr.opcode)

            if isa_instr is None:
                self.pc += 1
                self.cycle_count += 1
                continue

            self.cycle_count += isa_instr.latency_cycles
            self.energy_consumed_mj += isa_instr.power_mw * isa_instr.latency_cycles * 0.001

            self.execution_trace.append({
                "pc": self.pc,
                "opcode": instr.opcode,
                "cycle": self.cycle_count,
            })

            if instr.opcode == "ADD" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[1])
                b = self._resolve_operand(instr.operands[2])
                self.registers[instr.operands[0]] = a + b
            elif instr.opcode == "SUB" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[1])
                b = self._resolve_operand(instr.operands[2])
                self.registers[instr.operands[0]] = a - b
            elif instr.opcode == "MUL" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[1])
                b = self._resolve_operand(instr.operands[2])
                self.registers[instr.operands[0]] = a * b
            elif instr.opcode == "DIV" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[1])
                b = self._resolve_operand(instr.operands[2])
                self.registers[instr.operands[0]] = a // b if b != 0 else 0
            elif instr.opcode == "LOAD" and len(instr.operands) >= 2:
                addr = self._resolve_operand(instr.operands[1])
                self.registers[instr.operands[0]] = self.memory.get(addr, 0)
            elif instr.opcode == "STORE" and len(instr.operands) >= 2:
                addr = self._resolve_operand(instr.operands[1])
                self.registers.get(instr.operands[0], 0)
                self.memory[addr] = self._resolve_operand(instr.operands[0])
            elif instr.opcode == "HALT":
                self.halted = True
            # BEQ/BNE branching
            elif instr.opcode == "BEQ" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[0])
                b = self._resolve_operand(instr.operands[1])
                if a == b:
                    offset = self._resolve_operand(instr.operands[2])
                    self.pc += offset
                    continue
            elif instr.opcode == "BNE" and len(instr.operands) >= 3:
                a = self._resolve_operand(instr.operands[0])
                b = self._resolve_operand(instr.operands[1])
                if a != b:
                    offset = self._resolve_operand(instr.operands[2])
                    self.pc += offset
                    continue

            self.pc += 1

        return {
            "cycles": self.cycle_count,
            "energy_mj": round(self.energy_consumed_mj, 6),
            "instructions_executed": len(self.execution_trace),
            "halted": self.halted,
            "registers": dict(self.registers),
            "timed_out": self.cycle_count >= max_cycles,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Benchmark Critic Agent
# ═══════════════════════════════════════════════════════════════════════════════

class BenchmarkCriticAgent:
    """Evaluates performance/power trade-offs and suggests iterations."""

    def analyze(self, sim_result: Dict[str, Any], isa: ISA) -> Dict[str, Any]:
        cycles = sim_result.get("cycles", 1)
        energy = sim_result.get("energy_mj", 0.0)
        instr_executed = sim_result.get("instructions_executed", 0)

        ipc = instr_executed / max(cycles, 1)
        energy_per_instr = energy / max(instr_executed, 1)

        # Performance score: higher IPC is better (max ~1.0 for single-issue)
        perf_score = min(ipc, 1.0) * 100.0

        # Power score: lower energy per instruction is better
        # Normalize: < 0.001 mJ/instr is excellent
        power_score = max(0.0, 100.0 - (energy_per_instr * 100000.0))
        power_score = min(power_score, 100.0)

        # Combined PPA (Performance-Power-Area) score
        ppa_score = (perf_score * 0.5) + (power_score * 0.5)

        bottlenecks = []
        if ipc < 0.3:
            bottlenecks.append("Low IPC - consider adding parallel execution units")
        if energy_per_instr > 0.002:
            bottlenecks.append("High energy per instruction - optimize power gating")
        if sim_result.get("timed_out", False):
            bottlenecks.append("Execution timed out - possible infinite loop")

        return {
            "ipc": round(ipc, 4),
            "energy_per_instruction_mj": round(energy_per_instr, 6),
            "performance_score": round(perf_score, 2),
            "power_score": round(power_score, 2),
            "ppa_score": round(ppa_score, 2),
            "bottlenecks": bottlenecks,
            "grade": "A" if ppa_score >= 80 else "B" if ppa_score >= 60 else "C" if ppa_score >= 40 else "F",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Fabrication Advisor Agent
# ═══════════════════════════════════════════════════════════════════════════════

class FabricationAdvisorAgent:
    """Factors in manufacturing constraints and supply chain realities."""

    PROCESS_NODES = {
        "7nm": {"transistor_density": 100e6, "cost_per_mm2": 0.25, "max_clock_ghz": 5.0, "yield_pct": 85.0},
        "14nm": {"transistor_density": 40e6, "cost_per_mm2": 0.10, "max_clock_ghz": 4.0, "yield_pct": 92.0},
        "28nm": {"transistor_density": 15e6, "cost_per_mm2": 0.04, "max_clock_ghz": 3.0, "yield_pct": 96.0},
    }

    def estimate_die_area(self, isa: ISA, process_node: str = "14nm") -> Dict[str, Any]:
        node = self.PROCESS_NODES.get(process_node)
        if node is None:
            raise ValueError(f"Unknown process node: {process_node}. Valid: {list(self.PROCESS_NODES.keys())}")

        # Estimate: each instruction type needs ~50k transistors for decode/execute logic
        # Registers need ~1k transistors each (flip-flops)
        transistor_count = (isa.instruction_count() * 50000) + (isa.register_count * 1000)
        die_area_mm2 = transistor_count / node["transistor_density"]
        cost = die_area_mm2 * node["cost_per_mm2"]
        effective_yield = node["yield_pct"] / 100.0

        return {
            "process_node": process_node,
            "transistor_count": transistor_count,
            "die_area_mm2": round(die_area_mm2, 6),
            "cost_per_die_usd": round(cost, 4),
            "estimated_yield_pct": node["yield_pct"],
            "effective_cost_usd": round(cost / effective_yield, 4),
            "max_clock_ghz": node["max_clock_ghz"],
        }

    def recommend_node(self, isa: ISA, budget_per_die: float) -> Dict[str, Any]:
        viable = []
        for node_name in self.PROCESS_NODES:
            est = self.estimate_die_area(isa, node_name)
            if est["effective_cost_usd"] <= budget_per_die:
                viable.append(est)

        if not viable:
            return {"recommendation": None, "reason": "No process node fits within budget."}

        # Pick the one with lowest area (best density)
        best = min(viable, key=lambda x: x["die_area_mm2"])
        return {"recommendation": best["process_node"], "details": best}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Message Bus & Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class MessageBus:
    """Thread-safe pub/sub message bus for agent communication."""
    def __init__(self):
        self._lock = threading.Lock()
        self._history: Dict[str, List[Dict[str, Any]]] = {}

    def publish(self, topic: str, message: Dict[str, Any]):
        with self._lock:
            if topic not in self._history:
                self._history[topic] = []
            self._history[topic].append(message)

    def get_history(self, topic: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history.get(topic, []))


class CoDesignOrchestrator:
    """Central coordinator for the hardware-software co-design pipeline."""

    def __init__(self):
        self.bus = MessageBus()
        self.explorer = ArchitectureExplorerAgent()
        self.compiler = CompilerOptimizerAgent()
        self.fab_advisor = FabricationAdvisorAgent()

    def run_pipeline(self, arch_type: str = "risc", program: Program = None,
                     process_node: str = "14nm", budget: float = 1.0) -> Dict[str, Any]:
        # Step 1: Architecture exploration
        if arch_type == "neuromorphic":
            isa = self.explorer.propose_neuromorphic()
        else:
            isa = self.explorer.propose_risc()

        self.bus.publish("architecture", {"isa": isa.name, "instructions": isa.instruction_count()})

        # Step 2: If program provided, compile and optimize
        compile_report = None
        opt_report = None
        sim_result = None
        benchmark = None

        if program is not None:
            validation = self.compiler.validate_program(program, isa)
            self.bus.publish("compilation", {"validation": validation})

            if validation["valid"]:
                optimized, opt_report = self.compiler.optimize(program, isa)
                self.bus.publish("optimization", opt_report)

                # Step 3: Simulate
                sim = SimulatorAgent(isa)
                sim_result = sim.execute_program(optimized)
                self.bus.publish("simulation", sim_result)

                # Step 4: Benchmark analysis
                critic = BenchmarkCriticAgent()
                benchmark = critic.analyze(sim_result, isa)
                self.bus.publish("benchmark", benchmark)

            compile_report = validation

        # Step 5: Fabrication feasibility
        fab_estimate = self.fab_advisor.estimate_die_area(isa, process_node)
        node_rec = self.fab_advisor.recommend_node(isa, budget)
        self.bus.publish("fabrication", {"estimate": fab_estimate, "recommendation": node_rec})

        return {
            "architecture": isa.to_dict(),
            "compilation": compile_report,
            "optimization": opt_report,
            "simulation": sim_result,
            "benchmark": benchmark,
            "fabrication": {"estimate": fab_estimate, "recommendation": node_rec},
            "message_log": {
                "architecture": self.bus.get_history("architecture"),
                "compilation": self.bus.get_history("compilation"),
                "optimization": self.bus.get_history("optimization"),
                "simulation": self.bus.get_history("simulation"),
                "benchmark": self.bus.get_history("benchmark"),
                "fabrication": self.bus.get_history("fabrication"),
            },
        }
