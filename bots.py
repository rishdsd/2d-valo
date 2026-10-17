import math
import random
import pygame
from tactical_ai import TacticalAI
from config import (
    WIDTH,
    HEIGHT,
    BOT_SPEED,
    BOT_FIRE_INTERVAL,
    FIRE_COOLDOWN,
    WATER_WALL_COOLDOWN,
)
from entities import Bullet, FireProjectile, WaterWall
from bot_policy import choose_fire_burst_target, choose_water_wall_position, choose_combat_target
from arena import clear_line_of_sight, find_path, move_with_walls, circle_hits_rect, walls


def find_cover_position(bot, target):
    """Find a reachable nearby position that blocks enemy line of sight."""
    candidates = []

    for radius in (55, 90, 125, 160):
        for i in range(16):
            angle = 2 * math.pi * i / 16
            offset = pygame.Vector2(
                math.cos(angle), math.sin(angle)
            ) * radius
            candidate = bot.pos + offset

            if not (
                bot.radius <= candidate.x <= WIDTH - bot.radius
                and bot.radius <= candidate.y <= HEIGHT - bot.radius
            ):
                continue

            if any(
                circle_hits_rect(candidate, bot.radius, wall)
                for wall in walls
            ):
                continue

            # A useful cover position blocks the target's line of sight.
            if clear_line_of_sight(candidate, target.pos):
                continue

            path = find_path(bot.pos, candidate, bot.radius)

            # A candidate very close to the bot may need no path.
            if not path and bot.pos.distance_to(candidate) > 20:
                continue

            score = (
                bot.pos.distance_to(candidate)
                + 0.20 * candidate.distance_to(target.pos)
            )
            candidates.append((score, candidate))

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[0])[1]


def move_toward_position(bot, destination, dt):
    """Move using existing wall-aware pathfinding."""
    delta = destination - bot.pos

    if delta.length() <= 16:
        return True

    path = find_path(bot.pos, destination, bot.radius)

    if path:
        waypoint = path[0]
    else:
        waypoint = destination

    direction = waypoint - bot.pos

    if direction.length_squared() > 1:
        move_with_walls(
            bot.pos,
            direction.normalize() * BOT_SPEED * dt,
            bot.radius,
        )

    return bot.pos.distance_to(destination) <= 18


def update_cover_peek(bot, target, dt, now):
    """
    Run the cover -> peek -> shoot -> cover cycle.
    Returns True when this controller handled movement.
    """
    if not hasattr(bot, "tactical_state"):
        bot.tactical_state = "seek_cover"
        bot.cover_position = None
        bot.tactical_state_since = now
        bot.peek_visible_since = None

    state = bot.tactical_state

    # Find cover when starting a cycle or when the old position is lost.
    if bot.cover_position is None:
        bot.cover_position = find_cover_position(bot, target)

        if bot.cover_position is None:
            bot.cover_peek_failed_until = now + 2.0
            bot.tactical_state = "normal"
            print(
                f"[Tactics] {bot.team}: no reachable cover found",
                flush=True,
            )
            return False

        print(
            f"[Tactics] {bot.team}: cover cycle started",
            flush=True,
        )

    if state == "seek_cover":
        reached = move_toward_position(
            bot, bot.cover_position, dt
        )

        if reached:
            bot.tactical_state = "in_cover"
            bot.tactical_state_since = now
            print(f"[Tactics] {bot.team}: in cover", flush=True)

        return True

    if state == "in_cover":
        # Brief pause before attempting the next peek.
        if now - bot.tactical_state_since >= 0.45:
            bot.tactical_state = "peeking"
            bot.tactical_state_since = now
            bot.peek_visible_since = None
            print(f"[Tactics] {bot.team}: peeking", flush=True)

        return True

    if state == "peeking":
        visible = clear_line_of_sight(bot.pos, target.pos)

        if visible:
            if bot.peek_visible_since is None:
                bot.peek_visible_since = now

            # Limit exposure after gaining a firing angle.
            elif now - bot.peek_visible_since >= 0.65:
                bot.tactical_state = "return_cover"
                print(
                    f"[Tactics] {bot.team}: returning to cover",
                    flush=True,
                )
                return True

        else:
            bot.peek_visible_since = None

            # Don't chase indefinitely if no angle is available.
            if now - bot.tactical_state_since >= 1.5:
                bot.tactical_state = "return_cover"
                print(
                    f"[Tactics] {bot.team}: peek timed out",
                    flush=True,
                )
                return True

            move_toward_position(bot, target.pos, dt)

        return True

    if state == "return_cover":
        reached = move_toward_position(
            bot, bot.cover_position, dt
        )

        if reached:
            bot.tactical_state = "in_cover"
            bot.tactical_state_since = now
            bot.peek_visible_since = None
            print(
                f"[Tactics] {bot.team}: back in cover",
                flush=True,
            )

        return True

    return False


def bot_update(
    bot,
    characters,
    bullets,
    dt,
    now,
    fire_projectiles=None,
    water_walls=None,
    human_target=None,
    tactical_ai=None,
):
    if not bot.alive or bot.is_human:
        return

    enemies = [c for c in characters if c.alive and c.team != bot.team]
    if not enemies:
        return
    
    # Ask the rule-based policy whether Fire Burst is worth using.
    if fire_projectiles is not None:
        ability_target = choose_fire_burst_target(bot, enemies, now)

        if ability_target is not None:
            direction = ability_target - bot.pos

            if direction.length_squared() > 0:
                direction = direction.normalize()

                fire_projectiles.append(
                    FireProjectile(
                        bot.pos + direction * (bot.radius + 5),
                        direction,
                        bot,
                    )
                )

                bot.fire_burst_ready_at = now + FIRE_COOLDOWN

    # Defensive Water Wall decision.
    if water_walls is not None:
        wall_decision = choose_water_wall_position(
            bot, characters, now
        )

        if wall_decision is not None:
            wall_position, threat_direction = wall_decision

            water_walls.append(
                WaterWall(
                    wall_position,
                    threat_direction,
                    now,
                )
            )

            bot.water_wall_ready_at = now + WATER_WALL_COOLDOWN

    # Target the closest enemy, even when a wall currently blocks the shot.
    target = choose_combat_target(
        bot,
        enemies,
        human_target,
    )
    if target is None:
        return

    # Ask Ollama for an occasional high-level tactical decision.
    if not hasattr(bot, "tactical_action"):
        bot.tactical_action = "attack"

    if tactical_ai is not None:
        visible_enemies = [
            enemy for enemy in enemies
            if clear_line_of_sight(bot.pos, enemy.pos)
        ]

        max_hp = getattr(bot, "max_hp", 100)
        health_ratio = bot.hp / max_hp if max_hp > 0 else 1.0

        observation = {
            "bot_hp": bot.hp,
            "target_hp": target.hp,
            "target_distance": round(
                bot.pos.distance_to(target.pos)
            ),
            "target_visible": clear_line_of_sight(
                bot.pos, target.pos
            ),
            "visible_enemy_count": len(visible_enemies),
            "bot_health_percent": round(health_ratio * 100),
            "available_actions": ["attack", "cover_peek"],
        }

        tactical_ai.request_decision(observation)

        
        decision = tactical_ai.get_latest_decision()

        if decision is not None:
            bot.tactical_action = decision["action"]

            print(
                f"[Bot] {bot.team}: "
                f"{bot.tactical_action} | HP={bot.hp}",
                flush=True,
            )



    delta = target.pos - bot.pos
    distance = delta.length()
    has_los = clear_line_of_sight(bot.pos, target.pos)

    
    # Low-health bots, or bots instructed by Ollama, use cover-and-peek.
    max_hp = getattr(bot, "max_hp", 100)
    health_ratio = bot.hp / max_hp if max_hp > 0 else 1.0

    use_cover_peek = (
        health_ratio <= 0.50
        or getattr(bot, "tactical_action", "attack") == "cover_peek"
    )

    cover_peek_active = False

    if use_cover_peek:
        cover_peek_active = update_cover_peek(
            bot, target, dt, now
        )
    else:
        # Clear old tactical state when returning to normal combat.
        bot.tactical_state = "normal"
        bot.cover_position = None

    move_dir = pygame.Vector2()

    if not cover_peek_active:
        # Preserve the existing normal combat movement.
        if not has_los or distance > 235:
            path = find_path(bot.pos, target.pos, bot.radius)

            if path:
                waypoint_delta = path[0] - bot.pos
                if waypoint_delta.length_squared() > 16:
                    move_dir = waypoint_delta.normalize()

            elif distance > 235 and distance > 1:
                candidates = [
                    delta.normalize(),
                    pygame.Vector2(1, 0),
                    pygame.Vector2(-1, 0),
                    pygame.Vector2(0, 1),
                    pygame.Vector2(0, -1),
                    pygame.Vector2(1, 1).normalize(),
                    pygame.Vector2(-1, 1).normalize(),
                    pygame.Vector2(1, -1).normalize(),
                    pygame.Vector2(-1, -1).normalize(),
                ]

                best_score = distance

                for candidate in candidates:
                    test_pos = bot.pos + candidate * BOT_SPEED * dt

                    if any(
                        circle_hits_rect(test_pos, bot.radius, wall)
                        for wall in walls
                    ):
                        continue

                    score = test_pos.distance_to(target.pos)

                    if score < best_score:
                        best_score = score
                        move_dir = candidate

        elif distance < 115 and distance > 1:
            move_dir = -delta.normalize()

        elif distance > 1:
            perpendicular = pygame.Vector2(
                -delta.y, delta.x
            ).normalize()

            strafe_sign = (
                1
                if int(now * 1.7 + (0 if bot.team == "blue" else 1)) % 2 == 0
                else -1
            )

            move_dir = perpendicular * strafe_sign

    if move_dir.length_squared() > 0:
        move_with_walls(
            bot.pos,
            move_dir.normalize() * BOT_SPEED * dt,
            bot.radius,
        )

    can_shoot = (
        not cover_peek_active
        or bot.tactical_state == "peeking"
    )

    if (
        can_shoot
        and distance > 1
        and clear_line_of_sight(bot.pos, target.pos)
        and now - bot.last_shot >= BOT_FIRE_INTERVAL
    ):
        # Bots only fire when they have a clear line of sight.
        delta = target.pos - bot.pos
        distance = delta.length()
        if distance > 1 and clear_line_of_sight(bot.pos, target.pos) and now - bot.last_shot >= BOT_FIRE_INTERVAL:
            angle = math.atan2(delta.y, delta.x)
            error = 0.20 if bot.skill == 1 else 0.09
            angle += random.uniform(-error, error)
            aim = pygame.Vector2(math.cos(angle), math.sin(angle))
            bullets.append(Bullet(bot.pos + aim * (bot.radius + 3), aim, bot))
            bot.last_shot = now

