def generate_manim_code(animation_plan):

    return """
from manim import *


class CodeVisualization(Scene):

    def construct(self):

        title = Text("Code Visualization")

        self.play(Write(title))

        self.wait(2)
"""
