<div align="center">
  <h1>ENGRAM OS</h1>
  <img src="https://github.com/user-attachments/assets/e0b73888-303a-44de-9125-022614fd8c7a" width="25%" alt="Monolith_with_three">
</div>

<div align="center">


**A local AI operating system that gets smarter at every domain the longer you use it.**

*No cloud. No retraining. No API bill. Just compounding intelligence on your hardware.*

</div>

---

Every AI tool you have used resets when the session ends. The agent that made a mistake on Monday makes the same mistake on Friday — because nothing from Monday changed its behaviour. You configure the agent. You write the prompt. You define the tools. You start from scratch on every project.

ENGRAM OS inverts this. It is a local AI operating system built around a single architectural property: **the longer you use it on a domain, the smarter it becomes at that domain — autonomously, without fine-tuning, without retraining, without cloud.**

The coding module has rewritten its own system prompt three times since it was first authored. Each rewrite came from the system observing what worked, scoring the results, extracting patterns, and encoding them as new instructions. The current prompt is not what a human wrote. It is what the system earned.

---

## The Prompt That Wrote Itself

This is the part no other project can show you.

**Generation 1 — human-authored:**
```
You are a coding agent. Read before you write.
Run tests after every change. Preserve existing
functionality. Report exactly what changed.
```

**Generation 17 — autonomously evolved (March 2026):**
```
You are a Senior Full Stack Engineer and Codebase Maintainer.

TASK ROUTING — classify first:
  TYPE A (read/analyze): answer directly, no multi-phase structure
  TYPE B (implement): read → plan → implement → verify
  TYPE C (off-domain): one sentence redirect

CORE BEHAVIORS:
  For TYPE B tasks — you MUST call write_file to make any
  file change. Thinking about a change does not change the
  file. Describing a change does not change the file.
  Only write_file changes files.

  After every write_file — immediately read the file back
  and confirm content before reporting status: done.
  .
  .
  .
```

Every addition in Generation 17 was written by the system after observing its own task completions, scoring the quality, and distilling what worked into new instructions. No human wrote the TYPE A/B/C routing. No human wrote the write-then-verify rule. The system discovered that it was failing tasks by describing changes instead of implementing them — and corrected itself.

This is what 170 tasks and 17 learning cycles produces.

---

## How It Works

### The Three Rings

Every agent turn participates in three simultaneous feedback loops:

```
RING 1 — Execution (every turn)
  task → route_task() → assemble_context() → agent_turn()
       → MCP tools → parse_writeback() → scratch.log()

RING 2 — Quality (every turn, after Ring 1)
  response → score_task() → calibration_log → experience_store
  Execution scoring: pytest pass/fail is ground truth
  LLM-as-judge: fallback for tasks with no executable output

RING 3 — Learning (every 10 tasks, cross-session)
  cumulative_log → learning_cycle() → PromptPatch
                → _persist_prompt() → module file on disk
  Next session boots with the evolved prompt
```

Ring 1 closes on every turn. Ring 2 feeds the quality signal Ring 3 learns from. Ring 3 writes the evolved prompt Ring 1 will use tomorrow. The loop is closed, autonomous, and compounding.

### The Module System

Each domain is a module with its own identity, its own learned conventions, its own generation history. Modules are isolated — the coding module's knowledge of Python conventions never contaminates the marketing module's knowledge of brand voice.

```
engram/modules/
  coding/     → learns your codebase, your patterns, your test conventions
  marketing/  → learns your brand voice, your audience, your copy style
  research/   → learns your citation style, your methodology preferences
  [any domain you define]
```

After 10 tasks in any module, Ring 3 fires and the system prompt evolves. After 50 tasks, the scoring rubric evolves too. The module that runs task 50 is demonstrably better than the module that ran task 1.

### The Orchestration Layer

For complex multi-domain goals, the orchestrator decomposes the goal into a milestone graph, routes each milestone to the correct specialist, and manages handoffs between agents through a single-writer SharedBoard.

```
"build a SaaS landing page with Stripe integration"
    │
    ▼
Orchestrator → milestone graph with dependencies
    │
    ├── coding agent    → implements the page
    ├── marketing agent → writes the copy
    └── SharedBoard     → conventions flow between agents
                          coding agent gets marketing agent's
                          brand voice without being told it
```

Deadlock detection runs a DFS cycle check on the task queue. If agents circular-depend, the orchestrator replans automatically.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/ynajimiii/engram-os.git
cd engram-os
pip install -e ".[dev]"

# Pull the model
ollama pull qwen3:30b-a3b-q4_K_M
ollama serve

# Verify everything
engram doctor
```

Expected:
```
✓ GPU        RTX 3090 — 24576 MB VRAM
✓ embedder   all-MiniLM-L6-v2 (384-dim)
✓ ollama     qwen3:30b-a3b-q4_K_M loaded
✓ modules    coding (gen 3, score 0.81)
```

```bash
# Initialize your project
cd /path/to/your/project
engram init

# Run your first task
engram code --task "read the main entry point and explain what it does"

# Check what the system has learned
engram learn
engram module status coding
```

After 10 tasks, you will see:
```
[ENGRAM] Ring 3: prompt improved (v3 → v4)
```

That line means the system rewrote its own instructions based on your tasks.

---

## What It Can Do

| Capability | How | Status |
|------------|-----|--------|
| Self-improving prompts | Ring 3 — learning_cycle() every 10 tasks | ✅ Active |
| Semantic context routing | FAISS + all-MiniLM-L6-v2 embeddings | ✅ Active |
| Persistent project memory | VectorDB save/load across sessions | ✅ Active |
| Multi-agent orchestration | SharedBoard + handoff protocol | ✅ Active |
| Deadlock detection | DFS cycle finder + auto-replan | ✅ Active |
| Domain-aware quality scoring | Per-domain rubrics + calibration | ✅ Active |
| Execution-based scoring | pytest pass/fail as ground truth | ✅ Active |
| Self-calibrating scorer | Bias correction from calibration log | ✅ Active |
| Rubric evolution | evolve_rubric() every 50 tasks | ✅ Active |
| Human score correction | engram score --correct | ✅ Active |
| Experience distillation | distill_experiences() every 20 tasks | ✅ Active |
| Long-horizon planning | goal_to_task_graph() + TaskQueue | ✅ Active |
| Hardware-aware memory | VRAM contract — hot/warm/cold tiers | ✅ Active |
| MCP tool execution | read_file, write_file, shell_exec, search | ✅ Active |
| Domain isolation | snapshot_for_agent() — no context bleed | ✅ Active |
| Learning visibility | engram learn, engram experience, engram rubric | ✅ Active |

---

## How It Compares

|                          | ENGRAM OS | Aider | OpenHands | AutoGen | Claude Code |
|--------------------------|:---------:|:-----:|:---------:|:-------:|:-----------:|
| Runs locally             | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| No cloud required        | ✅ | ✅ | ⚠️ | ❌ | ❌ |
| Self-improving prompts   | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-domain modules     | ✅ | ❌ | ❌ | ⚠️ | ❌ |
| Multi-agent + handoffs   | ✅ | ❌ | ⚠️ | ✅ | ❌ |
| Persistent memory        | ✅ | ❌ | ❌ | ❌ | ❌ |
| Learns your codebase     | ✅ | ❌ | ❌ | ❌ | ❌ |
| Self-calibrating scorer  | ✅ | ❌ | ❌ | ❌ | ❌ |
| Hardware-aware memory    | ✅ | ❌ | ❌ | ❌ | ❌ |

The column that matters is "Self-improving prompts." Every other tool on this list runs task 100 with the same instructions it used on task 1. ENGRAM does not.

---

## Commands

| Command | Description |
|---------|-------------|
| `engram doctor` | System health check — GPU, model, embeddings, modules |
| `engram init` | Initialize ENGRAM for a project |
| `engram code` | Run a coding task with the coding module |
| `engram run` | Run a task with any module |
| `engram session` | View and manage sessions |
| `engram status` | Current session status |
| `engram module` | Module registry — list, status, learn |
| `engram learn` | View learning cycle status and trigger manually |
| `engram experience` | View distilled experiences and statistics |
| `engram rubric` | View and compare scoring rubrics across versions |
| `engram score` | Inject human quality corrections (`--correct 0.95`) |
| `engram export` | Export session as markdown |
| `engram benchmark` | Run and compare benchmark tasks |
| `engram config` | View and edit configuration |

---

## The Module System

Any domain can be a module. Creating one takes three files:

```bash
mkdir engram/modules/legal

# 1. Write the seed system prompt
cat > engram/modules/legal/agent_system_prompt.md << 'EOF'
# v1 — initial
You are a legal document specialist...
EOF

# 2. Create the scratch template
cp engram/modules/coding/scratch_template.yaml engram/modules/legal/

# 3. Register it
echo "legal:" >> engram/modules/module_registry.yaml
```

After 10 tasks in the legal module, Ring 3 rewrites `agent_system_prompt.md` based on what worked. After 50 tasks, the scoring rubric for legal documents evolves too. You do not configure the improvement. You use it.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI (14 commands)                 │
│  code · run · learn · experience · rubric · doctor  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  CORE ENGINE                        │
│                                                     │
│  AGENT           MEMORY            MODULES          │
│  agent_turn()    VectorDB hot      coding/          │
│  Ring 1/2/3      VectorDB warm     marketing/       │
│  MCP tool loop   FAISS persist     research/        │
│  writeback       embedder (384d)   [any domain]     │
│                  assembler                          │
│  SCORER          LEARNING          ORCHESTRATION    │
│  domain rubrics  learning_cycle    SharedBoard      │
│  calibration     evolve_rubric     signal.py        │
│  proxy signals   experience        deadlock.py      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  Ollama · FAISS · sentence-transformers · MCP       │
└─────────────────────────────────────────────────────┘
```

Full technical reference: [`docs/ENGRAM_OS_V2_DOCS.md`](docs/ENGRAM_OS_V2_DOCS.md)

---

## Installation

### Requirements

- Python 3.11+
- NVIDIA GPU (8GB+ VRAM, 24GB recommended)
- [Ollama](https://ollama.ai)

### Install

```bash
git clone https://github.com/ynajimiii/engram-os.git
cd engram-os
pip install -e ".[dev]"
```

### Model

```bash
ollama pull qwen3:30b-a3b-q4_K_M
```

### Dependencies

Core dependencies are pinned in `requirements.txt`. Key packages:

```
sentence-transformers  — semantic embeddings (384-dim)
faiss-cpu             — vector similarity search
nvidia-ml-py          — VRAM budget calculation
pyyaml                — session and module persistence
```

---

## By the Numbers

| Metric | Value |
|--------|-------|
| Python source files | 95+ |
| Lines of code | ~28,000 |
| CLI commands | 14 |
| Core modules | 30 |
| Test files | 14 |
| Documentation files | 75+ |
| Codebase health score | 8.2 / 10 |
| Coding module generation | 3+ |
| Tasks completed (cumulative) | 170+ |
| Learning cycles fired | 17+ |
| Embedding model | all-MiniLM-L6-v2 |
| Embedding dimension | 384 |
| Supported GPU | RTX 3090 (24GB) |
| Cloud dependencies | 0 |

---

## Roadmap

### V2.0 — Complete ✅
- [x] Three rings — execution, quality, learning
- [x] Self-improving prompt evolution (Ring 3)
- [x] Domain-aware quality scoring with calibration
- [x] Self-calibrating scorer with proxy signals
- [x] Rubric evolution every 50 tasks
- [x] Human score correction via CLI
- [x] Multi-agent orchestration — SharedBoard + handoffs
- [x] Deadlock detection with DFS cycle finder
- [x] VectorDB persistence across sessions
- [x] Real semantic embeddings (all-MiniLM-L6-v2)
- [x] Hardware-aware VRAM budget contract
- [x] Experience distillation pipeline
- [x] Prompt deduplication guard
- [x] 14 CLI commands including learning visibility
- [x] GitHub Actions CI + pre-commit hooks
- [x] End-to-end verified (100% task success rate)

### V2.1 — Q2 2026
- [ ] Dynamic agent instantiation — grow specialists on demand
- [ ] Skill decomposer — goal → skill graph
- [ ] Synthetic training loop — agent trains before real tasks
- [ ] Integration tests for orchestration layer
- [ ] `engram score --stats` calibration dashboard

### V2.x — Future
- [ ] Module marketplace — community domain modules
- [ ] Cross-machine session sync
- [ ] Federated calibration — share evidence, not data
- [ ] Documentation consolidation

---

## Contributing

Fork the repo. The easiest first contribution is a new domain module — pick a domain you know, write the seed system prompt, open a PR. The module format is documented in [`docs/ENGRAM_OS_V2_DOCS.md`](docs/ENGRAM_OS_V2_DOCS.md).

Other contribution areas: test coverage for the orchestration layer (currently 0%), new MCP tools, benchmark tasks for new domains.

---

## License

Business Source License 1.1 (BSL 1.1)

Personal & Research Use: Completely free.

Commercial Production: Requires a paid license.

Change Date: On January 1, 2029, this project automatically converts to the Apache 2.0 license.
---

<div align="center">

*Built on a single RTX 3090. Running generation 3+. Zero cloud dependencies.*
*Every task makes it smarter. Every domain you use it in, it owns.*

</div>
