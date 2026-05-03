User Question: {question}

Frontend Caption (initial audio analysis):
{caption}

Available Tools (only these may be used):
{available_tools}

Based on the question, the caption, and the available tools above, create an initial plan.

**Tool Type Rules:**
- Only suggest tool types from the available tools list above.
- If no tools are available, return an empty list for `possible_tool_types`.
- Do not invent tool types that are not in the available tools list.

Return your response as JSON with this structure:
{{
    "approach": "your high-level strategy",
    "focus_points": ["point 1", "point 2"],
    "possible_tool_types": ["asr", "diarization", "etc"],
    "clarified_intent": "what the user really wants",
    "expected_output_format": "e.g., short answer, list, JSON"
}}
