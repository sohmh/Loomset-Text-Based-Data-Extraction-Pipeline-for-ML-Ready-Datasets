from ollama import chat
import json

MODEL = "elenchus"

mode = "SOCRATIC"
messages = []

print("Elenchus is ready.")
print("Mode: SOCRATIC")
print("Commands: /direct, /socratic, /exit\n")


def get_response(user_input):
    if mode == "SOCRATIC":
        instruction = """
You are operating in SOCRATIC mode.

Return ONLY valid JSON with exactly these fields:

{
  "type": "question" | "hint" | "explanation",
  "content": "your response"
}

Rules:
- Ask exactly one meaningful question when possible.
- Do not give the complete solution.
- Do not provide the requested formula, code, or final answer.
- If the user is stuck, provide a small conceptual hint.
- Keep the response concise.
"""
    else:
        instruction = """
You are operating in DIRECT mode.

Return ONLY valid JSON with exactly these fields:

{
  "type": "answer",
  "content": "your response"
}

Direct answers, explanations, formulas, and code are allowed.
"""

    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": instruction
            },
            *messages
        ],
        think=False
    )

    return response.message.content


while True:

    user_input = input("You: ").strip()

    if user_input.lower() == "/exit":
        break

    if user_input.lower() == "/direct":
        mode = "DIRECT"
        print("\n[Mode changed to DIRECT]\n")
        continue

    if user_input.lower() == "/socratic":
        mode = "SOCRATIC"
        print("\n[Mode changed to SOCRATIC]\n")
        continue

    messages.append({
        "role": "user",
        "content": user_input
    })

    raw_response = get_response(user_input)

    try:
        response = json.loads(raw_response)

        response_type = response["type"]
        content = response["content"]

        allowed_types = {
            "SOCRATIC": ["question", "hint", "explanation"],
            "DIRECT": ["answer"]
        }

        if response_type not in allowed_types[mode]:
            print("\nElenchus produced an invalid response type.")
            print("Please try again.\n")
            continue

        print(f"\nElenchus: {content}\n")

        messages.append({
            "role": "assistant",
            "content": content
        })

    except (json.JSONDecodeError, KeyError):
        print("\nElenchus returned an invalid response format.")
        print("Please try again.\n")