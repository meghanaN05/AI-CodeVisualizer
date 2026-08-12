from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai import generate_animation_plan
from manim_generator import generate_manim_code
from parser import parse_code
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
    parsed_code = parse_code(request.code, request.language)
    animation_plan = generate_animation_plan(parsed_code)
    return {
        "success": True,
        "ir": parsed_code,
        "animation_plan": animation_plan,
    }


@app.post("/generate")
def generate(request: CodeRequest):
    try:
        parsed_code = parse_code(request.code, request.language)
        animation_plan = generate_animation_plan(parsed_code)
        manim_code = generate_manim_code(animation_plan)
        video_url = render_video(manim_code)

        return {
            "success": True,
            "video_url": video_url,
            "algorithm": animation_plan.get("algorithm"),
            "title": animation_plan.get("title"),
            "data_structure": animation_plan.get("data_structure"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
