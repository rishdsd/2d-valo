import math
import random
import sys
import pygame

# -------------------- Configuration --------------------

WIDTH, HEIGHT = 1000, 700
FPS = 60

BG = (22, 26, 35)
GRID = (31, 36, 47)
WALL_COLOR = (75, 85, 105)
PLAYER_COLOR = (70, 180, 255)
ENEMY_COLOR = (240, 90, 95)
WHITE = (240, 243, 250)
MUTED = (160, 170, 190)
GREEN = (90, 220, 140)
YELLOW = (250, 205, 90)
DARK_RED = (105, 35, 45)

PLAYER_RADIUS = 16
PLAYER_SPEED = 250
BULLET_SPEED = 620
BOT_BULLET_SPEED = 430
BULLET_RADIUS = 4
SHOT_COOLDOWN = 0.22
BOT_SHOT_COOLDOWN = 0.85
MAGAZINE_SIZE = 12
RELOAD_SECONDS = 1.2
PLAYER_MAX_HEALTH = 100
BOT_MAX_HEALTH = 100

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Tactical Arena — Prototype 2")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 25)
small_font = pygame.font.Font(None, 19)
large_font = pygame.font.Font(None, 38)

walls = [
    pygame.Rect(240, 145, 70, 220),
    pygame.Rect(420, 90, 190, 55),
    pygame.Rect(470, 280, 70, 210),
    pygame.Rect(700, 160, 55, 230),
    pygame.Rect(180, 500, 220, 45),
]


class Player:
    def __init__(self):
        self.pos = pygame.Vector2(100, 350)
        self.health = PLAYER_MAX_HEALTH
        self.ammo = MAGAZINE_SIZE
        self.last_shot = -SHOT_COOLDOWN
        self.reloading_until = 0.0

    @property
    def reloading(self):
        return pygame.time.get_ticks() / 1000 < self.reloading_until


class Target:
    def __init__(self, x, y):
        self.pos = pygame.Vector2(x, y)
        self.health = 100
        self.radius = 18

    @property
    def alive(self):
        return self.health > 0


class Bullet:
    def __init__(self, pos, direction, owner):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(direction) * (
            BULLET_SPEED if owner == "player" else BOT_BULLET_SPEED
        )
        self.owner = owner
        self.alive = True


class EnemyBot:
    """A simple rule-based opponent: approach, aim imperfectly, and shoot."""

    def __init__(self):
        self.pos = pygame.Vector2(865, 350)
        self.health = BOT_MAX_HEALTH
        self.radius = 17
        self.last_shot = 0.0
        self.speed = 105
        self.alive = True

    def update(self, player, dt, now, bullets):
        if not self.alive or player.health <= 0:
            return

        to_player = player.pos - self.pos
        distance = to_player.length()

        # Keep some distance rather than running directly into the player.
        if distance > 255:
            direction = to_player.normalize()
            movement = direction * self.speed * dt
            move_with_walls(self.pos, movement, self.radius)

        # The bot only shoots when it has a reasonable line of sight.
        if distance < 520 and distance > 1 and now - self.last_shot >= BOT_SHOT_COOLDOWN:
            if clear_line_of_sight(self.pos, player.pos):
                direction = to_player.normalize()
                # Simulate imperfect aim by adding a small angular error.
                angle = math.atan2(direction.y, direction.x)
                angle += random.uniform(-0.14, 0.14)
                aim = pygame.Vector2(math.cos(angle), math.sin(angle))
                bullets.append(Bullet(self.pos + aim * (self.radius + 3), aim, "bot"))
                self.last_shot = now


def circle_hits_rect(pos, radius, rect):
    closest_x = max(rect.left, min(pos.x, rect.right))
    closest_y = max(rect.top, min(pos.y, rect.bottom))
    dx = pos.x - closest_x
    dy = pos.y - closest_y
    return dx * dx + dy * dy < radius * radius


def move_with_walls(pos, movement, radius):
    pos.x += movement.x
    for wall in walls:
        if circle_hits_rect(pos, radius, wall):
            if movement.x > 0:
                pos.x = wall.left - radius
            elif movement.x < 0:
                pos.x = wall.right + radius

    pos.y += movement.y
    for wall in walls:
        if circle_hits_rect(pos, radius, wall):
            if movement.y > 0:
                pos.y = wall.top - radius
            elif movement.y < 0:
                pos.y = wall.bottom + radius

    pos.x = max(radius, min(WIDTH - radius, pos.x))
    pos.y = max(radius + 70, min(HEIGHT - radius, pos.y))


def clear_line_of_sight(start, end):
    # Sample points between shooter and target; walls block vision and bullets.
    distance = start.distance_to(end)
    if distance == 0:
        return True
    steps = max(1, int(distance / 8))
    for i in range(1, steps):
        point = start.lerp(end, i / steps)
        if any(wall.collidepoint(point.x, point.y) for wall in walls):
            return False
    return True


def draw_text(text, x, y, color=WHITE, font_obj=font):
    surface = font_obj.render(text, True, color)
    screen.blit(surface, (x, y))


def reset_targets():
    return [Target(800, 100), Target(850, 520), Target(600, 590)]


def reset_round():
    return Player(), EnemyBot(), reset_targets(), [], 0


player, bot, targets, bullets, score = reset_round()
message = "WASD: move   Mouse: aim   Click: shoot   R: reload"
round_over = False
running = True

while running:
    dt = min(clock.tick(FPS) / 1000.0, 0.04)
    now = pygame.time.get_ticks() / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_r and not round_over and not player.reloading and player.ammo < MAGAZINE_SIZE:
                player.reloading_until = now + RELOAD_SECONDS
                message = "Reloading..."
            elif event.key == pygame.K_RETURN and round_over:
                player, bot, targets, bullets, score = reset_round()
                round_over = False
                message = "New round! Find cover and take the fight."

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not round_over and not player.reloading and player.ammo > 0 and now - player.last_shot >= SHOT_COOLDOWN:
                mouse = pygame.Vector2(pygame.mouse.get_pos())
                direction = mouse - player.pos
                if direction.length_squared() > 0:
                    direction = direction.normalize()
                    bullets.append(Bullet(player.pos + direction * (PLAYER_RADIUS + 4), direction, "player"))
                    player.ammo -= 1
                    player.last_shot = now

    if not round_over:
        if player.reloading and now >= player.reloading_until:
            player.ammo = MAGAZINE_SIZE
            player.reloading_until = 0.0
            message = "Reload complete."

        keys = pygame.key.get_pressed()
        move = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if move.length_squared() > 0:
            move = move.normalize() * PLAYER_SPEED * dt
            move_with_walls(player.pos, move, PLAYER_RADIUS)

        bot.update(player, dt, now, bullets)

        for bullet in bullets:
            bullet.pos += bullet.velocity * dt

            if not (0 <= bullet.pos.x <= WIDTH and 70 <= bullet.pos.y <= HEIGHT):
                bullet.alive = False
                continue

            if any(circle_hits_rect(bullet.pos, BULLET_RADIUS, wall) for wall in walls):
                bullet.alive = False
                continue

            if bullet.owner == "player":
                if bot.alive and bullet.pos.distance_to(bot.pos) <= bot.radius + BULLET_RADIUS:
                    bot.health = max(0, bot.health - 25)
                    bullet.alive = False
                    if bot.health == 0:
                        bot.alive = False
                        score += 1
                        message = "Enemy eliminated! Press Enter to restart the round."
                    continue

                for target in targets:
                    if target.alive and bullet.pos.distance_to(target.pos) <= target.radius + BULLET_RADIUS:
                        target.health = max(0, target.health - 25)
                        bullet.alive = False
                        if not target.alive:
                            score += 1
                        break
            else:
                if bullet.pos.distance_to(player.pos) <= PLAYER_RADIUS + BULLET_RADIUS:
                    player.health = max(0, player.health - 10)
                    bullet.alive = False
                    if player.health == 0:
                        round_over = True
                        message = "You were eliminated. Press Enter to try again."

        bullets = [b for b in bullets if b.alive]

        if not bot.alive:
            round_over = True
            message = "You won the duel! Press Enter to play again."

    # -------------------- Render --------------------

    screen.fill(BG)
    for x in range(0, WIDTH, 40):
        pygame.draw.line(screen, GRID, (x, 70), (x, HEIGHT))
    for y in range(70, HEIGHT, 40):
        pygame.draw.line(screen, GRID, (0, y), (WIDTH, y))

    pygame.draw.rect(screen, (15, 18, 25), (0, 0, WIDTH, 70))
    draw_text("TACTICAL ARENA", 18, 12, WHITE, large_font)
    draw_text(f"HP  {player.health}", 315, 18, GREEN if player.health > 30 else ENEMY_COLOR)
    draw_text(f"AMMO  {player.ammo}/{MAGAZINE_SIZE}", 440, 18, YELLOW)
    draw_text(f"BOT HP  {bot.health if bot.alive else 0}", 650, 18, ENEMY_COLOR)
    draw_text(f"SCORE  {score}", 850, 18)

    for wall in walls:
        pygame.draw.rect(screen, WALL_COLOR, wall, border_radius=5)
        pygame.draw.rect(screen, (105, 118, 140), wall, width=2, border_radius=5)

    for target in targets:
        if not target.alive:
            pygame.draw.circle(screen, (75, 80, 90), target.pos, target.radius, width=2)
            continue
        pygame.draw.circle(screen, (120, 130, 150), target.pos, target.radius)
        bar = pygame.Rect(target.pos.x - 22, target.pos.y - 31, 44, 6)
        pygame.draw.rect(screen, (65, 40, 45), bar)
        pygame.draw.rect(screen, GREEN, (bar.x, bar.y, bar.width * target.health / 100, bar.height))

    if bot.alive:
        pygame.draw.circle(screen, ENEMY_COLOR, bot.pos, bot.radius)
        pygame.draw.circle(screen, (255, 175, 175), bot.pos, bot.radius, width=2)
        bar = pygame.Rect(bot.pos.x - 24, bot.pos.y - 31, 48, 6)
        pygame.draw.rect(screen, DARK_RED, bar)
        pygame.draw.rect(screen, GREEN, (bar.x, bar.y, bar.width * bot.health / BOT_MAX_HEALTH, bar.height))

    for bullet in bullets:
        pygame.draw.circle(screen, YELLOW if bullet.owner == "player" else ENEMY_COLOR, bullet.pos, BULLET_RADIUS)

    mouse = pygame.Vector2(pygame.mouse.get_pos())
    aim = mouse - player.pos
    if aim.length_squared() > 0:
        aim.scale_to_length(PLAYER_RADIUS + 10)
        pygame.draw.line(screen, WHITE, player.pos, player.pos + aim, 3)

    pygame.draw.circle(screen, PLAYER_COLOR, player.pos, PLAYER_RADIUS)
    pygame.draw.circle(screen, WHITE, player.pos, PLAYER_RADIUS, width=2)

    mx, my = pygame.mouse.get_pos()
    pygame.draw.circle(screen, WHITE, (mx, my), 8, width=1)
    pygame.draw.line(screen, WHITE, (mx - 12, my), (mx - 4, my), 1)
    pygame.draw.line(screen, WHITE, (mx + 4, my), (mx + 12, my), 1)
    pygame.draw.line(screen, WHITE, (mx, my - 12), (mx, my - 4), 1)
    pygame.draw.line(screen, WHITE, (mx, my + 4), (mx, my + 12), 1)

    draw_text(message, 18, HEIGHT - 30, MUTED, small_font)

    if round_over:
        overlay_text = "YOU WIN!" if not bot.alive else "YOU WERE ELIMINATED"
        overlay = large_font.render(overlay_text + " — PRESS ENTER", True, GREEN if not bot.alive else ENEMY_COLOR)
        screen.blit(overlay, overlay.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    pygame.display.flip()

pygame.quit()
sys.exit()
