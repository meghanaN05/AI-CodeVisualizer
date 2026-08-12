# AI Code Visualizer

An AI-powered application that converts source code into animated visualizations and videos using **LLMs + program analysis + Manim**.

The goal is to help students understand the execution and working of **data structures, algorithms, graphs, trees, recursion, sorting algorithms, and other programming concepts** through visual animations instead of only reading code.

---

## 🚀 Project Overview

Traditional code explanations are mostly text-based. This project takes a different approach:

```text
Source Code
     ↓
Language Detection
     ↓
Code Parsing
     ↓
Intermediate Representation
     ↓
AI Analysis
     ↓
Animation Plan
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

The current MVP uses a deliberately minimal structure:

```text
AI-CodeVisualizer/
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── api.js
│   │   └── index.css
│   └── package.json
│
├── backend/
│   ├── app.py
│   ├── parser.py
│   ├── ai.py
│   ├── manim_generator.py
│   ├── renderer.py
│   └── requirements.txt
│
├── uploads/
├── outputs/
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
├── parser.py
├── ai.py
├── manim_generator.py
├── renderer.py
└── requirements.txt
```

---

## `app.py`

Main FastAPI application.

It exposes:

```text
GET  /
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

## `parser.py`

Responsible for analyzing the submitted source code.

Current MVP implementation provides a simple intermediate representation.

Future implementation will use proper parsers such as:

- Tree-sitter
- Python AST
- Clang AST
- JavaParser
- Babel Parser

---

## `ai.py`

Responsible for AI-based code understanding.

The planned pipeline is:

```text
Parsed Code
     ↓
Prompt Construction
     ↓
LLM
     ↓
Animation JSON
```

The LLM should produce structured JSON rather than directly producing arbitrary Manim code.

This makes the system easier to validate and safer to execute.

---

## `manim_generator.py`

Converts the animation plan into Manim code.

Example:

```text
Animation JSON
      ↓
Manim Generator
      ↓
Python Script
```

---

## `renderer.py`

Responsible for running Manim and generating the final video.

Eventually it will execute something similar to:

```bash
manim -pqh generated_scene.py SceneName
```

The generated `.mp4` file will then be returned to the frontend.

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

The system is designed to eventually support:

### Trees

- Binary Tree
- Binary Search Tree
- AVL Tree
- Heap
- Trie
- Segment Tree

### Graphs

- BFS
- DFS
- Dijkstra
- Bellman-Ford
- Floyd-Warshall
- Prim's Algorithm
- Kruskal's Algorithm

### Sorting

- Bubble Sort
- Selection Sort
- Insertion Sort
- Merge Sort
- Quick Sort
- Heap Sort

### Data Structures

- Array
- Linked List
- Stack
- Queue
- Deque
- Hash Table
- Heap

### Other Algorithms

- Recursion
- Backtracking
- Dynamic Programming
- Searching
- Greedy Algorithms

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
  "video_url": "http://localhost:8000/videos/output.mp4"
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
- [ ] Real parser
- [ ] Manim rendering

## Phase 2 — Code Understanding

- [ ] AST generation
- [ ] Control Flow Graph
- [ ] Intermediate Representation
- [ ] Algorithm detection
- [ ] Variable extraction

## Phase 3 — AI

- [ ] LLM integration
- [ ] Prompt engineering
- [ ] Animation JSON
- [ ] JSON validation
- [ ] Scene planning

## Phase 4 — Visualization

- [ ] Array visualization
- [ ] Tree visualization
- [ ] Graph visualization
- [ ] Linked List visualization
- [ ] Sorting visualization
- [ ] Recursion visualization

## Phase 5 — Video Generation

- [ ] Dynamic Manim generation
- [ ] Manim rendering
- [ ] MP4 generation
- [ ] Video preview
- [ ] Video download

## Phase 6 — Deployment

- [ ] Dockerize backend
- [ ] Deploy frontend
- [ ] Deploy backend
- [ ] Cloud storage
- [ ] Background workers
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
