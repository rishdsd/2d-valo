
import json
import urllib.request
import urllib.error
import time


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:2b"




SYSTEM_PROMPT = """
You are the tactical planner for a bot in a 2D shooter.

Choose exactly one action from available_actions.

Actions:
- attack: use the existing normal combat behavior.
- cover_peek: repeatedly move behind nearby cover, briefly peek
  toward the enemy, shoot when visible, and return to cover.

Decision policy:
- Above 50% health, generally attack.
- At or below 50% health, prefer cover_peek when an enemy exists.
- Do not choose cover_peek merely because an enemy is not visible.
- Never invent actions or battlefield information.
- The Python game engine handles all movement, aiming, and shooting.

Return only valid JSON:
{"action": "attack", "target_id": null, "reason": "brief reason"}
"""



def choose_tactical_action(observation, timeout=8):
    """
    Choose exactly one action from available_actions.
    Return JSON with this structure:
    {"action": "attack", "target_id": null, "reason": "brief explanation"}

    Choose retreat when health is critically low or the fight is
    unfavorable. Otherwise, attack when an enemy is a viable target.
    Never invent actions that are not in available_actions.
    """
    available_actions = observation.get("available_actions", [])

    if not available_actions:
        return None

    prompt = (
        "Battlefield observation:\n"
        + json.dumps(observation)
    )

    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Battlefield observation:\n"
                + json.dumps(observation),
            },
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": 64,
        },
    }


    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    
    started_at = time.monotonic()
    print(
        f"[Ollama] Requesting decision | "
        f"HP={observation.get('bot_hp')} | "
        f"Actions={available_actions}",
        flush=True,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result.get("message", {}).get("content", "")
        decision = json.loads(content)

        action = decision.get("action")

        if action not in available_actions:
            print(
                f"[Ollama] Invalid action={action!r} | "
                f"Allowed={available_actions}",
                flush=True,
            )
            return None

        elapsed = time.monotonic() - started_at

        print(
            f"[Ollama] Response in {elapsed:.2f}s | "
            f"Action={action} | "
            f"Reason={decision.get('reason', '')}",
            flush=True,
        )

        return {
            "action": action,
            "target_id": decision.get("target_id"),
            "reason": str(decision.get("reason", ""))[:200],
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        TypeError,
    ) as exc:
        elapsed = time.monotonic() - started_at
        print(
            f"[Ollama] Request failed after {elapsed:.2f}s | "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None

