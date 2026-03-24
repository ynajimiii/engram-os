# ENGRAM OS — USER GUIDE

**Version:** 0.1.0  
**Last Updated:** March 24, 2026  
**For:** Developers, Teams, and AI Practitioners

---

## TABLE OF CONTENTS

1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [CLI Commands Reference](#cli-commands-reference)
4. [Common Workflows](#common-workflows)
5. [Learning System](#learning-system)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)
8. [Configuration](#configuration)

---

## QUICK START

```bash
# 1. Check system health
engram doctor

# 2. Initialize a project
engram init

# 3. Run your first task
engram code "implement a login form with email validation"

# 4. Check status
engram status

# 5. View learning status
engram learn
```

**That's it!** ENGRAM OS will automatically learn from your tasks and improve over time.

---

## INSTALLATION

### Prerequisites

- **Python:** 3.10 or later
- **GPU:** NVIDIA with 8GB+ VRAM (24GB recommended)
- **Ollama:** Installed and running

### Step 1: Install Ollama

```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai/download
```

### Step 2: Pull Required Models

```bash
# Main model (coding tasks)
ollama pull qwen3:30b-a3b-q4_K_M

# Embedding model (for semantic search)
ollama pull all-minilm:l6-v2
```

### Step 3: Install ENGRAM OS

```bash
# Clone repository
git clone https://github.com/ynajimiii/engram-os.git
cd engram-os

# Install dependencies
pip install -e ".[dev]"

# Verify installation
python -m engram doctor
```

### Expected Output

```
  ══════════════════════════════════════════════════
  ENGRAM OS — System Health Check
  ══════════════════════════════════════════════════

  Dependencies
  ──────────────────────────────────────────────────
  ✓ faiss-gpu: 1.7.4
  ✓ sentence-transformers: 2.3.1
  ✓ pynvml: 11.5.0
  ✓ psutil: 5.9.8
  ✓ PyYAML: 6.0.1

  GPU & Hardware
  ──────────────────────────────────────────────────
  ✓ GPU: NVIDIA GeForce RTX 3090 (24576 MB VRAM)
  ✓ RAM: 32 GB available

  Ollama
  ──────────────────────────────────────────────────
  ✓ Ollama: running
  ✓ Model: qwen3:30b-a3b-q4_K_M

  All checks passed ✓
```

---

## CLI COMMANDS REFERENCE

### Setup & Health Commands

#### `engram doctor` — System Health Check

**Purpose:** Verify system requirements and diagnose issues

**Usage:**
```bash
engram doctor              # Run health check
engram doctor --json       # Output as JSON
```

**When to use:**
- After installation
- When encountering errors
- Before important tasks

---

#### `engram init` — Project Setup

**Purpose:** Initialize a new ENGRAM project

**Usage:**
```bash
engram init                                    # Interactive setup
engram init --path /path/to/project            # Specify path
engram init --module coding --name my-project  # Non-interactive
```

**Interactive Prompts:**
1. Hardware check (automatic)
2. Ollama check (automatic)
3. Module selection (coding/marketing/seo/custom)
4. Project naming
5. Codebase ingestion (optional)

**Output:**
- Creates session file in `engram/sessions/`
- Ingests project files into vector DB
- Ready for task execution

---

### Execution Commands

#### `engram code` — Coding Tasks

**Purpose:** Execute coding tasks with file/shell tools

**Usage:**
```bash
engram code "implement login form"
engram code "fix auth bug" --session abc123
engram code "add tests for user module" --module coding
engram code --dry-run "refactor auth.py"  # Preview only
```

**What it does:**
1. Reads relevant files
2. Makes changes using `write_file`
3. Runs tests if requested
4. Scores response quality
5. Logs to session

**Example Session:**
```bash
$ engram code "add email validation to signup form"

  ══════════════════════════════════════════════════
  ENGRAM OS — Coding
  ══════════════════════════════════════════════════

✓ GPU: NVIDIA GeForce RTX 3090 (24 GB)
✓ Model: qwen3:30b-a3b-q4_K_M
✓ Hot tier: 45 chunks (2.3 MB)

Coding... ⠋

I'll add email validation to the signup form.

First, let me read the existing signup form:
[tool_call: read_text_file path="src/signup.py"]

Now I'll add validation:
[tool_call: write_file path="src/signup.py" content="..."]

Let me verify the changes:
[tool_call: read_text_file path="src/signup.py"]

```writeback
module: coding
status: done
files_modified: ["src/signup.py"]
conventions_learned: null
next_focus: null
evict: []
```

Quality: 0.87 (llm_judge_calibrated)
══════════════════════════════════════════════════════
✓ Task complete (28.4s)
══════════════════════════════════════════════════════
```

---

#### `engram run` — Multi-Step Goals

**Purpose:** Execute complex, multi-step goals

**Usage:**
```bash
engram run --goal "implement JWT authentication"
engram run --goal "build REST API" --module coding
engram run --interactive  # REPL mode
```

**When to use:**
- Complex features requiring multiple files
- Goals needing planning and iteration
- Tasks that may take multiple agent turns

---

### Management Commands

#### `engram status` — Session Status

**Purpose:** View current session state

**Usage:**
```bash
engram status                           # Current session
engram status --session abc123          # Specific session
engram status --json                    # JSON output
```

**Output:**
```
  ══════════════════════════════════════════════════
  ENGRAM OS — Session Status
  ══════════════════════════════════════════════════

✓ Project:  my-auth-service
✓ Module:   coding
✓ Session:  abc123-def456.yaml

Active Tasks
──────────────────────────────────────────────────────
  ✓ Create user model
  ✓ Implement JWT auth
  ● Add password hashing
  ○ Write tests
  ○ Add documentation

Conventions Learned
──────────────────────────────────────────────────────
  - Use bcrypt for password hashing
  - Store tokens in HTTP-only cookies
  - Validate token expiry on each request

Recent Tasks (last 5)
──────────────────────────────────────────────────────
  1. [DONE] Create user model (0.92)
  2. [DONE] Implement JWT auth (0.88)
  3. [DONE] Add password hashing (0.85)
```

---

#### `engram session` — Session Management

**Purpose:** Manage multiple project sessions

**Usage:**
```bash
engram session list                      # List all sessions
engram session resume my-auth-service    # Resume session
engram session history my-auth-service   # View history
engram session delete old-project        # Delete session
engram session export my-project         # Export as markdown
```

**Example:**
```bash
$ engram session list

  ══════════════════════════════════════════════════
  ENGRAM OS — Sessions
  ══════════════════════════════════════════════════

Learning Status
──────────────────────────────────────────────────────
✓ Embeddings: all-minilm:l6-v2 (local)
✓ Cumulative tasks: 168
✓ Next learning: in 2 tasks

Sessions
──────────────────────────────────────────────────────
  my-auth-service      coding     2026-03-24 15:30   15 tasks
  marketing-campaign   marketing  2026-03-23 10:15   8 tasks
  seo-audit            seo        2026-03-22 14:00   12 tasks
```

---

#### `engram module` — Module Management

**Purpose:** View and manage modules

**Usage:**
```bash
engram module list                # List available modules
engram module info coding         # Module details
engram module validate ./custom   # Validate custom module
```

**Available Modules:**
| Module | Description | Extensions |
|--------|-------------|------------|
| coding | Software development | .py .ts .tsx .js .yaml .sql .md |
| marketing | Brand copy, campaigns | .md .txt .csv .yaml |
| seo | Keyword research, audits | .csv .json .md .txt .yaml |

---

#### `engram config` — Configuration

**Purpose:** View and modify configuration

**Usage:**
```bash
engram config show                      # Show all config
engram config get model                 # Get specific value
engram config set model qwen3:30b       # Set value
engram config reset                     # Reset to defaults
```

**Configuration Groups:**

| Group | Settings |
|-------|----------|
| **Inference** | model, router_model, ollama_url |
| **Memory** | weights_mb, n_ctx, scratch_mb |
| **Learning** | context_limit, max_tokens, min_response_chars |
| **Paths** | sessions_dir |
| **Behavior** | default_module, verbose, color |

**Example:**
```bash
$ engram config show

  ══════════════════════════════════════════════════
  ENGRAM OS — Configuration
  ══════════════════════════════════════════════════
  File: /home/user/.engram/config.yaml

  Inference
  ──────────────────────────────────────────────────
    model                qwen3:30b-a3b-q4_K_M
    router_model         qwen2.5:7b
    ollama_url           http://localhost:11434

  Memory
  ──────────────────────────────────────────────────
    weights_mb           14000
    n_ctx                8192
    scratch_mb           512

  Learning
  ──────────────────────────────────────────────────
    context_limit        10
    max_tokens           4096
    min_response_chars   150
```

---

### Learning Commands

#### `engram learn` — Learning Cycle Management

**Purpose:** View and trigger learning cycles

**Usage:**
```bash
engram learn                           # Show status
engram learn --module coding           # Trigger learning
engram learn --history                 # Show history
engram learn --show-patches            # Show patches
engram learn --trigger                 # Force trigger
```

**Output:**
```
  ══════════════════════════════════════════════════
  ENGRAM OS — Learning Status
  ══════════════════════════════════════════════════

✓ Embeddings: all-minilm:l6-v2 (ollama)
✓ Cumulative tasks: 168
✓ Next learning: in 2 tasks

Configuration
──────────────────────────────────────────────────────
    Trigger every:     10 tasks
    Tasks to analyze:  20
    Min improvement:   0.05
```

**When learning triggers:**
- **Automatic:** Every 10 tasks
- **Manual:** `engram learn --module coding`
- **Force:** `engram learn --trigger` (ignores 10-task rule)

---

#### `engram experience` — Experience Retrieval

**Purpose:** View distilled experiences

**Usage:**
```bash
engram experience list                   # List experiences
engram experience search "validation"    # Search
engram experience stats                  # Statistics
```

**Output:**
```
  ══════════════════════════════════════════════════
  ENGRAM OS — Experience Statistics
  ══════════════════════════════════════════════════

Overview
──────────────────────────────────────────────────────
✓ Total tasks:           168
✓ Expected experiences:  ~8
✓ Next experience in:    12 tasks

Distillation Schedule
──────────────────────────────────────────────────────
    Experiences are distilled every 20 tasks
    Each experience analyzes task patterns and extracts insights
```

---

#### `engram rubric` — Rubric Management

**Purpose:** View and compare scoring rubrics

**Usage:**
```bash
engram rubric show coding                # Show current
engram rubric history coding             # Evolution history
engram rubric compare coding v1 v2       # Compare versions
engram rubric stats coding               # Calibration stats
```

**Output:**
```
  ══════════════════════════════════════════════════
  ENGRAM OS — Calibration Stats — coding
  ══════════════════════════════════════════════════

Overview
──────────────────────────────────────────────────────
✓ Total entries:        34
✓ With ground truth:    0
✓ Human corrections:    0

Bias Analysis
──────────────────────────────────────────────────────
    Mean error:         +0.0000
    Mean absolute err:  0.0000
    Bias direction:     calibrated
✓ Calibration looks good
```

---

#### `engram score` — Quality Corrections

**Purpose:** Inject human quality corrections

**Usage:**
```bash
engram score --session abc123 --task 3 --correct 0.95
engram score --module coding --stats
```

**When to use:**
- When you disagree with auto-score
- To teach system your quality standards
- Human corrections weighted 3x in calibration

**Example:**
```bash
$ engram score --session abc123 --task 3 --correct 0.95

[ENGRAM] Human correction recorded:
  Session:     abc123
  Task   3:    implement login form
  LLM score:   0.75
  Your score:  0.95
  Difference:  +0.20
  Weight:      3x (high-value calibration signal)
  Module:      coding
```

---

### Analysis Commands

#### `engram export` — Export Reports

**Purpose:** Export session as markdown report

**Usage:**
```bash
engram export my-auth-service
engram export my-project --output ./reports/
```

**Output:** Markdown file with:
- Project info
- Task log
- Conventions learned
- Files modified
- Decisions made

---

#### `engram benchmark` — Run Benchmarks

**Purpose:** Run ENGRAM benchmark suite

**Usage:**
```bash
engram benchmark              # Full suite (5 tests)
engram benchmark --quick      # 3 tests
engram benchmark --share      # Shareable results
```

**Benchmarks:**
| Metric | Description | Target |
|--------|-------------|--------|
| Context Precision | Context relevance | ≥0.80 |
| Goal Coherence | Goal adherence | ≥0.50 |
| Resume Fidelity | Session resume | ≥0.85 |
| Learning Effectiveness | Prompt improvement | ≥0.05 |
| Tool Efficiency | Tool call efficiency | ≥0.70 |

---

## COMMON WORKFLOWS

### Workflow 1: New Project Setup

```bash
# 1. Check system
engram doctor

# 2. Initialize project
engram init --path /path/to/project --module coding

# 3. Run first task
engram code "read main.py and explain the entry point"

# 4. Check status
engram status
```

---

### Workflow 2: Daily Development

```bash
# 1. Check session status
engram status

# 2. Run coding task
engram code "add user authentication"

# 3. Review quality score
# If score seems low, inject correction
engram score --session abc123 --task 5 --correct 0.90

# 4. Continue with next task
engram code "add password reset"
```

---

### Workflow 3: Learning Cycle

```bash
# 1. Check learning status
engram learn

# Output: Next learning: in 2 tasks

# 2. Run 2 more tasks
engram code "fix login bug"
engram code "add email validation"

# 3. Trigger learning
engram learn --module coding

# 4. View learning history
engram learn --history
```

---

### Workflow 4: Multi-Project Management

```bash
# 1. List all sessions
engram session list

# 2. Switch to auth project
engram session resume my-auth-service

# 3. Run task
engram code "add JWT refresh"

# 4. Switch to marketing project
engram session resume marketing-campaign

# 5. Run task with different module
engram code "write landing page copy" --module marketing
```

---

### Workflow 5: Quality Tuning

```bash
# 1. Check calibration stats
engram rubric stats coding

# 2. If bias detected, inject corrections
engram score --session abc123 --task 3 --correct 0.95
engram score --session abc123 --task 7 --correct 0.85

# 3. Re-check stats
engram rubric stats coding

# 4. View rubric evolution
engram rubric history coding
```

---

## LEARNING SYSTEM

### How Learning Works

ENGRAM OS learns autonomously through three mechanisms:

#### 1. Prompt Evolution (Every 10 Tasks)

```
Tasks Completed → Analyze Quality → Propose Patch → Evaluate → Apply
      10              ✓               ✓              ✓         ✓
```

**What changes:**
- System prompt instructions
- Task routing patterns
- Convention definitions

**View with:**
```bash
engram learn --history
engram learn --show-patches
```

---

#### 2. Experience Distillation (Every 20 Tasks)

```
Task Completions → Cluster by Type → Critique → Extract Insight → Store
       20                ✓              ✓            ✓           ✓
```

**What's stored:**
- Task type patterns
- Quality differentiators
- Actionable insights

**View with:**
```bash
engram experience stats
```

---

#### 3. Rubric Evolution (Every 50 Tasks)

```
Calibration Log → Analyze Bias → Rewrite Rubric → Backup → Apply
       50              ✓             ✓            ✓       ✓
```

**What changes:**
- Scoring criteria
- Penalty conditions
- Reward conditions

**View with:**
```bash
engram rubric history coding
engram rubric compare coding v1 v2
```

---

### Learning Schedule

| Event | Frequency | Manual Trigger |
|-------|-----------|----------------|
| Prompt Evolution | Every 10 tasks | `engram learn --module coding` |
| Experience Distillation | Every 20 tasks | Automatic |
| Rubric Evolution | Every 50 tasks | Automatic |
| Quality Scoring | Every task | `engram score --correct X.XX` |

---

### Monitoring Learning

```bash
# Check when next learning triggers
engram learn

# View learning history
engram learn --history

# Check experience count
engram experience stats

# View rubric calibration
engram rubric stats coding
```

---

## BEST PRACTICES

### Task Formulation

**DO:**
```bash
# Specific and actionable
engram code "add email validation to signup form"

# Break complex tasks
engram code "read auth.py and list functions"
engram code "add JWT token generation"
engram code "add token verification"

# Include context
engram code "fix the null pointer bug in user_service.py line 45"
```

**DON'T:**
```bash
# Too vague
engram code "fix auth"

# Too complex (break into subtasks)
engram code "build complete authentication system with login, logout, refresh, and password reset"

# Missing context
engram code "fix the bug"
```

---

### Quality Scoring

**When to inject corrections:**
- Score seems too low for good work
- Score seems too high for poor work
- You want to teach system your standards

**How to inject:**
```bash
# Find task in session
engram status

# Inject correction
engram score --session abc123 --task 5 --correct 0.90
```

**Impact:**
- Human corrections weighted 3x
- Affects future scoring calibration
- Helps rubric evolution

---

### Session Management

**Best practices:**
- One session per project
- Name sessions descriptively
- Export important sessions
- Clean up old sessions periodically

```bash
# Good naming
engram init --name my-auth-service

# Export before cleanup
engram session export old-project

# Delete when done
engram session delete old-project
```

---

### Configuration Tuning

**For slower GPUs:**
```bash
engram config set model qwen2.5:14b      # Smaller model
engram config set n_ctx 4096             # Shorter context
```

**For faster GPUs:**
```bash
engram config set model qwen3:30b        # Larger model
engram config set n_ctx 16384            # Longer context
```

**For better responses:**
```bash
engram config set max_tokens 4096        # More output tokens
engram config set min_response_chars 200 # Longer minimum
```

---

## TROUBLESHOOTING

### Common Issues

#### "Ollama not running"

**Symptoms:**
```
✗ Ollama: not running
  → Run: ollama serve
```

**Fix:**
```bash
# Start Ollama
ollama serve

# Verify
curl http://localhost:11434/api/tags
```

---

#### "Model not found"

**Symptoms:**
```
✗ Model: qwen3:30b-a3b-q4_K_M not found
  → Run: ollama pull qwen3:30b-a3b-q4_K_M
```

**Fix:**
```bash
ollama pull qwen3:30b-a3b-q4_K_M
ollama pull all-minilm:l6-v2
```

---

#### "Response too short"

**Symptoms:**
```
[ENGRAM] Response too short (85 chars < 150), retrying...
```

**What it means:**
- LLM returned very short response
- System automatically retried
- May indicate unclear task

**Fix:**
```bash
# Make task more specific
engram code "read auth.py and explain the main authentication flow in detail"
```

---

#### "Learning cycle failed"

**Symptoms:**
```
✗ Learning cycle failed: LLM call failed
```

**Possible causes:**
- Ollama not running
- Model not loaded
- Out of VRAM

**Fix:**
```bash
# Check Ollama
ollama serve

# Check GPU memory
nvidia-smi

# Reduce model size
engram config set model qwen2.5:14b
```

---

#### "Session not found"

**Symptoms:**
```
✗ Session not found: abc123
  → Run: engram init
```

**Fix:**
```bash
# List available sessions
engram session list

# Resume correct session
engram session resume correct-name

# Or create new
engram init
```

---

### Getting Help

```bash
# General help
engram --help

# Command-specific help
engram code --help
engram learn --help

# System health
engram doctor

# Configuration
engram config show
```

---

## CONFIGURATION REFERENCE

### Full Configuration File

**Location:** `~/.engram/config.yaml`

```yaml
# Inference settings
model: qwen3:30b-a3b-q4_K_M
router_model: qwen2.5:7b
ollama_url: http://localhost:11434
lmstudio_url: http://localhost:1234
tool_backend: ollama

# Memory settings
weights_mb: 14000
n_ctx: 8192
scratch_mb: 512

# Learning settings
context_limit: 10
max_tokens: 4096
min_response_chars: 150
max_retries: 2

# Paths
sessions_dir: /home/user/.engram/sessions

# Behavior
default_module: coding
verbose: false
color: true
```

### Changing Configuration

```bash
# View all settings
engram config show

# Change model
engram config set model qwen2.5:14b

# Change context length
engram config set n_ctx 4096

# Reset to defaults
engram config reset
```

---

## APPENDIX

### A. Keyboard Shortcuts

None currently — all interaction via CLI commands.

### B. Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ENGRAM_HOME` | Config directory | `~/.engram` |
| `OLLAMA_URL` | Ollama endpoint | `http://localhost:11434` |

### C. File Structure

```
~/.engram/
├── config.yaml              # Configuration
└── sessions/                # Session files

engram-os/
├── engram/
│   ├── cli/                 # CLI commands
│   ├── core/                # Core engine
│   ├── modules/             # Modules (coding, marketing)
│   └── sessions/            # Local sessions
├── batch2tst/               # Test files (safe to modify)
└── README.md
```

### D. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-03-24 | Initial release |

---

**End of User Guide**

For technical documentation, see:
- `ARCHITECTURE.md` — System architecture
- `README.md` — Project overview
- `docs/` — Detailed documentation
