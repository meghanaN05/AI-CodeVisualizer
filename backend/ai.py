def generate_animation_plan(parsed_code):

    return {
        "type": "code",
        "language": parsed_code["language"],
        "source": parsed_code["source_code"],
        "scenes": [
            {
                "type": "text",
                "content": "Code visualization started"
            }
        ]
    }
