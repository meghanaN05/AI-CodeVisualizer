# AI Code Visualizer — Frontend

React + Vite frontend for the AI Code Visualizer. Users paste source code, pick
a language, and the app generates an animated Manim video explaining how the
code works.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Environment

| Variable        | Default                | Purpose                        |
| --------------- | ---------------------- | ------------------------------ |
| `VITE_API_URL`  | `http://localhost:8000`| Backend base URL for the API.  |

## API client (`src/api.js`)

- `generateVideo(code, language)` → `POST /generate`, returns `{ video_url, ... }`.
- `parseCode(code, language)` → `POST /parse`, returns analysis metadata.

Relative `video_url` values returned by the backend are prefixed with
`VITE_API_URL` so the video plays correctly.

## Structure

```text
src/
├── App.jsx                  # main UI: editor → generate → player
├── main.jsx
├── api.js                   # backend communication
├── index.css
└── components/
    ├── Header.jsx           # app header
    ├── CodeEditorPanel.jsx  # code input + language selector
    ├── VideoPanel.jsx       # video player + download
    ├── icons.jsx
    └── languages.js         # supported language definitions
```