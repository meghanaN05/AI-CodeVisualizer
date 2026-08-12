from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from parser import parse_code
from ai import generate_animation_plan
from manim_generator import generate_manim_code
from renderer import render_video


app = FastAPI(title="AI Code Visualizer")


# Allow React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str
    language: str


@app.get("/")
def home():
    return {
        "message": "AI Code Visualizer Backend is running"
    }


@app.post("/generate")
def generate(request: CodeRequest):

    # Step 1: Parse code
    parsed_code = parse_code(
        request.code,
        request.language
    )

    # Step 2: Generate animation plan using AI
    animation_plan = generate_animation_plan(
        parsed_code
    )

    # Step 3: Convert animation plan to Manim code
    manim_code = generate_manim_code(
        animation_plan
    )

    # Step 4: Render Manim code into video
    video_url = render_video(
        manim_code
    )

    return {
        "success": True,
        "video_url": video_url
    }
