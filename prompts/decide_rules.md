Decision Rules:

1. If you have direct evidence that fully answers the question, use action='answer'.
2. If you need more information (transcription, speaker info, etc.), use action='call_tool' with the most relevant tool.
3. If the question is unclear even after clarification, use action='fail'.
4. Do not call the same tool twice with the same parameters unless new evidence justifies it.
5. On the final step (step_count >= max_steps - 1), you MUST use action='answer'.
6. If a tool previously failed, consider trying a different tool or approach.
