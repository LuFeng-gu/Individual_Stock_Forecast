User Question: {question}

Frontend Caption (initial audio analysis):
{caption}

Based on the question and the caption above, create an initial plan.

Return your response as JSON with this structure:
{{
    "approach": "your high-level strategy",
    "focus_points": ["point 1", "point 2"],
    "possible_tool_types": ["asr", "diarization", "etc"],
    "clarified_intent": "what the user really wants",
    "expected_output_format": "e.g., short answer, list, JSON"
}}
