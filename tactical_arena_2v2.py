import math
import random
import sys
import pygame

WIDTH, HEIGHT, FPS = 1000, 700, 60
ROUND_WIN_TARGET = 3
BG, GRID = (20, 24, 33), (30, 35, 46)
WALL_COLOR, WHITE, MUTED = (70, 81, 101), (240, 243, 250), (160, 170, 190)
BLUE, BLUE_LIGHT = (70, 180, 255), (150, 220, 255)
RED, RED_LIGHT = (240, 90, 95), (255, 175, 175)
GREEN, YELLOW = (90, 220, 140), (250, 205, 90)

PLAYER_RADIUS, PLAYER_SPEED, BOT_SPEED = 15, 245, 115
PLAYER_MAX_HP = BOT_MAX_HP = 100
PLAYER_DAMAGE, BOT_DAMAGE = 25, 12
PLAYER_BULLET_SPEED, BOT_BULLET_SPEED = 620, 420
PLAYER_FIRE_INTERVAL, BOT_FIRE_INTERVAL = 0.22, 0.82
MAGAZINE_SIZE, RELOAD_SECONDS, BULLET_RADIUS = 12, 1.2, 4

# Ember's signature ability.
FIRE_COOLDOWN = 8.0
FIRE_PROJECTILE_SPEED = 520
FIRE_PROJECTILE_RANGE = 420
FIRE_ZONE_RADIUS = 62
FIRE_ZONE_DURATION = 3.0
FIRE_DAMAGE = 5
FIRE_DAMAGE_INTERVAL = 0.5
FIRE_ORANGE, FIRE_YELLOW = (255, 105, 35), (255, 190, 70)

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Tactical Arena — 2v2 + Fire Burst")
clock = pygame.time.Clock()
font, small_font, large_font = pygame.font.Font(None, 25), pygame.font.Font(None, 19), pygame.font.Font(None, 42)

walls = [
    pygame.Rect(240, 145, 70, 220),
    pygame.Rect(420, 90, 190, 55),
    pygame.Rect(470, 280, 70, 210),
    pygame.Rect(700, 160, 55, 230),
    pygame.Rect(180, 500, 220, 45),
]


def circle_hits_rect(pos, radius, rect):
    closest_x = max(rect.left, min(pos.x, rect.right))
    closest_y = max(rect.top, min(pos.y, rect.bottom))
    dx, dy = pos.x - closest_x, pos.y - closest_y
    return dx * dx + dy * dy < radius * radius


def move_with_walls(pos, movement, radius):
    """Move on each axis independently and only resolve collisions on that axis."""
    # X axis
    if movement.x != 0:
        pos.x += movement.x
        for wall in walls:
            if circle_hits_rect(pos, radius, wall):
                if movement.x > 0:
                    pos.x = wall.left - radius
                else:
                    pos.x = wall.right + radius

    # Y axis. Do not snap horizontally when vertical movement hits a wall.
    if movement.y != 0:
        pos.y += movement.y
        for wall in walls:
            if circle_hits_rect(pos, radius, wall):
                if movement.y > 0:
                    pos.y = wall.top - radius
                else:
                    pos.y = wall.bottom + radius

    pos.x = max(radius, min(WIDTH - radius, pos.x))
    pos.y = max(70 + radius, min(HEIGHT - radius, pos.y))


def clear_line_of_sight(start, end):
    distance = start.distance_to(end)
    if distance <= 1:
        return True
    steps = max(2, int(distance / 8))
    for i in range(1, steps):
        point = start.lerp(end, i / steps)
        if any(wall.collidepoint(point.x, point.y) for wall in walls):
            return False
    return True


class Character:
    def __init__(self, name, team, position, is_human=False, skill=1):
        self.name, self.team = name, team
        self.pos = pygame.Vector2(position)
        self.is_human, self.skill = is_human, skill
        self.radius = PLAYER_RADIUS
        self.max_hp = PLAYER_MAX_HP if is_human else BOT_MAX_HP
        self.hp, self.alive = self.max_hp, True
        self.last_shot = -10.0
        self.ammo = MAGAZINE_SIZE if is_human else 999
        self.reloading_until = 0.0
        self.kills = 0

    @property
    def reloading(self):
        now = pygame.time.get_ticks() / 1000.0
        return self.reloading_until > now


class Bullet:
    def __init__(self, position, direction, owner):
        self.pos = pygame.Vector2(position)
        self.owner, self.team = owner, owner.team
        self.velocity = pygame.Vector2(direction) * (
            PLAYER_BULLET_SPEED if owner.is_human else BOT_BULLET_SPEED
        )
        self.damage = PLAYER_DAMAGE if owner.is_human else BOT_DAMAGE
        self.alive = True


class FireProjectile:
    def __init__(self, position, direction, owner):
        self.pos = pygame.Vector2(position)
        self.velocity = pygame.Vector2(direction) * FIRE_PROJECTILE_SPEED
        self.owner, self.team = owner, owner.team
        self.distance_travelled = 0.0
        self.alive = True


class FireZone:
    def __init__(self, position, owner, now):
        self.pos = pygame.Vector2(position)
        self.owner, self.team = owner, owner.team
        self.created_at = now
        self.expires_at = now + FIRE_ZONE_DURATION
        self.next_damage_at = {}


def make_round():
    return [
        Character("YOU", "blue", (100, 350), True),
        Character("ALLY", "blue", (145, 430), skill=1),
        Character("ENEMY 1", "red", (860, 250), skill=1),
        Character("ENEMY 2", "red", (860, 470), skill=2),
    ], []


def nearest_visible_enemy(bot, characters):
    enemies = [
        c for c in characters
        if c.alive and c.team != bot.team and clear_line_of_sight(bot.pos, c.pos)
    ]
    return min(enemies, key=lambda c: bot.pos.distance_squared_to(c.pos)) if enemies else None



def walkable_grid_point(gx, gy, radius=PLAYER_RADIUS):
    point = pygame.Vector2(gx * 25 + 12.5, gy * 25 + 82.5)
    if point.x < radius or point.x > WIDTH - radius:
        return False
    if point.y < 70 + radius or point.y > HEIGHT - radius:
        return False
    return not any(circle_hits_rect(point, radius, wall) for wall in walls)


def find_path(start_pos, goal_pos, radius=PLAYER_RADIUS):
    """Small-grid BFS pathfinding so bots can route around arena walls."""
    cell = 25
    cols, rows = WIDTH // cell, (HEIGHT - 70) // cell

    def to_grid(pos):
        return (
            max(0, min(cols - 1, int(pos.x // cell))),
            max(0, min(rows - 1, int((pos.y - 70) // cell))),
        )

    start = to_grid(start_pos)
    goal = to_grid(goal_pos)
    if start == goal:
        return []

    # If the exact target tile is blocked, route to the closest walkable tile.
    goals = []
    for gy in range(rows):
        for gx in range(cols):
            if walkable_grid_point(gx, gy, radius):
                center = pygame.Vector2(gx * cell + cell / 2, 70 + gy * cell + cell / 2)
                if center.distance_squared_to(goal_pos) <= (cell * 2) ** 2:
                    goals.append((gx, gy))
    if not goals:
        return []

    goal_set = set(goals)
    queue = [start]
    came_from = {start: None}
    found = None
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (1, -1), (-1, 1), (-1, -1))

    for current in queue:
        if current in goal_set:
            found = current
            break
        for dx, dy in directions:
            nxt = (current[0] + dx, current[1] + dy)
            if nxt in came_from or not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            if not walkable_grid_point(*nxt, radius):
                continue
            # Prevent diagonal corner-cutting through walls.
            if dx and dy:
                if not walkable_grid_point(current[0] + dx, current[1], radius):
                    continue
                if not walkable_grid_point(current[0], current[1] + dy, radius):
                    continue
            came_from[nxt] = current
            queue.append(nxt)

    if found is None:
        return []

    path = []
    node = found
    while node is not None:
        path.append(pygame.Vector2(node[0] * cell + cell / 2, 70 + node[1] * cell + cell / 2))
        node = came_from[node]
    path.reverse()
    return path[1:]


def bot_update(bot, characters, bullets, dt, now):
    if not bot.alive or bot.is_human:
        return

    enemies = [c for c in characters if c.alive and c.team != bot.team]
    if not enemies:
        return

    # Target the closest enemy, even when a wall currently blocks the shot.
    target = min(enemies, key=lambda c: bot.pos.distance_squared_to(c.pos))
    delta = target.pos - bot.pos
    distance = delta.length()
    has_los = clear_line_of_sight(bot.pos, target.pos)

    # Move toward a firing position using a wall-aware route.
    move_dir = pygame.Vector2()
    if not has_los or distance > 235:
        path = find_path(bot.pos, target.pos, bot.radius)
        if path:
            waypoint_delta = path[0] - bot.pos
            if waypoint_delta.length_squared() > 16:
                move_dir = waypoint_delta.normalize()
        elif distance > 235 and distance > 1:
            # Fallback: test several directions and choose a valid step that
            # makes progress, rather than repeatedly pushing into a wall.
            candidates = [
                delta.normalize(),
                pygame.Vector2(1, 0), pygame.Vector2(-1, 0),
                pygame.Vector2(0, 1), pygame.Vector2(0, -1),
                pygame.Vector2(1, 1).normalize(), pygame.Vector2(-1, 1).normalize(),
                pygame.Vector2(1, -1).normalize(), pygame.Vector2(-1, -1).normalize(),
            ]
            best_score = distance
            for candidate in candidates:
                test_pos = bot.pos + candidate * BOT_SPEED * dt
                if any(circle_hits_rect(test_pos, bot.radius, wall) for wall in walls):
                    continue
                score = test_pos.distance_to(target.pos)
                if score < best_score:
                    best_score, move_dir = score, candidate
    elif distance < 115 and distance > 1:
        move_dir = -delta.normalize()
    else:
        # Strafe during a duel so bots don't stand still in the open.
        if distance > 1:
            perpendicular = pygame.Vector2(-delta.y, delta.x).normalize()
            strafe_sign = 1 if int(now * 1.7 + (0 if bot.team == "blue" else 1)) % 2 == 0 else -1
            move_dir = perpendicular * strafe_sign

    if move_dir.length_squared() > 0:
        move_with_walls(bot.pos, move_dir.normalize() * BOT_SPEED * dt, bot.radius)

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


def draw_text(text, x, y, color=WHITE, font_obj=font):
    screen.blit(font_obj.render(text, True, color), (x, y))


def make_new_round():
    return make_round()


characters, bullets = make_new_round()
fire_projectiles, fire_zones = [], []
player_fire_burst_ready_at = 0.0
blue_rounds = red_rounds = 0
round_number = 1
round_over = match_over = False
round_message = "Eliminate the other team!"


def start_next_round():
    global characters, bullets, fire_projectiles, fire_zones
    global player_fire_burst_ready_at, round_over, round_message, round_number
    characters, bullets = make_new_round()
    fire_projectiles, fire_zones = [], []
    player_fire_burst_ready_at = 0.0
    round_over = False
    round_number += 1
    round_message = "Round started — work with your teammate!"


running = True
while running:
    dt = min(clock.tick(FPS) / 1000.0, 0.04)
    now = pygame.time.get_ticks() / 1000.0
    player = next(c for c in characters if c.is_human)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif (
                event.key == pygame.K_r
                and not round_over
                and player.reloading_until == 0
                and player.ammo < MAGAZINE_SIZE
            ):
                player.reloading_until = now + RELOAD_SECONDS
                round_message = "Reloading..."
            elif (
                event.key == pygame.K_q
                and not round_over
                and player.alive
                and now >= player_fire_burst_ready_at
            ):
                direction = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    fire_projectiles.append(
                        FireProjectile(player.pos + direction * (player.radius + 5), direction, player)
                    )
                    player_fire_burst_ready_at = now + FIRE_COOLDOWN
                    round_message = "Fire Burst launched!"
            elif event.key == pygame.K_RETURN and round_over and not match_over:
                start_next_round()
            elif event.key == pygame.K_RETURN and match_over:
                blue_rounds = red_rounds = 0
                round_number = 1
                match_over = False
                start_next_round()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if (
                not round_over and player.alive and not player.reloading
                and player.ammo > 0 and now - player.last_shot >= PLAYER_FIRE_INTERVAL
            ):
                direction = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    bullets.append(Bullet(player.pos + direction * (player.radius + 4), direction, player))
                    player.ammo -= 1
                    player.last_shot = now

    if not round_over:
        keys = pygame.key.get_pressed()
        movement = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if player.alive and movement.length_squared() > 0:
            move_with_walls(player.pos, movement.normalize() * PLAYER_SPEED * dt, player.radius)

        # Important: test the timer directly. The reloading property becomes False
        # once the deadline passes, so it cannot be used as this completion condition.
        if player.reloading_until > 0 and now >= player.reloading_until:
            player.ammo = MAGAZINE_SIZE
            player.reloading_until = 0.0
            round_message = "Reload complete."

        for character in characters:
            bot_update(character, characters, bullets, dt, now)

        # Move Fire Burst projectiles and create a burning zone on impact/range.
        for projectile in fire_projectiles:
            step = projectile.velocity * dt
            projectile.pos += step
            projectile.distance_travelled += step.length()

            hit_wall = any(circle_hits_rect(projectile.pos, 6, wall) for wall in walls)
            hit_enemy = any(
                c.alive and c.team != projectile.team
                and projectile.pos.distance_to(c.pos) <= c.radius + 6
                for c in characters
            )
            out_of_bounds = not (
                0 <= projectile.pos.x <= WIDTH and 70 <= projectile.pos.y <= HEIGHT
            )
            reached_range = projectile.distance_travelled >= FIRE_PROJECTILE_RANGE

            if hit_wall or hit_enemy or out_of_bounds or reached_range:
                zone_pos = projectile.pos - projectile.velocity.normalize() * (8 if hit_wall else 0)
                zone_pos.x = max(FIRE_ZONE_RADIUS, min(WIDTH - FIRE_ZONE_RADIUS, zone_pos.x))
                zone_pos.y = max(70 + FIRE_ZONE_RADIUS, min(HEIGHT - FIRE_ZONE_RADIUS, zone_pos.y))
                if not out_of_bounds:
                    fire_zones.append(FireZone(zone_pos, projectile.owner, now))
                projectile.alive = False
        fire_projectiles = [p for p in fire_projectiles if p.alive]

        # Damage opposing characters while they stand inside a fire zone.
        for zone in fire_zones:
            if now >= zone.expires_at:
                continue
            for victim in characters:
                if not victim.alive or victim.team == zone.team:
                    continue
                inside = victim.pos.distance_to(zone.pos) <= FIRE_ZONE_RADIUS + victim.radius
                if not inside:
                    zone.next_damage_at.pop(victim, None)
                    continue
                if now >= zone.next_damage_at.get(victim, zone.created_at):
                    victim.hp = max(0, victim.hp - FIRE_DAMAGE)
                    zone.next_damage_at[victim] = now + FIRE_DAMAGE_INTERVAL
                    if victim.hp == 0:
                        victim.alive = False
                        zone.owner.kills += 1
        fire_zones = [z for z in fire_zones if now < z.expires_at]

        for bullet in bullets:
            bullet.pos += bullet.velocity * dt
            if not (0 <= bullet.pos.x <= WIDTH and 70 <= bullet.pos.y <= HEIGHT):
                bullet.alive = False
                continue
            if any(circle_hits_rect(bullet.pos, BULLET_RADIUS, wall) for wall in walls):
                bullet.alive = False
                continue
            for victim in characters:
                if not victim.alive or victim.team == bullet.team:
                    continue
                if bullet.pos.distance_to(victim.pos) <= victim.radius + BULLET_RADIUS:
                    victim.hp = max(0, victim.hp - bullet.damage)
                    bullet.alive = False
                    if victim.hp == 0:
                        victim.alive = False
                        bullet.owner.kills += 1
                    break
        bullets = [b for b in bullets if b.alive]

        blue_alive = any(c.alive for c in characters if c.team == "blue")
        red_alive = any(c.alive for c in characters if c.team == "red")
        if not blue_alive or not red_alive:
            round_over = True
            if blue_alive:
                blue_rounds += 1
                round_message = "BLUE TEAM WINS THE ROUND!"
            else:
                red_rounds += 1
                round_message = "RED TEAM WINS THE ROUND!"
            if blue_rounds >= ROUND_WIN_TARGET or red_rounds >= ROUND_WIN_TARGET:
                match_over = True
                round_message = (
                    "MATCH VICTORY — BLUE TEAM!"
                    if blue_rounds >= ROUND_WIN_TARGET
                    else "MATCH DEFEAT — RED TEAM!"
                )

    # Rendering
    screen.fill(BG)
    for x in range(0, WIDTH, 40):
        pygame.draw.line(screen, GRID, (x, 70), (x, HEIGHT))
    for y in range(70, HEIGHT, 40):
        pygame.draw.line(screen, GRID, (0, y), (WIDTH, y))
    pygame.draw.rect(screen, (14, 17, 24), (0, 0, WIDTH, 70))
    draw_text("TACTICAL ARENA | 2v2", 18, 10, WHITE, large_font)
    draw_text(f"BLUE {blue_rounds} - {red_rounds} RED", 440, 18, YELLOW)
    draw_text(f"ROUND {round_number}", 805, 18)

    for wall in walls:
        pygame.draw.rect(screen, WALL_COLOR, wall, border_radius=5)
        pygame.draw.rect(screen, (105, 118, 140), wall, 2, border_radius=5)

    # Draw active fire zones and their projectiles.
    for zone in fire_zones:
        remaining = max(0.0, zone.expires_at - now)
        pulse = int(5 * (1.0 - remaining / FIRE_ZONE_DURATION))
        pygame.draw.circle(screen, (130, 48, 25), zone.pos, FIRE_ZONE_RADIUS)
        pygame.draw.circle(screen, FIRE_ORANGE, zone.pos, max(8, FIRE_ZONE_RADIUS - pulse), 4)
        pygame.draw.circle(screen, FIRE_YELLOW, zone.pos, max(6, FIRE_ZONE_RADIUS // 2), 2)

    for projectile in fire_projectiles:
        pygame.draw.circle(screen, FIRE_ORANGE, projectile.pos, 8)
        pygame.draw.circle(screen, FIRE_YELLOW, projectile.pos, 4)

    for bullet in bullets:
        pygame.draw.circle(screen, BLUE_LIGHT if bullet.team == "blue" else RED_LIGHT, bullet.pos, BULLET_RADIUS)

    for character in characters:
        color = BLUE if character.team == "blue" else RED
        highlight = BLUE_LIGHT if character.team == "blue" else RED_LIGHT
        if not character.alive:
            pygame.draw.circle(screen, (75, 80, 90), character.pos, character.radius, 2)
            continue
        pygame.draw.circle(screen, color, character.pos, character.radius)
        pygame.draw.circle(screen, highlight, character.pos, character.radius, 2)
        bar = pygame.Rect(character.pos.x - 22, character.pos.y - 29, 44, 6)
        pygame.draw.rect(screen, (55, 40, 48), bar)
        hp_color = GREEN if character.hp > 35 else YELLOW if character.hp > 15 else RED
        pygame.draw.rect(screen, hp_color, (bar.x, bar.y, bar.width * character.hp / character.max_hp, bar.height))
        name_surface = small_font.render(character.name, True, WHITE)
        screen.blit(name_surface, name_surface.get_rect(center=(character.pos.x, character.pos.y + 29)))

    if player.alive:
        aim = pygame.Vector2(pygame.mouse.get_pos()) - player.pos
        if aim.length_squared() > 0:
            aim.scale_to_length(player.radius + 10)
            pygame.draw.line(screen, WHITE, player.pos, player.pos + aim, 3)
    mx, my = pygame.mouse.get_pos()
    pygame.draw.circle(screen, WHITE, (mx, my), 8, 1)
    pygame.draw.line(screen, WHITE, (mx - 12, my), (mx - 4, my), 1)
    pygame.draw.line(screen, WHITE, (mx + 4, my), (mx + 12, my), 1)
    pygame.draw.line(screen, WHITE, (mx, my - 12), (mx, my - 4), 1)
    pygame.draw.line(screen, WHITE, (mx, my + 4), (mx, my + 12), 1)

    pygame.draw.rect(screen, (14, 17, 24), (0, HEIGHT - 55, WIDTH, 55))
    ally = next(c for c in characters if c.name == "ALLY")
    draw_text(f"YOU HP: {player.hp}", 16, HEIGHT - 42, GREEN if player.hp > 30 else RED)
    draw_text(f"AMMO: {player.ammo}/{MAGAZINE_SIZE}", 175, HEIGHT - 42, YELLOW)
    draw_text(f"ALLY: {'UP' if ally.alive else 'DOWN'} ({ally.hp} HP)", 365, HEIGHT - 42, BLUE_LIGHT)
    fire_ready_in = max(0.0, player_fire_burst_ready_at - now)
    ability_label = "Q FIRE BURST: READY" if fire_ready_in <= 0 else f"Q FIRE BURST: {fire_ready_in:.1f}s"
    draw_text(ability_label, 570, HEIGHT - 42, FIRE_YELLOW if fire_ready_in <= 0 else MUTED, small_font)
    draw_text("WASD move | Mouse aim | Click shoot | R reload", 570, HEIGHT - 22, MUTED, small_font)

    if player.reloading:
        draw_text("RELOADING...", 18, HEIGHT - 72, YELLOW, small_font)

    if round_over:
        color = GREEN if blue_rounds > red_rounds else RED
        overlay = large_font.render(round_message, True, color)
        screen.blit(overlay, overlay.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 15)))
        prompt = "Enter: restart match" if match_over else "Enter: next round"
        label = font.render(prompt, True, WHITE)
        screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 25)))

    pygame.display.flip()

pygame.quit()
sys.exit()
