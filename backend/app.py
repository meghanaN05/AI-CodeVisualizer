from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import jobs
from analyzer import analyze
from manim_generator import generate_manim_code
from pipeline import build_visualization_plan
from renderer import render_video

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "outputs"
VIDEOS_DIR = OUTPUT_DIR / "videos"

app = FastAPI(title="AI Code Visualizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")


class CodeRequest(BaseModel):
    code: str
    language: str


@app.get("/")
def home():
    return {"message": "AI Code Visualizer Backend is running"}


@app.post("/parse")
def parse(request: CodeRequest):
    parsed_code = analyze(request.code, request.language)
    animation_plan = build_visualization_plan(request.code, request.language)
    return {
        "success": True,
        "ir": parsed_code,
        "classification": parsed_code.get("classification"),
        "complexity": parsed_code.get("complexity"),
        "animation_plan": animation_plan,
    }


@app.post("/generate", status_code=202)
def generate(request: CodeRequest):
    """Start rendering in the background; poll GET /jobs/{job_id} for the result."""
    code, language = request.code, request.language

    def work(report):
        animation_plan = build_visualization_plan(code, language, report)
        report("rendering")
        video_url = render_video(generate_manim_code(animation_plan))
        return {
            "video_url": video_url,
            "algorithm": animation_plan.get("algorithm"),
            "title": animation_plan.get("title"),
            "data_structure": animation_plan.get("data_structure"),
            "scene_count": len(animation_plan.get("scenes") or []),
        }

    job = jobs.submit(work)
    return {"job_id": job["id"], "status": job["status"]}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id")
    return {
        "job_id": job["id"],
        "status": job["status"],
        "result": job["result"],
        "error": job["error"],
    }
