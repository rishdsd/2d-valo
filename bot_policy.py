import pygame

from config import FIRE_PROJECTILE_RANGE, WATER_WALL_MAX_RANGE
from arena import clear_line_of_sight


def choose_fire_burst_target(bot, enemies, now):
    """
    Decide whether a bot should use Fire Burst.
    Works for bots on either team.
    """

    if now < bot.fire_burst_ready_at:
        return None

    # Consider enemies that are in range and visible.
    candidates = [
        enemy
        for enemy in enemies
        if bot.pos.distance_to(enemy.pos) <= FIRE_PROJECTILE_RANGE - 20
        and clear_line_of_sight(bot.pos, enemy.pos)
    ]

    if not candidates:
        return None

    # Priority 1: target a cluster of at least two enemies.
    for target in candidates:
        nearby = [
            enemy
            for enemy in candidates
            if enemy.pos.distance_to(target.pos) <= 115
        ]

        if len(nearby) >= 2:
            center = pygame.Vector2(0, 0)

            for enemy in nearby:
                center += enemy.pos

            center /= len(nearby)

            if (
                bot.pos.distance_to(center) <= FIRE_PROJECTILE_RANGE - 20
                and clear_line_of_sight(bot.pos, center)
            ):
                return center

    # Priority 2: attack a single enemy at a useful distance.
    target = min(
        candidates,
        key=lambda enemy: bot.pos.distance_squared_to(enemy.pos),
    )

    distance = bot.pos.distance_to(target.pos)

    if 110 <= distance <= 220:
        return target.pos.copy()

    return None

def choose_water_wall_position(bot, characters, now):
    """
    Decide whether the Blue bot should protect itself or its teammate.

    Returns (wall_position, threat_direction), or None.
    """
    if bot.is_human or bot.team != "blue":
        return None

    if now < bot.water_wall_ready_at:
        return None

    enemies = [
        c for c in characters
        if c.alive and c.team != bot.team
    ]

    allies_to_protect = [
        c for c in characters
        if c.alive and c.team == bot.team
    ]

    candidates = []

    for ally in allies_to_protect:
        for enemy in enemies:
            threat_vector = enemy.pos - ally.pos
            threat_distance = threat_vector.length()

            # Only respond to plausible ranged threats.
            if not 110 <= threat_distance <= 320:
                continue

            if not clear_line_of_sight(enemy.pos, ally.pos):
                continue

            threat_direction = threat_vector.normalize()

            # Put the barrier between the threatened ally and the enemy.
            offset = min(90, threat_distance * 0.45)
            wall_position = ally.pos + threat_direction * offset

            # The bot must be able to deploy the wall within its range.
            if bot.pos.distance_to(wall_position) > WATER_WALL_MAX_RANGE:
                continue

            # Prefer protecting the human player, while considering
            # how far the bot must move its ability placement.
            score = bot.pos.distance_to(wall_position)
            if ally.is_human:
                score -= 35

            candidates.append(
                (score, wall_position, threat_direction)
            )

    if not candidates:
        return None

    _, position, direction = min(candidates, key=lambda item: item[0])
    return position, direction

def choose_player_aim_target(player, characters, mouse_pos):
    """
    Infer which enemy the human player is aiming at.
    Returns the enemy character, or None.
    """
    enemies = [
        c for c in characters
        if c.alive and c.team != player.team
    ]

    cursor = pygame.Vector2(mouse_pos)
    candidates = []

    for enemy in enemies:
        cursor_distance = enemy.pos.distance_to(cursor)

        # The cursor should be reasonably close to the enemy.
        if cursor_distance > max(70, enemy.radius + 40):
            continue

        # Don't coordinate around an enemy hidden behind a wall.
        if not clear_line_of_sight(player.pos, enemy.pos):
            continue

        candidates.append((cursor_distance, enemy))

    if not candidates:
        return None

    return min(candidates, key=lambda item: item[0])[1]


def choose_combat_target(bot, enemies, human_target=None):
    """
    Select a target using team coordination and tactical priorities.
    """
    visible_enemies = [
        enemy for enemy in enemies
        if clear_line_of_sight(bot.pos, enemy.pos)
    ]

    # Blue teammate coordinates with the human player's target.
    if (
        bot.team == "blue"
        and human_target is not None
        and human_target in visible_enemies
    ):
        return human_target

    # Otherwise, finish off a weakened enemy when possible.
    if visible_enemies:
        return min(
            visible_enemies,
            key=lambda enemy: (
                enemy.hp,
                bot.pos.distance_squared_to(enemy.pos),
            ),
        )

    # No visible targets: still approach the nearest enemy.
    if enemies:
        return min(
            enemies,
            key=lambda enemy: bot.pos.distance_squared_to(enemy.pos),
        )

    return None