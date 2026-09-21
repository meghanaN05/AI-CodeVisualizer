# AI Code Visualizer
An AI-powered application that converts source code into animated visualizations and videos using **LLMs + program analysis + Manim**.

The goal is to help students understand the execution and working of **data structures, algorithms, graphs, trees, recursion, sorting algorithms, and other programming concepts** through visual animations instead of only reading code.
## 🚀 Project Overview

Traditional code explanations are mostly text-based. This project takes a different approach:

```text
Source Code
     ↓
Language Detection
     ↓
Code Parsing (AST-based IR)
     ↓
Enrich IR (extract real arrays/graphs/trees, detect algorithm)
     ↓
Classify Input (graph | tree | system-design | array | generic)
     ↓
Plan (Visualization DSL) — Layout Engine computes coordinates
     ↓
Manim Code Generation
     ↓
Video Rendering
     ↓
Animated Visualization
```

The user uploads or enters code, and the system analyzes the code and generates an educational animation showing how the code works step by step.

---

## 🎯 Objectives

- Visualize the execution of source code.
- Make algorithms and data structures easier to understand.
- Generate animations automatically using AI.
- Show step-by-step changes in variables and data structures.
- Visualize trees, graphs, arrays, linked lists, stacks, queues, and other structures.
- Generate downloadable educational videos.
- Provide an interactive web-based interface.
- Support multiple programming languages.

---

## ✨ Features

### 1. Code Input

Users can enter or paste source code into the browser.

Currently planned languages:

- C++
- Python
- Java
- JavaScript

---

### 2. Automatic Code Analysis

The backend analyzes the submitted code and extracts useful information such as:

- Functions
- Variables
- Loops
- Conditions
- Recursion
- Data structures
- Control flow
- Function calls

---

### 3. AI-Based Understanding

An LLM analyzes the structured representation of the program and determines:

- What the code is doing
- Which algorithm is being used
- Which data structures are involved
- What execution steps should be visualized
- Which nodes/elements should be highlighted
- What transitions should be animated

---

### 4. Animation Generation

The AI generates a structured animation plan instead of directly generating a video.

Example:

```json
{
  "scene": 1,
  "action": "highlight",
  "node": 10
}
```

This animation plan is converted into **Manim code**.

---

### 5. Manim Rendering

Manim is used as the animation engine.

```text
Animation JSON
      ↓
Manim Generator
      ↓
Python/Manim Code
      ↓
Manim Renderer
      ↓
MP4 Video
```

---

### 6. Video Visualization

The generated video can be played directly in the browser.

Users can:

- Play
- Pause
- Seek
- Change playback speed
- Download the generated video

---

# 🏗️ System Architecture

```text
                    ┌─────────────────────┐
                    │      React UI       │
                    │                     │
                    │  Code Editor        │
                    │  Language Selector  │
                    │  Video Player       │
                    └──────────┬──────────┘
                               │
                               │ HTTP
                               ▼
                    ┌─────────────────────┐
                    │     FastAPI         │
                    │      Backend        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Code Parser      │
                    │                     │
                    │ AST / CFG / IR      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    AI / LLM         │
                    │                     │
                    │ Scene Generation    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Manim Code Generator│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Manim Renderer    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      MP4 Video      │
                    └──────────┬──────────┘
                               │
                               ▼
                         React Player
```

---

# 📂 Project Structure

```text
AI-CodeVisualizer/
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── api.js
│   │   ├── components/
│   │   │   ├── Header.jsx
│   │   │   ├── CodeEditorPanel.jsx
│   │   │   ├── VideoPanel.jsx
│   │   │   ├── icons.jsx
│   │   │   └── languages.js
│   │   └── index.css
│   └── package.json
│
├── backend/
│   ├── app.py                 # FastAPI routes
│   ├── pipeline.py            # analyze → classify → plan
│   ├── analyzer.py            # semantic analyzer (classification, complexity)
│   ├── classifier.py          # domain classification
│   ├── parser.py              # entrypoint → AST parsers
│   ├── python_parser.py       # Python AST parser
│   ├── cpp_parser.py          # C++ (tree-sitter / fallback)
│   ├── java_parser.py         # Java (tree-sitter / fallback)
│   ├── javascript_parser.py   # JavaScript (tree-sitter / fallback)
│   ├── ts_parser.py           # shared tree-sitter helper
│   ├── graph_extractor.py     # real graph data extraction
│   ├── tree_extractor.py      # real tree data extraction
│   ├── ir_analysis.py         # algorithm/data-structure detection
│   ├── ai.py                  # optional LLM planner (fallback = rule-based)
│   ├── animation_planner.py   # legacy rule-based planner
│   ├── animation_schema.py    # legacy plan schema
│   ├── manim_generator.py     # plan → Manim code
│   ├── renderer.py            # Manim → MP4
│   ├── visualization/         # DSL + layout engine
│   │   ├── schema.py          # VisualizationDocument / DslStep DSL
│   │   ├── graph.py           # Dijkstra / BFS / DFS planners
│   │   ├── tree.py            # inorder/preorder/postorder planners
│   │   ├── system_design.py   # Twitter architecture planner
│   │   ├── layout.py          # collision-free Node/Graph/Architecture layout
│   │   ├── complexity.py      # scene/effort estimator
│   │   ├── validator.py       # DSL validation
│   │   └── __init__.py
│   └── requirements.txt
│
├── outputs/
│   ├── videos/                # generated MP4s (served at /videos)
│   ├── scenes/                # generated Manim scripts
│   └── media/                 # Manim render cache
│
├── Dockerfile
└── README.md
```

---

# 🖥️ Frontend

The frontend is built using:

- React
- Vite
- JavaScript
- CSS

### Responsibilities

The frontend handles:

1. Code input
2. Language selection
3. API requests
4. Loading state
5. Video playback
6. Video download

### Main files

```text
frontend/src/

App.jsx
main.jsx
api.js
index.css
```

### `App.jsx`

Contains the main user interface.

It provides:

- Code editor
- Language selector
- Generate button
- Loading indicator
- Video player
- Download button

### `api.js`

Handles communication with the FastAPI backend.

Example:

```javascript
fetch("http://localhost:8000/generate", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    code,
    language,
  }),
});
```

---

# ⚙️ Backend

The backend is built using **FastAPI**.

Current architecture:

```text
backend/
│
├── app.py
├── pipeline.py
├── analyzer.py
├── classifier.py
├── parser.py
├── graph_extractor.py
├── tree_extractor.py
├── ir_analysis.py
├── ai.py
├── animation_planner.py
├── manim_generator.py
├── renderer.py
├── visualization/
└── requirements.txt
```

---

## `app.py`

Main FastAPI application.

It exposes:

```text
GET  /
POST /parse
POST /generate
```

The `/generate` endpoint receives:

```json
{
  "code": "source code",
  "language": "cpp"
}
```

and sends it through the visualization pipeline.

---

## `pipeline.py`

The unified planning pipeline. It wires the analysis layer into the planners:

```text
analyzer.analyze()          → enriched IR (classification, graph, complexity)
classifier domain           → graph | tree | system_design | fallback
visualization.* planners    → VisualizationDocument (DSL)
layout.apply_layout()       → collision-free coordinates
validator.validate_document → DSL sanity checks
manim_generator             → Manim code
```

Graphs, trees, and system-design inputs are routed through the deterministic
DSL agents in `visualization/`. Everything else (sorts, recursion, hash maps,
generic code) falls back to the legacy rule-based planner in
`animation_planner.py`.

---

## `parser.py`

Responsible for analyzing the submitted source code using real AST parsers:

- Python: built-in `ast`
- C++: tree-sitter (or text fallback)
- Java / JavaScript: tree-sitter

Each parse produces a language-neutral IR that is then enriched with:

- Real array literals (`arrays`)
- Extracted graph (`extracted_graph`, via `graph_extractor.py`)
- Extracted tree (`extracted_tree`, via `tree_extractor.py`)
- Detected algorithm / data structures (via `ir_analysis.py`)

---

## `classifier.py`

Classifies input into one of five domains:

- `graph` — Dijkstra, BFS, DFS constructions
- `tree` — BST/traversal code
- `system_design` — Twitter / architecture-style prompts
- `array` — sorting, binary search
- `generic` — fallback

---

## `analyzer.py`

Semantic analyzer combining parsing, classification, graph extraction, and
complexity estimation into a single enriched IR.

---

## `ai.py`

Optional LLM-driven planner. When `OPENAI_API_KEY` is set, the LLM decides the
approach and emits a structured, validated animation plan. Without a key (or
on any LLM failure) the system deterministically falls back to the rule-based
planner, so the pipeline never depends on network access.

The LLM plans WHAT to show; the deterministic layout engine decides WHERE to
place objects, and `manim_generator.py` decides HOW to animate.

---

## `visualization/`

The deterministic DSL package (`VisualizationDocument` / `DslStep`):

- `graph.py`    — Dijkstra, BFS, DFS planners (run on the real extracted graph)
- `tree.py`     — inorder/preorder/postorder traversal planners
- `system_design.py` — Twitter-style architecture chapters
- `layout.py`   — collision-detection layout engine (NetworkX + reflow) that
  fills coordinates; the planner never emits coordinates itself
- `complexity.py` — estimates scene count so large problems become chapters
- `validator.py` — rejects unsupported DSL actions before rendering
- `schema.py`   — contract between planner and renderer

---

## `manim_generator.py`

Converts the animation plan into Manim code.

Supports array, tree, graph, heap, hash-map, stack, recursion, shortest-path,
and architecture scenes. Object cleanup is keyed to the mobjects actually
added to the scene, so re-rendered arrays/graphs/heaps replace rather than
stack.

---

## `renderer.py`

Responsible for running Manim and generating the final video.

```bash
manim -ql --disable_caching scene.py CodeVisualization
```

The generated `.mp4` file is copied into `outputs/videos/` and served at
`/videos/<scene_id>.mp4`.

---

# 🧠 AI Architecture

The AI component should not directly transform arbitrary source code into a video.

Instead, use an intermediate representation:

```text
Source Code
     ↓
Parser
     ↓
AST / CFG
     ↓
Intermediate Representation
     ↓
LLM
     ↓
Animation JSON
     ↓
Manim
```

This reduces hallucinations and makes the generated animations more deterministic.

---

# 🔄 Example Workflow

Suppose the user enters:

```cpp
void inorder(Node* root) {

    if(root == NULL)
        return;

    inorder(root->left);

    cout << root->data;

    inorder(root->right);
}
```

The system should identify:

```text
Algorithm:
Inorder Traversal

Data Structure:
Binary Tree

Important concepts:
- Recursion
- Left subtree
- Root
- Right subtree
```

The AI then generates an animation plan:

```text
1. Display binary tree
2. Highlight root
3. Move to left child
4. Continue recursively
5. Highlight visited node
6. Return to parent
7. Move to right child
8. Continue until traversal is complete
```

Manim converts this into an animation.

Final result:

```text
Binary Tree
     ↓
Node Highlighting
     ↓
Traversal Animation
     ↓
Step-by-Step Video
```

---

# 🌳 Supported Visualizations

### Implemented (real data extracted from your code)

- Array traversal & sorting: Bubble, Selection, Insertion, Merge, Quick, Binary Search
- Trees: Inorder / Preorder / Postorder traversals (uses your tree when extractable)
- Graphs: BFS, DFS, Dijkstra's shortest path (uses your graph when extractable)
- Recursion: call-stack push/pop visualization
- Hash map: insert / lookup
- Heap: push / pop on a priority queue
- System design: Twitter architecture (requirements, write path, fanout, timeline, scaling)
- Object-oriented designs: class + methods overview that composes the above structures

### Planned

- Linked List
- Tries, Union-Find, LRU Cache (currently illustrative outlines)
- Dynamic Programming tables (currently illustrative)
- AVL / Red-Black / Segment trees
- Prim's / Kruskal's algorithms
- Backtracking
- Bellman-Ford / Floyd-Warshall
- Heap Sort / Counting Sort

---

# 🛠️ Technology Stack

| Component         | Technology        |
| ----------------- | ----------------- |
| Frontend          | React             |
| Build Tool        | Vite              |
| Frontend Language | JavaScript        |
| Backend           | FastAPI           |
| Backend Language  | Python            |
| AI                | LLM               |
| Code Parsing      | AST / Tree-sitter |
| Animation         | Manim             |
| Video             | MP4               |
| API               | REST              |
| Containerization  | Docker            |
| Version Control   | Git               |
| Repository        | GitHub            |

---

# 🚀 Installation

## Prerequisites

Install:

- Node.js
- npm
- Python 3.10+
- Git
- Manim
- FFmpeg

---

# Frontend Setup

Navigate to the frontend:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

Frontend:

```text
http://localhost:5173
```

---

# Backend Setup

Navigate to the backend:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start FastAPI:

```bash
uvicorn app:app --reload
```

Backend:

```text
http://localhost:8000
```

---

# 🔌 API

## Health Check

```http
GET /
```

Response:

```json
{
  "message": "AI Code Visualizer Backend is running"
}
```

---

## Parse (Analysis)

```http
POST /parse
```

Request:

```json
{
  "code": "def inorder(root):\n    if not root: return\n    inorder(root.left)\n    ...",
  "language": "python"
}
```

Response includes the enriched IR, classification, complexity estimate, and
the animation plan.

## Generate Visualization

```http
POST /generate
```

Request:

```json
{
  "code": "int main() { return 0; }",
  "language": "cpp"
}
```

Response:

```json
{
  "success": true,
  "video_url": "http://localhost:8000/videos/output.mp4",
  "algorithm": "code_analysis",
  "title": "Code Visualization",
  "data_structure": null,
  "classification": "array",
  "complexity": { "scenes_required": 2, "complexity": "low" }
}
```

---

# 🔐 Security Considerations

Generated code must **never be executed directly on the main backend server**.

Because users can submit arbitrary code, the production system should execute:

- Parser
- LLM-generated code
- Manim
- FFmpeg

inside isolated Docker containers or sandboxed workers.

Recommended restrictions:

- CPU limits
- Memory limits
- Execution timeout
- No unnecessary network access
- Read-only filesystem where possible
- Temporary working directories
- Restricted subprocess permissions

---

# 📈 Future Production Architecture

The MVP can later be expanded into:

```text
                    React
                      │
                      ▼
                FastAPI API
                      │
                      ▼
                Redis Queue
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
     Parser Worker           AI Worker
                                  │
                                  ▼
                         Animation Planner
                                  │
                                  ▼
                           Render Worker
                                  │
                                  ▼
                               Manim
                                  │
                                  ▼
                              AWS S3
                                  │
                                  ▼
                             Video URL
```

This allows expensive video rendering to happen asynchronously without blocking the API.

---

# 🧪 Development Roadmap

## Phase 1 — Basic MVP

- [x] React frontend
- [x] FastAPI backend
- [x] Code input
- [x] Language selection
- [x] API communication
- [x] Real parser (Python AST, tree-sitter for C++/Java/JS)
- [x] Manim rendering

## Phase 2 — Code Understanding

- [x] AST generation
- [x] Intermediate Representation
- [x] Algorithm detection
- [x] Variable extraction
- [x] Array literal extraction
- [x] Graph extraction (`graph_extractor`)
- [x] Tree extraction (`tree_extractor`)
- [ ] Control Flow Graph / execution trace

## Phase 3 — AI

- [x] LLM integration (optional, with rule-based fallback)
- [x] Prompt engineering
- [x] Animation JSON / DSL
- [x] JSON validation
- [x] Scene planning
- [ ] Phase E: true execution trace / line-level stepping

## Phase 4 — Visualization

- [x] Array visualization
- [x] Tree visualization (inorder/preorder/postorder)
- [x] Graph visualization (Dijkstra, BFS, DFS)
- [x] Sorting visualization (bubble/selection/insertion/merge/quick)
- [x] Recursion visualization
- [x] Hash map visualization
- [x] Heap / priority-queue visualization
- [x] System-design architecture visualization (Twitter)
- [x] Collision-free layout engine (`visualization/layout.py`)
- [ ] Linked List visualization
- [ ] Trie / Union-Find / LRU / DP (source-bound, not just illustrative)
- [ ] AVL / Red-Black / segment tree
- [ ] Prim / Kruskal

## Phase 5 — Video Generation

- [x] Dynamic Manim generation
- [x] Manim rendering
- [x] MP4 generation
- [x] Video preview
- [x] Video download

## Phase 6 — Deployment

- [x] Dockerize backend
- [ ] Deploy frontend
- [ ] Deploy backend
- [ ] Cloud storage (S3)
- [ ] Background workers (Celery/Redis)
- [ ] Redis queue
- [ ] Production monitoring

---

# 🔮 Future Features

- Voice narration
- Automatic subtitles
- Interactive step-by-step playback
- Variable state visualization
- Execution timeline
- Multiple animation themes
- User accounts
- Visualization history
- Custom test cases
- Interactive quizzes
- Algorithm recommendations
- AI-generated explanations
- Support for more programming languages

---

# 🎓 Educational Use Case

The application is primarily designed for students learning:

- Data Structures
- Algorithms
- Programming
- Recursion
- Graph Theory
- Tree Algorithms
- Competitive Programming

Instead of asking:

> "What does this code do?"

the student can see:

```text
Code
 ↓
Execution
 ↓
State Changes
 ↓
Animation
 ↓
Understanding
```

---

# 💡 Why This Project?

Most AI coding assistants explain code using text.

This project focuses on **visual understanding**.

Instead of only producing:

```text
"The algorithm traverses the left subtree first..."
```

the system produces an animation showing:

```text
        10
       /  \
      5    20
     / \
    3   7

     ↓

10 → 5 → 3 → 5 → 7 → 10 → 20
```

This makes abstract algorithms easier to understand and remember.

---

# 👩‍💻 Author

**Meghana N**

AI Code Visualizer — An AI-powered platform for converting source code into educational algorithm visualizations.

---

# 📄 License

This project is intended for educational and research purposes.
