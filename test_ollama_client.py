
from ollama_client import choose_tactical_action


observation = {
    "bot_hp": 20,
    "target_hp": 100,
    "target_distance": 150,
    "target_visible": True,
    "visible_enemy_count": 1,
    "available_actions": ["attack", "retreat"],
}

decision = choose_tactical_action(observation)

print("Observation:", observation)
print("Decision:", decision)

assert decision is not None, (
    "Ollama did not return a valid decision."
)
assert decision["action"] in ["attack", "retreat"]

print("Client test passed.")
