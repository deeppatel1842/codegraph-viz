# codegraph

**Understand any Python codebase in seconds.** One command generates an interactive dependency graph with full source browsing, impact analysis, and 4 layout modes.

---

## The Problem

You join a new team. The codebase has 200+ files across 15 modules. Where do you start?

- Reading file by file takes days
- Architecture docs are outdated or missing
- You change one file and break three others you didn't know existed

## The Solution

```bash
pip install codegraph-viz
cd your-project
codegraph scan
```

Your browser opens with a full interactive map of the entire codebase. Every file. Every dependency. Every function signature. Zero configuration.

---

## What You Get

### Interactive Dependency Graph
A D3.js-powered visualization showing how every file connects to every other file. Click any node to see its imports, dependents, classes, functions, and full source code.

### 4 Layout Modes
Switch between views depending on what you're trying to understand:

| Layout | Best For |
|--------|----------|
| **Force** | Discovering clusters and hidden relationships |
| **Grid** | Understanding module boundaries and file organization |
| **Hierarchy** | Tracing dependency chains top-to-bottom |
| **Radial** | Getting a high-level module overview |

### Impact Analysis
Click any file and instantly see: "If I change this file, which other files are affected?" Color-coded by severity (low/medium/high). Prevents the "I only changed one line" production incidents.

### Inline Source Viewer
Full syntax-highlighted source code, function signatures, class hierarchies, and docstrings — all without leaving the graph. Three tabs: Source, Summary, Dependencies.

### Git History Integration
See who last modified each file, recent commits, and change frequency. Identify hot spots and knowledge silos.

---

## Installation

```bash
pip install codegraph-viz
```

Requires Python 3.11+. No other dependencies.

## Usage

### One-Shot Scan
```bash
codegraph scan                    # Current directory
codegraph scan /path/to/project   # Any project
codegraph scan --no-open          # Generate without opening browser
```

### Live Server (Auto-Reload)
```bash
codegraph serve                   # Watch for changes, auto-regenerate
codegraph serve -p 8080           # Custom port
codegraph serve --interval 10     # Check every 10 seconds
```

### Project Stats
```bash
codegraph info
```
```
==================================================
Project: my-project
==================================================
Files:   147
Lines:   18,432
Edges:   312
==================================================

Modules:
  api                  23 files   4,210 lines  ##################
  core                 18 files   3,891 lines  ################
  models               12 files   1,204 lines  ######
  ...
```

### Export for CI/Agents
```bash
codegraph export > codebase_index.json
codegraph export --compact > codebase_index.json
```

Generates a token-efficient JSON index that AI coding agents can consume to understand your project structure without reading every file.

---

## Token Reduction for LLMs

This is the killer feature for anyone using GPT, Claude, or any LLM to work on their codebase.

**The problem**: To understand a 150-file project, an LLM has to read every file. That's 40,000-80,000 tokens just for context — slow, expensive, and often exceeds context windows.

**The solution**: `codegraph export --compact` produces a single JSON file with:
- Every function signature and type annotation
- Every class with its base classes and method list
- Import dependencies between files
- Impact scores (how many files break if this one changes)
- Module boundaries

**No source code bodies.** Just the architectural skeleton.

| Approach | Tokens | Cost (GPT-4) |
|----------|--------|---------------|
| Feed all raw .py files | ~45,000 | ~$0.90 per query |
| Feed `codegraph export` | ~4,000 | ~$0.08 per query |
| **Reduction** | **~90%** | **~10x cheaper** |

The LLM reads the index once, understands the full architecture, then only requests the specific file it needs to edit. Instead of paying for 45K tokens of context every message, you pay for 4K.

```bash
# Generate the index
codegraph export --compact > codebase_index.json

# Feed to your LLM
# "Here is the project structure: <contents of codebase_index.json>"
# "Now read src/agents/planner.py and fix the bug in plan_task()"
```

---

## How It Helps

### For New Engineers
Stop spending the first two weeks just figuring out what calls what. Open the graph, switch to Hierarchy mode, trace from entry points to database calls. Understand the architecture in an afternoon.

### For Tech Leads
Run `codegraph info` in CI. Track module growth, identify files with high impact scores (change one, break many), and catch architecture violations before they ship.

### For Code Reviews
Before approving a PR that touches `config/settings.py`, check its impact analysis. If 40 files depend on it, that's a different review than if 2 files depend on it.

### For AI-Assisted Development
Export the index and feed it to your AI coding agent. Instead of the agent burning 45K tokens reading 200 files, it reads a 4K-token JSON index and understands the entire architecture instantly. Then it only fetches the one file it needs to edit. 90% fewer tokens, 10x cheaper.

---

## What Users Get After `pip install`

When someone runs `pip install codegraph-viz`, they get:
- The `codegraph` command in their terminal
- That's it. No source files in their project folder.

The package installs into Python's internal `site-packages` directory (hidden away from the user's workspace). Users interact with it purely through the CLI commands. They cannot modify the package code. The source code lives on GitHub for transparency and contributions — users who want to contribute can fork the repo and submit pull requests.

---

## How It Works

1. **AST Parsing** — Walks every `.py` file, extracts classes, functions, signatures, docstrings, and imports using Python's `ast` module
2. **Import Resolution** — Maps `from src.agents.base import BaseAgent` to the actual file path
3. **Graph Construction** — Builds a directed dependency graph with module detection
4. **Impact Analysis** — Computes transitive closure: "if X changes, what else breaks?"
5. **Git Integration** — Reads commit history per file for change frequency and authorship
6. **Visualization** — Generates a self-contained HTML file (no server required) with embedded D3.js

The output is a single `.html` file. No server. No database. No accounts. Just open it.

---

## Architecture

```
codegraph/
    __init__.py      # Package version
    __main__.py      # python -m codegraph
    cli.py           # Argument parsing, commands
    scanner.py       # AST analysis, graph building, import resolution
    server.py        # HTTP server with file watching
    templates/
        graph.html   # D3.js visualization template
```

~1,200 lines of Python. Zero runtime dependencies beyond the standard library.

---

## License

MIT
