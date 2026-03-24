# How ENGRAM OS Works

## A Human Guide to the System

**Last Updated:** March 24, 2026  
**For:** Developers, users, and anyone curious about what's happening under the hood

---

## The Big Picture

Imagine you have an AI assistant that **remembers everything you've worked on together**, **learns from its mistakes**, and **gets better at your specific projects over time**. That's ENGRAM OS.

Unlike ChatGPT or Claude, which start fresh every conversation, ENGRAM:
- Remembers your codebase structure
- Learns which patterns work in your projects
- Improves its own instructions automatically
- Runs entirely on your computer (no cloud, no API bills)

Think of it as an AI pair programmer that actually learns your codebase instead of forgetting everything when you close the chat.

---

## The Core Idea: Three Rings

ENGRAM operates in three continuous loops, called "Rings":

### Ring 1: Execution (Doing the Work)

You give ENGRAM a task like *"add login validation to the auth module"*. Here's what happens:

1. **Router** figures out what kind of task this is (coding, research, marketing, etc.)
2. **Context Assembler** loads relevant files from memory — your project structure, similar past work, coding conventions
3. **LLM** (running locally on your GPU) generates a response with tool calls
4. **Tools** execute: read files, write changes, run tests
5. **Writeback** block summarizes what was done

**Result:** Your task is completed with actual file changes, not just advice.

### Ring 2: Scoring (Learning What Worked)

After every task, ENGRAM scores its own performance:

1. **Execution Score** — If tests ran, what percentage passed? (Ground truth)
2. **LLM Judge Score** — A separate AI model evaluates the response quality
3. **Calibration** — The system adjusts for known biases:
   - "Hmm, I've been scoring too harshly on bug fixes lately"
   - "My judge was too optimistic on refactoring tasks"
4. **Proxy Signals** — Objective checks:
   - Did it actually call `write_file`? (Or just talk about changes?)
   - Are there generic phrases like "world-class solution"? (Marketing red flag)
   - Does it cite sources? (Research requirement)

**Result:** Every task gets a calibrated quality score (0.0 to 1.0) that accounts for domain-specific standards.

### Ring 3: Evolution (Getting Smarter)

After every 10 tasks, ENGRAM rewrites its own instructions:

1. **Analyze** the last 10 task completions and their scores
2. **Identify patterns** — "Low scores happened when I didn't read files before modifying"
3. **Propose improvement** — Add rule: "Always read file before writing"
4. **Test the patch** — Would this have improved past scores?
5. **Apply if better** — Rewrite the system prompt with the new rule

After 50 tasks, the **scoring rubric itself evolves**:
- "Bug fix scores are consistently 0.2 lower than they should be"
- "Adjust rubric: don't penalize missing tests on quick fixes"

**Result:** The system literally rewrites its own brain to work better for your specific use cases.

---

## The Memory System: Hot, Warm, and Cold

ENGRAM remembers things using a three-tier memory system, modeled after human memory:

### Hot Memory (Active Context)
- **What:** Currently relevant information
- **Size:** ~100 chunks (about 1500 tokens)
- **Example:** Files you're working on right now, current task context
- **Fate:** Gets compressed when full, least relevant items move to warm

### Warm Memory (Recent Sessions)
- **What:** Recent work, frequently accessed patterns
- **Size:** Unlimited (stored in RAM)
- **Example:** Last 10 sessions, your coding conventions, common utilities
- **Fate:** Can be promoted to hot when relevant, or demoted to cold when old

### Cold Memory (Full History)
- **What:** Everything ever done
- **Size:** Unlimited (archived on disk)
- **Example:** Sessions from months ago, old projects, deprecated patterns
- **Fate:** Only searched on-demand when you need something specific

**How it works:**

When you start a task, ENGRAM:
1. Looks at your recent messages to guess what you're working on
2. Searches warm memory for similar past work
3. Promotes relevant chunks to hot memory
4. Assembles context: system prompt + hot memory + your task
5. After the task, demotes irrelevant hot memory back to warm

This is why ENGRAM can say *"I remember you prefer async/await over callbacks"* — it's retrieving that pattern from warm memory.

---

## The Module System: Different Brains for Different Jobs

ENGRAM isn't one-size-fits-all. It has specialized modules for different domains:

### Coding Module (Most Developed)
- **Current Generation:** v3 (autonomously evolved)
- **Training:** 250+ tasks analyzed
- **Specialties:**
  - File navigation and reading
  - Implementation with `write_file`
  - Test running and verification
  - Code review and refactoring

**What makes it different:**
- Knows to read files before modifying
- Always verifies changes with read-back
- Understands your project's naming conventions
- Learned that TYPE A tasks (analysis) should complete in one response

### Marketing Module
- **Current Generation:** v1
- **Specialties:**
  - Copywriting with audience targeting
  - Specificity over generic phrases
  - Call-to-action inclusion
  - Format adherence (bullets vs paragraphs)

**What it watches for:**
- Generic filler phrases ("world-class", "cutting-edge") → penalized
- Specific numbers with timeframes ("23% reduction in 90 days") → rewarded
- Audience named in copy → rewarded

### Research Module
- **Current Generation:** v1
- **Specialties:**
  - Citation density
  - Internal consistency
  - Qualified claims (not presenting single studies as consensus)

**What it watches for:**
- Named references (Smith et al., 2023) → required for good scores
- Quantified claims → expected in analysis
- Qualification language ("however", "limited by") → intellectual honesty signal

**You can add your own modules** for legal, finance, medical, or any domain.

---

## The Tool System: Hands That Do Work

ENGRAM isn't just a chatbot — it has tools that actually modify your files:

### Available Tools

| Tool | What It Does | When Used |
|------|--------------|-----------|
| `read_text_file` | Reads file contents | Before analysis or modification |
| `write_file` | Creates or overwrites files | Implementing changes |
| `create_directory` | Makes new folders | Setting up project structure |
| `list_directory` | Shows folder contents | Exploring project layout |
| `run_command` | Executes shell commands | Running tests, linting, building |

### How Tools Work

When ENGRAM wants to use a tool:

1. **LLM generates** a tool call in its response:
   ```json
   {
     "name": "write_file",
     "arguments": {
       "path": "src/auth.py",
       "content": "def login(): ..."
     }
   }
   ```

2. **MCP Client** executes the tool:
   - Validates the path is allowed
   - Performs the operation
   - Captures output and return code

3. **Result returns** to LLM:
   ```json
   {
     "success": true,
     "stdout": "",
     "stderr": "",
     "returncode": 0
   }
   ```

4. **LLM continues** with next step or reports completion

**Critical rule:** ENGRAM learned (through Ring 3) that *thinking* about a change doesn't change the file. Only `write_file` does. So it's explicit about tool calls now.

---

## The Scoring System: How ENGRAM Judges Itself

This is where ENGRAM gets unique. Every task completion is scored, and the scoring system **learns from its own mistakes**.

### Two Scoring Paths

**Path 1: Execution Score (Ground Truth)**
- Did tests run? → Parse pytest output
- 5 passed, 0 failed? → Score = 1.0
- 0 passed, 5 failed? → Score = 0.0
- No tests? → Can't use this path

**Path 2: LLM Judge (Semantic Evaluation)**
- A separate LLM call evaluates the response
- Scores three dimensions:
  - **Correctness** — Factually accurate?
  - **Completeness** — All parts addressed?
  - **Convention Alignment** — Follows project patterns?
- Average becomes the score

### Calibration: Correcting for Bias

Here's the magic: ENGRAM tracks when its LLM judge was wrong.

**Example:**
```
Task: Fix auth bug
LLM Judge Score: 0.65
Actual Test Result: 1.0 (all tests passed)
Error: +0.35 (judge was too pessimistic)
```

After seeing this pattern 10+ times:
- **Bias Correction:** +0.30 for "fix_bug" tasks
- **Next Time:** LLM judge score gets +0.30 added automatically

### Proxy Signals: Objective Reality Checks

Sometimes the LLM judge is confidently wrong. Proxy signals catch this:

**Coding Proxies:**
- `write_file_called` — Did it actually modify files?
- `pytest_in_response` — Did tests run and pass?
- `writeback_present` — Proper summary provided?

**Marketing Proxies:**
- `generic_phrase_count` — How many "world-class" buzzwords?
- `specificity_signals` — Numbers with business context?
- `audience_named` — Persona or role mentioned?

**Research Proxies:**
- `named_refs` — Citations with author/year?
- `quantified_claims` — Numbers in analysis?
- `qualifier_count` — Intellectual honesty markers?

### Floor and Ceiling Rules

When proxy signals are strong, they override the LLM judge:

**Coding:**
- All tests pass (exec=1.0) → Score ≥ 0.80 (floor)
- All tests fail (exec=0.0) → Score ≤ 0.45 (ceiling)
- No `write_file` called → Score ≤ 0.65

**Marketing:**
- 3+ generic phrases → Score ≤ 0.50
- Zero specificity signals → Score ≤ 0.55
- No audience named → Score ≤ 0.70

**Research:**
- Zero named references → Score ≤ 0.55
- Zero quantified claims → Score ≤ 0.65
- Under 100 words → Score ≤ 0.50

### Human Corrections: You Can Teach It

If ENGRAM scores itself wrong, you can correct it:

```bash
engram score --session abc123 --task 3 --correct 0.95
```

This logs:
```
LLM Score: 0.75
Your Score: 0.95
Difference: +0.20
Weight: 3x (high-value calibration signal)
```

**10 human corrections = 30 automatic corrections** for calibration purposes. You're teaching the system what good looks like.

---

## The Evolution System: Rewriting Its Own Brain

This is the part that sounds like science fiction but actually works.

### Prompt Evolution (Every 10 Tasks)

**Step 1: Gather Evidence**
ENGRAM loads the last 10 task completions with their scores.

**Step 2: Find Patterns**
```
Low-scoring tasks (0.3-0.5):
- "Explain the auth flow" → Gave generic answer without reading files
- "List API endpoints" → Missed 3 endpoints in routes.py
- "Review security" → Didn't check auth.py for vulnerabilities

High-scoring tasks (0.8-0.9):
- "Fix login bug" → Read auth.py, found issue, wrote fix, verified with tests
- "Add validation" → Read existing validators, followed patterns, added tests
```

**Step 3: Propose Improvement**
```
Pattern: Low scores when not reading files first
Proposal: Add rule "Always read relevant files before analysis or modification"
Expected improvement: +0.20 on analysis tasks
```

**Step 4: Evaluate**
Test the patch on 3 historical tasks:
- Old prompt average: 0.52
- New prompt average: 0.80
- **Improvement: +0.28** ✅ (threshold was 0.05)

**Step 5: Apply**
Rewrite `engram/modules/coding/agent_system_prompt.md`:
```markdown
## CORE BEHAVIORS

1. Read before writing — always read existing files first
2. Follow existing patterns in the codebase
...
```

**Step 6: Backup**
Save old version as `agent_system_prompt.v2.bak` for rollback if needed.

### Rubric Evolution (Every 50 Tasks)

Scoring rubrics also evolve based on calibration data:

**Calibration Report:**
```
50 tasks analyzed:
- Mean error: +0.15 (LLM judge consistently pessimistic)
- Bug fix tasks: +0.25 error (very pessimistic)
- Refactor tasks: +0.05 error (slightly pessimistic)
```

**Prompt to LLM:**
```
Rewrite the rubric to correct for observed bias patterns.

Rules:
- If bias is "pessimistic" (mean_error > 0): relax penalty conditions
- Don't change JSON return format
- Keep under 400 words
```

**Result:** New rubric with relaxed penalties for bug fixes.

---

## Multi-Agent Orchestration: When One Agent Isn't Enough

For complex projects, ENGRAM can coordinate multiple specialized agents.

### The Shared Board

Imagine a whiteboard where agents post updates:

```
GOAL: Build user authentication system
DEADLINE: 2026-03-30
PROGRESS: 60%

BOARD:
┌─────────────┬───────────────┬────────────┬──────────┐
│  Backlog    │  In Progress  │   Review   │   Done   │
├─────────────┼───────────────┼────────────┼──────────┤
│ Add OAuth   │ Fix login bug │ Code review│ User model│
│ Rate limit  │ Write tests   │            │ Auth API  │
└─────────────┴───────────────┴────────────┴──────────┘

DECISIONS:
- Using JWT for tokens (not sessions)
- bcrypt for password hashing

BLOCKERS:
- Waiting on database schema approval
```

### Agent Signals

Agents don't write directly to the board. They produce signals:

```python
AgentSignal(
    agent_id="coding-agent-1",
    task_id="fix-login-bug",
    status="done",
    deliverables=[
        {"path": "src/auth.py", "description": "Fixed null pointer in login"}
    ],
    board_updates={
        "progress": 60,
        "blockers_resolved": ["null pointer issue"]
    },
    quality_score=0.85
)
```

### Handoffs

One agent can hand off to another:

```
Agent A (coding): "Implemented feature, needs testing"
  ↓ handoff
Agent B (qa): "Received, running tests now"
  ↓ signal
Board: Task moved from "In Progress" to "Review"
```

### Deadlock Detection

Sometimes tasks depend on each other in circles:

```
Task A → depends on Task B
Task B → depends on Task C
Task C → depends on Task A
```

**Result:** Nothing can run. Deadlock.

ENGRAM detects this using DFS (depth-first search) and suggests:
```
Deadlock detected: A → B → C → A
Suggestion: Remove dependency C → A (it's not actually required)
```

---

## A Real Example: Your First ENGRAM Session

Let's walk through what actually happens when you use ENGRAM.

### Step 1: You Give a Task

```bash
engram code "add email validation to the signup form"
```

### Step 2: Session Resolution

ENGRAM checks:
- Do you have an active session? → Use it
- No session? → Create one automatically
- Load your project context from warm memory

### Step 3: Boot System

Behind the scenes:
```
Hardware probe → RTX 3090, 24GB VRAM
Memory contract → 14GB weights, 1GB KV cache, 512MB scratch, 6GB hot memory
Vector DB → Load warm chunks, prepare hot tier
```

### Step 4: Router Classifies Task

```
Input: "add email validation to the signup form"
Router output:
{
  "domain": "coding",
  "task_type": "implement_feature",
  "complexity": "medium"
}
```

### Step 5: Context Assembly

ENGRAM loads:
- **Stones (protected):** System prompt, scratch note
- **Hot chunks:** Signup form code, existing validators, email patterns
- **Task:** Your request

Total context: ~1500 tokens

### Step 6: LLM Generates Response

The LLM (qwen3:30b on your GPU) produces:
```
I'll add email validation to the signup form.

First, let me read the existing signup form:
[tool_call: read_text_file path="src/signup.py"]

Now I'll check existing validators:
[tool_call: read_text_file path="src/validators.py"]

I'll add an email validator following the existing pattern:
[tool_call: write_file path="src/validators.py" content="..."]

Let me verify the changes:
[tool_call: read_text_file path="src/validators.py"]

```writeback
module: coding
status: done
files_modified: ["src/validators.py"]
conventions_learned: null
next_focus: null
evict: []
```
```

### Step 7: Tools Execute

Each tool call runs:
- `read_text_file` → Returns file content
- `write_file` → Writes changes, returns success
- `read_text_file` → Confirms changes are present

### Step 8: Scoring Happens

**Execution Score:**
- No tests ran → Can't use execution score

**LLM Judge Score:**
- Correctness: 0.9 (followed existing patterns)
- Completeness: 0.8 (added validation, didn't add tests)
- Convention alignment: 0.9 (matched validator style)
- **Average: 0.87**

**Proxy Signals:**
- `write_file_called`: True ✅
- `writeback_present`: True ✅
- `response_length`: 450 words

**Calibration:**
- Historical bias for "implement_feature": +0.05
- **Final Score: 0.87 + 0.05 = 0.92**

### Step 9: Logging

Everything gets logged:
```json
{
  "task": "add email validation to the signup form",
  "response_length": 450,
  "tool_calls_count": 4,
  "quality_score": 0.92,
  "quality_source": "llm_judge_calibrated",
  "timestamp": "2026-03-24T01:30:00"
}
```

### Step 10: Memory Update

- Hot tier: Signup form, validators (still relevant)
- Warm tier: This session added to recent work
- Cold tier: Full session archived

### Step 11: Learning Check

- Tasks since last learning: 8
- **Threshold:** 10 tasks → Not yet triggered
- **Next check:** After 2 more tasks

---

## What Makes ENGRAM Different

### vs. ChatGPT / Claude

| Feature | ChatGPT | Claude | ENGRAM |
|---------|---------|--------|--------|
| Remembers your codebase | ❌ No | ⚠️ Limited | ✅ Yes |
| Learns from mistakes | ❌ No | ❌ No | ✅ Yes (Ring 3) |
| Runs locally | ❌ No | ❌ No | ✅ Yes |
| Modifies files directly | ❌ No | ❌ No | ✅ Yes |
| Improves over time | ❌ No | ❌ No | ✅ Yes |
| Domain-specific scoring | ❌ No | ❌ No | ✅ Yes |

### vs. Aider / Copilot

| Feature | Aider | Copilot | ENGRAM |
|---------|-------|---------|--------|
| Persistent memory | ❌ No | ⚠️ Limited | ✅ Yes |
| Self-scoring | ❌ No | ❌ No | ✅ Yes |
| Multi-agent | ❌ No | ❌ No | ✅ Yes |
| Prompt evolution | ❌ No | ❌ No | ✅ Yes |
| Human calibration | ❌ No | ❌ No | ✅ Yes |

**The key difference:** ENGRAM is the only system that **gets smarter the more you use it** — not just knowing your codebase, but literally rewriting its own instructions based on what works.

---

## The Hardware: What You Need

### Minimum Requirements

- **GPU:** NVIDIA with 8GB+ VRAM (GTX 1070 or better)
- **RAM:** 16GB system memory
- **Storage:** 50GB free space
- **Python:** 3.10 or later

### Recommended

- **GPU:** RTX 3090 (24GB VRAM) — what the system was developed on
- **RAM:** 32GB system memory
- **Storage:** 100GB SSD
- **Model:** qwen3:30b-a3b-q4_K_M (via Ollama)

### What Runs Where

```
VRAM (24GB on RTX 3090):
┌──────────────────────────────────────┐
│  Model weights         ~15 GB        │
│  KV cache (context)    ~1 GB         │
│  Scratch / stones      ~512 MB       │
│  Vector DB hot tier    ~6 GB         │
└──────────────────────────────────────┘

RAM (32GB):
┌──────────────────────────────────────┐
│  Vector DB warm tier   Unlimited     │
│  Session data          As needed     │
└──────────────────────────────────────┘
```

---

## Common Questions

### "Does it actually learn or is that marketing?"

It actually learns. After 10 tasks, check:
```bash
cat engram/modules/coding/learning_history.jsonl | tail -1
```

You'll see what it learned and how much quality improved.

### "What if it learns something wrong?"

Every evolution is backed up. You can rollback:
```bash
cp engram/modules/coding/agent_system_prompt.v2.bak engram/modules/coding/agent_system_prompt.md
```

### "Can I use it without a GPU?"

Technically yes, but it'll be slow. The system is designed for local GPU inference.

### "Does it phone home?"

No. Everything runs locally. No API calls, no telemetry, no cloud sync.

### "What if I want to add a new domain?"

Create a module:
```bash
mkdir engram/modules/legal
# Add agent_system_prompt.md
# Add to module_registry.yaml
```

After 10 legal tasks, it'll evolve its own legal expertise.

---

## The Philosophy

ENGRAM is built on three beliefs:

1. **AI should remember** — Forgetting everything after each session is a bug, not a feature.

2. **AI should improve** — If the system doesn't get better at your specific work, it's stagnating.

3. **AI should be yours** — Running on your hardware, learning your patterns, serving your goals — not a cloud service's metrics.

---

## Next Steps

**Want to try it?**

```bash
git clone https://github.com/ynajimiii/engram-os.git
cd engram-os
pip install -e ".[dev]"
ollama pull qwen3:30b-a3b-q4_K_M
engram doctor
engram code "read main.py and explain the entry point"
```

**Want to understand it deeper?**

Read these files in order:
1. `engram/core/agent.py` — The main agent loop
2. `engram/core/scorer.py` — How scoring works
3. `engram/core/learner.py` — How evolution works
4. `engram/orchestration/board.py` — Multi-agent coordination

**Want to contribute?**

Pick a module domain you know (legal, finance, medical, design) and create a module for it. After 10 tasks, watch it evolve beyond what you wrote.

---

*ENGRAM OS — Built on a single RTX 3090. Running generation 3. No cloud. No reset. Every task makes it smarter.*
