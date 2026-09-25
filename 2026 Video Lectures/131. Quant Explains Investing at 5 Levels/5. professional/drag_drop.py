"""Professional pygame drag-and-drop scene with a weather toggle.

- Two backgrounds: `nice.png` (sunny) and `stormy.png` (rainy).
- Only the Goldman (`gslogo.png`), Apple (`aapl.png`) and Cigna (`cigna.png`)
  logos are shown, in both weather states.
- On stormy weather (R) the three logos get a red overlay.
- Three baskets and the stick guy are shown by default.
- M toggles three money images.

Controls:
  - S                 : sunny weather  -> nice background, normal logos
  - R                 : stormy weather -> stormy background, red-tinted logos
  - M                 : show / hide three money images
  - Left click + drag : move an image around
  - SPACE             : reshuffle positions
  - ESC / close window: quit
"""

import os
import sys
import random

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))

SUNNY_BG = "nice.png"
STORMY_BG = "stormy.png"
BASKET_SPRITE = "basket.png"
STICK_SPRITE = "stick_guy.jpg"
MONEY_SPRITE = "money.png"
LOGO_FILES = ["gslogo.png", "aapl.png", "cigna.png"]

BASKET_COUNT = 3
MONEY_COUNT = 3
RED_OPACITY = 150  # 0-255 strength of the red overlay on stormy days

MAX_SPRITE_SIZE = 160


def load_scaled_background(path, size):
    image = pygame.image.load(path).convert()
    return pygame.transform.smoothscale(image, size)


def scale_to_fit(image, max_size):
    w, h = image.get_size()
    scale = min(max_size / w, max_size / h, 1.0)
    if scale < 1.0:
        image = pygame.transform.smoothscale(image, (int(w * scale), int(h * scale)))
    return image


def load_image(name, max_size, alpha=True):
    path = os.path.join(HERE, name)
    image = pygame.image.load(path)
    image = image.convert_alpha() if alpha else image.convert()
    return scale_to_fit(image, max_size)


def make_red_version(image, opacity=RED_OPACITY):
    """Return a copy of `image` with a translucent red overlay that
    follows the image's own shape (transparent pixels stay transparent)."""
    result = image.copy()
    red = image.copy()
    # Tint toward red by knocking down the green/blue channels.
    red.fill((255, 30, 30, 255), special_flags=pygame.BLEND_RGBA_MULT)
    # Scale the overlay's alpha down to the desired opacity (masked by shape).
    red.fill((255, 255, 255, opacity), special_flags=pygame.BLEND_RGBA_MULT)
    result.blit(red, (0, 0))
    return result


class Draggable:
    def __init__(self, image, pos):
        self.image = image
        self.rect = image.get_rect(topleft=pos)
        self.dragging = False
        self.grab_offset = (0, 0)

    def start_drag(self, mouse_pos):
        self.dragging = True
        self.grab_offset = (self.rect.x - mouse_pos[0], self.rect.y - mouse_pos[1])

    def stop_drag(self):
        self.dragging = False

    def update_drag(self, mouse_pos):
        if self.dragging:
            self.rect.x = mouse_pos[0] + self.grab_offset[0]
            self.rect.y = mouse_pos[1] + self.grab_offset[1]

    def draw(self, surface):
        surface.blit(self.image, self.rect)


class Logo(Draggable):
    """A draggable logo that swaps between a normal and red-tinted image."""

    def __init__(self, normal, red, pos):
        super().__init__(normal, pos)
        self.normal = normal
        self.red = red

    def set_stormy(self, stormy):
        self.image = self.red if stormy else self.normal


def random_positions(sprites, screen_size):
    screen_w, screen_h = screen_size
    for sprite in sprites:
        max_x = max(0, screen_w - sprite.rect.width)
        max_y = max(0, screen_h - sprite.rect.height)
        sprite.rect.topleft = (random.randint(0, max_x), random.randint(0, max_y))


def clamp_positions(sprites, screen_size):
    screen_w, screen_h = screen_size
    for sprite in sprites:
        max_x = max(0, screen_w - sprite.rect.width)
        max_y = max(0, screen_h - sprite.rect.height)
        sprite.rect.x = min(max(0, sprite.rect.x), max_x)
        sprite.rect.y = min(max(0, sprite.rect.y), max_y)


def main():
    pygame.init()
    pygame.display.set_caption("Professional - Sunny / Stormy Portfolio")

    sunny_path = os.path.join(HERE, SUNNY_BG)
    stormy_path = os.path.join(HERE, STORMY_BG)
    for path in (sunny_path, stormy_path):
        if not os.path.exists(path):
            print(f"Required background missing: {path}")
            sys.exit(1)

    raw_bg = pygame.image.load(sunny_path)
    screen_size = raw_bg.get_size()
    screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)

    backgrounds = {
        "sunny": load_scaled_background(sunny_path, screen_size),
        "stormy": load_scaled_background(stormy_path, screen_size),
    }
    weather = "sunny"

    # Three baskets shown by default.
    basket_image = load_image(BASKET_SPRITE, MAX_SPRITE_SIZE)
    baskets = [Draggable(basket_image, (0, 0)) for _ in range(BASKET_COUNT)]

    # Stick guy shown by default.
    stick_guy = Draggable(load_image(STICK_SPRITE, MAX_SPRITE_SIZE), (0, 0))

    # Only the Goldman / Apple / Cigna logos, each with a red variant.
    logos = []
    for name in LOGO_FILES:
        normal = load_image(name, MAX_SPRITE_SIZE)
        logos.append(Logo(normal, make_red_version(normal), (0, 0)))

    # Three money images toggled with M.
    money_image = load_image(MONEY_SPRITE, MAX_SPRITE_SIZE)
    moneys = [Draggable(money_image, (0, 0)) for _ in range(MONEY_COUNT)]
    show_money = True

    # Baskets drawn first so the logos sit on top of them.
    sprites = baskets + [stick_guy] + logos
    random_positions(sprites + moneys, screen_size)

    def active_sprites():
        return sprites + moneys if show_money else list(sprites)

    def set_weather(new_weather):
        nonlocal weather
        weather = new_weather
        stormy = weather == "stormy"
        for logo in logos:
            logo.set_stormy(stormy)

    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                new_size = (max(1, event.w), max(1, event.h))
                sx = new_size[0] / screen_size[0]
                sy = new_size[1] / screen_size[1]
                for sprite in sprites + moneys:
                    sprite.rect.x = int(sprite.rect.x * sx)
                    sprite.rect.y = int(sprite.rect.y * sy)
                screen_size = new_size
                screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
                backgrounds = {
                    "sunny": load_scaled_background(sunny_path, screen_size),
                    "stormy": load_scaled_background(stormy_path, screen_size),
                }
                clamp_positions(sprites + moneys, screen_size)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    set_weather("sunny")
                elif event.key == pygame.K_r:
                    set_weather("stormy")
                elif event.key == pygame.K_m:
                    show_money = not show_money
                    if not show_money:
                        for m in moneys:
                            m.stop_drag()
                elif event.key == pygame.K_SPACE:
                    random_positions(active_sprites(), screen_size)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for sprite in reversed(active_sprites()):
                    if sprite.rect.collidepoint(event.pos):
                        sprite.start_drag(event.pos)
                        target = moneys if sprite in moneys else sprites
                        target.remove(sprite)
                        target.append(sprite)
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for sprite in active_sprites():
                    sprite.stop_drag()
            elif event.type == pygame.MOUSEMOTION:
                for sprite in active_sprites():
                    sprite.update_drag(event.pos)

        screen.blit(backgrounds[weather], (0, 0))
        for sprite in active_sprites():
            sprite.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
