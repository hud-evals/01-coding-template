# Hardware-Software Co-Design Collective

## Overview
You are building a multi-agent Hardware-Software Co-Design system from scratch. This system simulates a cross-functional engineering team that explores novel chip architectures, compiles and optimizes programs, simulates execution, benchmarks performance/power trade-offs, and advises on fabrication constraints.

## Instructions
- Create and edit the solution directly in `/home/ubuntu/workspace/codesign_engine.py`.
- **CRITICAL**: Use ONLY the Python 3.10 standard library. No third-party packages allowed.
- You are building a production-grade multi-agent co-design engine.

## Architecture Requirements

### 1. ISA Definition & Instruction Classes
- **`Instruction`** class with attributes: `opcode`, `operands`, `latency_cycles`, `power_mw`, `pipeline_stage`. Must have `to_dict()`.
- **`ISA`** class: `__init__(self, name, word_size=32)`. Default `register_count=16`. Stores instructions in a dict keyed by opcode. Methods: `add_instruction`, `get_instruction(opcode)` (returns None if missing), `instruction_count()`, `avg_power()` (0.0 if empty), `to_dict()`.

### 2. Architecture Explorer Agent
**`ArchitectureExplorerAgent`**:
- `propose_risc() -> ISA`: Returns `"RISC-Lite"` ISA, word_size=32, 16 registers, with standard RISC instructions including arithmetic, memory, branch, and control flow operations.
- `propose_neuromorphic() -> ISA`: Returns `"NeuroCore-v1"` ISA, word_size=16, 8 registers, with neuromorphic computing primitives (spiking, accumulation, threshold, synapse operations) — should have lower average power than RISC.
- `compare_architectures(a, b) -> dict`: Compares two ISAs and recommends the one with lower average power.

### 3. Program & Compiler Optimizer
- **`ProgramInstruction`**: opcode + operands list.
- **`Program`**: list of instructions with `add(opcode, operands)` and `length()`.
- **`CompilerOptimizerAgent`**:
  - `validate_program(program, isa)`: Unknown opcodes → errors. Returns `{"valid": bool, "errors": [...], "warnings": [...], "instruction_count": int}`.
  - `dead_code_elimination(program)`: Removes NOP instructions.
  - `strength_reduction(program)`: Replaces expensive ops with cheaper equivalents where possible (e.g. multiply by constant powers of two, divide by one).
  - `optimize(program, isa) -> Tuple[Program, dict]`: Full pipeline returning optimized program and report.

### 4. Simulator Agent
**`SimulatorAgent(isa)`**: Register-based CPU simulator.
- Registers `R0..R{n-1}` initialized to 0. Memory dict. Track cycles, energy, execution trace.
- `execute_program(program, max_cycles=10000) -> dict`: Executes instructions, resolving operands as register names or integer literals. Handles arithmetic, memory, branching, and halt. Division by zero returns 0 without crashing. Energy = `power_mw * latency_cycles * 0.001` per instruction.

### 5. Benchmark Critic Agent
**`BenchmarkCriticAgent`**:
- `analyze(sim_result, isa) -> dict`: Computes IPC, energy efficiency, performance/power scores, combined PPA score, letter grade, and bottleneck diagnostics.

### 6. Fabrication Advisor Agent
**`FabricationAdvisorAgent`**:
- Supports process nodes: `"7nm"`, `"14nm"`, `"28nm"` with realistic density/cost/yield parameters.
- `estimate_die_area(isa, process_node)`: Estimates transistor count, die area, and cost. Raises `ValueError` for unknown nodes.
- `recommend_node(isa, budget_per_die)`: Recommends the best-fit process node within budget, or `None` if none fit.

### 7. Message Bus & Orchestrator
- **`MessageBus`**: Thread-safe pub/sub using `threading.Lock`. Methods: `publish(topic, message)`, `get_history(topic)`.
- **`CoDesignOrchestrator`**: Coordinates full pipeline: Architecture → Compile → Simulate → Benchmark → Fabrication. Returns comprehensive results dict.

### Technical Constraints
- Python standard library only.
- All computations must be deterministic.
- MessageBus must be thread-safe.
