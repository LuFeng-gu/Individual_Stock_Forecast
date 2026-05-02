Question: {question}

Frontend Caption: {frontend_caption}

Initial Plan: {initial_plan}

Evidence Log ({evidence_count} items):
{evidence_log}

Tool Call History ({tool_call_count} items):
{tool_call_history}

Available Tools:
{available_tools}

Step: {step_count} / {max_steps}

Based on the above, decide the next action.

Return your response as JSON with this structure:
{{
    "action": "answer" | "call_tool" | "fail",
    "rationale": "why you chose this action",
    "selected_tool_name": "tool name if action is call_tool",
    "selected_audio_id": "audio_0 if action is call_tool",
    "draft_answer": "your draft answer if action is answer"
}}

Rules:
- If action is "call_tool", you MUST provide selected_tool_name and selected_audio_id
- If action is "answer", provide a draft_answer
- If action is "fail", explain why in rationale
