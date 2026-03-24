Here's the full architecture map in a clear text format instead — this is actually more useful as reference material

---

## ENGRAM OS — Architecture Map

### Layer 1 — CLI (user entry point)
```
doctor · init · run · status · session · module · config · export · benchmark
         ↓
```

### Layer 2 — Core Engine

```
┌─────────────────────────────────────────────────────────────────┐
│  AGENT                  MEMORY                  MODULES         │
│  ─────────────────────  ─────────────────────  ──────────────── │
│  router_call()          probe + contract        module_loader    │
│  worker_call()          vector_db (FAISS)       scratch template │
│  agent_turn()           semantic router         agent prompt     │
│  parse_writeback()      assembler               chunkers         │
│  apply_writeback()      scratch note            learner          │
│  MCP tool loop          hot / warm tiers        experience store │
│  planner()              eviction loop           module registry  │
│  horizon()              stones (protected)      ingest pipeline  │
└─────────────────────────────────────────────────────────────────┘
         ↓
```

### Layer 3 — Infrastructure
```
Ollama · FAISS-GPU · MCP tools · pynvml · PyYAML · sentence-transformers
```

---

## The Agent Turn — Data Flow

Every call to `agent_turn()` follows this exact sequence:

```
User goal (task_text)
    │
    ▼
router_call()          ← same model, temp=0.1, max 150 tokens
    │                    classify: domain · task_type · complexity
    │                    returns JSON dict
    ▼
check_pressure_and_evict()
    │                    if hot_utilization > 0.85: demote bottom 20%
    ▼
route_task()           ← semantic scoring against task embedding
    │                    cosine similarity + anchor bias from scratch
    │                    promotes relevant chunks to hot tier
    │                    demotes irrelevant chunks to warm
    ▼
assemble_context()     ← stones + hot chunks + task text
    │                    stones = system_prompt + scratch_note (protected)
    │                    hot chunks = FAISS-GPU search results
    │                    total ~1500 tokens
    ▼
worker_call()          ← same model, temp=0.7, max 2048 tokens
    │                    full generation with MCP tool access
    │                    loops until no more tool_calls in response
    ▼
parse_writeback()      ← extracts ```writeback block from response
    │                    YAML: module, status, files, evict, next_focus
    ▼
apply_writeback()      ← updates scratch note deterministically
    │                    db.demote() for each evict signal
    ▼
scratch.log() + scratch.save()
    │                    appends to session_log (append-only)
    │                    persists YAML to disk
    ▼
return response string
```

---

## Memory Architecture — VRAM Budget

```
VRAM — 24576 MB (RTX 3090)
┌──────────────────────────────────────┐
│  model weights         ~15000 MB     │ FIXED
│  ──────────────────────────────────  │
│  KV cache               ~1024 MB     │ GROWS with context
│  ──────────────────────────────────  │
│  scratch / stones         512 MB     │ FIXED (never evicted)
│  ──────────────────────────────────  │
│  vector DB hot tier     ~5968 MB ↕   │ SHRINKS as KV grows
└──────────────────────────────────────┘

RAM — 32768 MB
┌──────────────────────────────────────┐
│  vector DB warm tier    unlimited    │ RECOVERABLE (demoted chunks)
└──────────────────────────────────────┘

Inverse coupling:
  context grows  →  KV expands  →  hot DB compressed  →  eviction fires
  context clears →  KV shrinks  →  hot DB expands     →  more chunks loaded
```

---

## Component Relationships

```
boot_system()
  ├── probe.py → get_hardware_state()
  ├── contract.py → calculate_memory_budget()
  └── vector_db.py → GPUVectorDB(max_hot_chunks)

agent_turn()
  ├── llm.py → router_call() + worker_call()
  ├── router.py → route_task() → vector_db.promote() / demote()
  ├── assembler.py → assemble_context() + check_pressure_and_evict()
  ├── writeback.py → parse_writeback() + apply_writeback()
  └── scratch.py → ScratchNote.log() + save()

new_session()
  ├── module_loader.py → detect_use_case() + load_module()
  ├── session.py → new_session() / load_session()
  └── stones.py → load_stones() → system_prompt + scratch_note

run_long_horizon()
  ├── planner.py → goal_to_task_graph() + TaskQueue
  ├── agent_session.py → AgentSession (per domain)
  └── horizon.py → autonomous loop + replan_if_blocked()
```

---

## What Each File Owns

```
probe.py          → hardware numbers (one question to GPU)
contract.py       → memory budget (one struct from four numbers)
boot.py           → system init (wires probe → contract → db)
scratch.py        → project map (read/write YAML)
stones.py         → protected memory (system prompt + scratch)
session.py        → session lifecycle (new / load / save)
vector_db.py      → FAISS hot+warm tiers (add/promote/demote)
router.py         → cosine scoring (task → chunk relevance)
assembler.py      → context builder (stones + chunks + task)
pipeline.py       → run_task() entry point
llm.py            → router_call() + worker_call() + tool loop
writeback.py      → parse fenced block + apply to scratch
agent.py          → agent_turn() full cycle
agent_session.py  → domain-isolated session wrapper
shared_scratch.py → cross-agent namespace safety
planner.py        → goal decomposition + TaskQueue
horizon.py        → autonomous long-horizon execution loop
ingestion.py      → codebase → semantic chunks → warm DB
learner.py        → module prompt evolution (autoresearch)
experience.py     → trajectory → tactical insight (XSkill)
scorer.py         → quality_score per task (LLM-as-judge)
```

---

That's the complete system. Every component has a single sentence description, every relationship is explicit, every data flow is directional. Good reference to keep alongside the scratch note when working on the remaining fixes.