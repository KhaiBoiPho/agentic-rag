"""Node 4 — Quality gate: assess if aggregated content is sufficient.

Returns quality_passed=True (continue to Node 5) or False (loop back to Node 1).
"""

from __future__ import annotations

import json

from app.core.llm.openrouter import OpenRouterClient
from app.core.research.state import ResearchState

_llm = OpenRouterClient()

QUALITY_PROMPT = """\
You are a research quality evaluator. Given a question and collected research content,
assess whether the content is sufficient to provide a comprehensive answer.

Question: {query}

Collected content (excerpt):
{content_excerpt}

Evaluate on a scale of 0.0-1.0 and respond in JSON only:
{{
  "score": 0.85,
  "passed": true,
  "feedback": "The content covers main aspects but lacks recent data."
}}

Threshold for passing: {threshold}
"""


async def quality_checker_node(state: ResearchState) -> dict:
    query = state["original_query"]
    aggregated = state.get("aggregated_text", "")
    threshold = state["config"].get("quality_threshold", 0.75)
    current_iter = state.get("iteration", 0)
    max_iter = state["config"].get("max_iterations", 3)

    # If we've hit max iterations, force pass to avoid infinite loop
    if current_iter >= max_iter:
        return {
            "quality_passed": True,
            "quality_score": threshold,
            "quality_feedback": "Max iterations reached, proceeding.",
            "events": [
                {
                    "node": "quality_checker",
                    "status": "completed",
                    "content": "Max iterations reached",
                    "progress": 0.6,
                    "iteration": current_iter,
                }
            ],
        }

    excerpt = aggregated[:4000]
    prompt = QUALITY_PROMPT.format(query=query, content_excerpt=excerpt, threshold=threshold)

    try:
        response = await _llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        start = response.find("{")
        end = response.rfind("}") + 1
        result = json.loads(response[start:end]) if start >= 0 else {}
        score = float(result.get("score", 0.5))
        passed = bool(result.get("passed", score >= threshold))
        feedback = result.get("feedback", "")
    except Exception:
        score = 0.5
        passed = current_iter >= 1  # pass on second attempt
        feedback = "Evaluation failed, proceeding."

    return {
        "quality_passed": passed,
        "quality_score": score,
        "quality_feedback": feedback,
        "iteration": current_iter + 1,
        "events": [
            {
                "node": "quality_checker",
                "status": "completed",
                "content": f"Điểm {score:.2f}" + (f" — {feedback}" if feedback else ""),
                "progress": 0.6,
                "iteration": current_iter,
            }
        ],
    }
