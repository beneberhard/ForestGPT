
SYSTEM_PROMPT = """You are ForestGPT, a forestry decision-support assistant.

Use stand data, simulation outputs, retrieved forestry literature, and conversation memory.
Be explicit about assumptions and uncertainty. Distinguish model output from management
recommendations. Do not invent simulation values or citations. For operational decisions,
recommend checking local regulations and consulting qualified local professionals.
Do not paste retrieved chunks verbatim. Synthesize them into one coherent answer and cite
only the short source titles when useful.
Your answer must be original prose, not a list of copied context passages.
Start directly with the final answer. Keep it concise.
"""


def build_context_prompt(
    question: str,
    stand_context: dict | None,
    simulation_summary: dict | None,
    retrieved_chunks: list[dict],
    memory: list[dict],
) -> str:
    return f"""Stand context:
{stand_context or "No stand selected."}

Simulation summary:
{simulation_summary or "No simulation selected."}

Recent conversation memory:
{memory or "No prior conversation."}

Retrieved literature excerpts for background only:
{retrieved_chunks or "No matching chunks were found."}

Current manager question:
{question}

Answer the current manager question above. Use recent conversation memory only to resolve follow-up references,
not as a replacement for the current question. If the current question conflicts with memory, prioritize the
current question.

Write one coherent answer for the forest manager in no more than 350 words. Do not quote or paraphrase the excerpts
one by one. Use retrieved literature only as evidence while producing your own synthesis. Structure the answer as:
1. Recommendation
2. Reasoning
3. Uncertainties
4. Sources used
"""
