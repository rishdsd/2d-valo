# Tactical Arena — Refactored

A modular version of the 2v2 Pygame prototype with Fire Burst.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

If you already have a working virtual environment with Pygame installed, activate it and run `python main.py`.

## Controls
- `WASD` or arrow keys: move
- Mouse: aim
- Left click: shoot
- `R`: reload
- `Q`: Fire Burst
- `Enter`: next round / restart match
- `Esc`: quit

## Modules
- `main.py`: event loop and game orchestration
- `config.py`: tuning constants and colors
- `entities.py`: characters, bullets, Fire Burst projectiles/zones
- `arena.py`: map geometry, collision, line-of-sight and bot pathfinding
- `combat.py`: bullet movement, collision and damage
- `abilities.py`: Fire Burst movement and burning-zone damage
- `bots.py`: rule-based bot movement and shooting
- `rounds.py`: new-round setup
- `rendering.py`: drawing and HUD

This is a structural refactor, not a new gameplay feature. Bot Fire Burst usage is intentionally not included yet.
