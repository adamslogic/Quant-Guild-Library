"""High school pygame drag-and-drop scene with a weather toggle.

- Two backgrounds: `nice.png` (sunny) and `stormy.png` (rainy).
- A weather character that swaps between the sun guy (`sunglasse.png`)
  and the rain cloud (`rain.png`).
- Every other image in the folder is a normal draggable prop.

Controls:
  - S                 : sunny weather  -> nice background + sun guy + customers
  - R                 : stormy weather -> stormy background + rain cloud (no customers)
  - M                 : show / hide the money
  - L                 : show / hide the lemonade stand
  - Left click + drag : move an image around
  - SPACE             : reshuffle prop positions
  - ESC / close window: quit
"""

import os
import random
import sys

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))

SUNNY_BG = "nice.png"
STORMY_BG = "stormy.png"
SUN_SPRITE = "sunglasse.png"
RAIN_SPRITE = "rain.png"
CUSTOMERS_SPRITE = "customers.png"
MONEY_SPRITE = "money.png"
LEMONADE_SPRITE = "lemonade_stand.jpg"

# Files handled specially (not treated as generic props).
SPECIAL_FILES = {
    SUNNY_BG,
    STORMY_BG,
    SUN_SPRITE,
    RAIN_SPRITE,
    CUSTOMERS_SPRITE,
    MONEY_SPRITE,
    LEMONADE_SPRITE,
}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

MAX_SPRITE_SIZE = 160
MAX_WEATHER_SIZE = 200


def load_scaled_background(path, size):
    image = pygame.image.load(path).convert()
    return pygame.transform.smoothscale(image, size)


def scale_to_fit(image, max_size):
    w, h = image.get_size()
    scale = min(max_size / w, max_size / h, 1.0)
    if scale < 1.0:
        image = pygame.transform.smoothscale(image, (int(w * scale), int(h * scale)))
    return image


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


def load_image(name, max_size, alpha=True):
    path = os.path.join(HERE, name)
    image = pygame.image.load(path)
    image = image.convert_alpha() if alpha else image.convert()
    return scale_to_fit(image, max_size)


def main():
    pygame.init()
    pygame.display.set_caption("High School - Sunny / Stormy Drag & Drop")

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

    # Weather characters share a position; only the active one is shown.
    sun_guy = Draggable(load_image(SUN_SPRITE, MAX_WEATHER_SIZE), (40, 40))
    rain_cloud = Draggable(load_image(RAIN_SPRITE, MAX_WEATHER_SIZE), (40, 40))
    weather_sprite = {"sunny": sun_guy, "stormy": rain_cloud}

    # Customers only turn up on nice days; money/lemonade are toggled with M/L.
    customers = Draggable(load_image(CUSTOMERS_SPRITE, MAX_SPRITE_SIZE), (0, 0))
    money = Draggable(load_image(MONEY_SPRITE, MAX_SPRITE_SIZE), (0, 0))
    lemonade = Draggable(load_image(LEMONADE_SPRITE, MAX_SPRITE_SIZE), (0, 0))
    show_money = True
    show_lemonade = True

    # Generic draggable props (everything else in the folder).
    props = []
    for name in sorted(os.listdir(HERE)):
        if name in SPECIAL_FILES:
            continue
        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue
        try:
            image = load_image(name, MAX_SPRITE_SIZE)
        except pygame.error:
            continue
        props.append(Draggable(image, (0, 0)))

    random_positions(props + [customers, money, lemonade], screen_size)

    def active_sprites():
        # Draw order: props, conditional extras, weather on top.
        sprites = list(props)
        if show_lemonade:
            sprites.append(lemonade)
        if weather == "sunny":
            sprites.append(customers)
        if show_money:
            sprites.append(money)
        sprites.append(weather_sprite[weather])
        return sprites

    def set_weather(new_weather):
        nonlocal weather
        if new_weather == weather:
            return
        # Swap the new character into the old one's position.
        old = weather_sprite[weather]
        new = weather_sprite[new_weather]
        new.rect.topleft = old.rect.topleft
        old.stop_drag()
        weather = new_weather
        if weather != "sunny":
            customers.stop_drag()

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
                all_movable = props + [sun_guy, rain_cloud, customers, money, lemonade]
                for sprite in all_movable:
                    sprite.rect.x = int(sprite.rect.x * sx)
                    sprite.rect.y = int(sprite.rect.y * sy)
                screen_size = new_size
                screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
                backgrounds = {
                    "sunny": load_scaled_background(sunny_path, screen_size),
                    "stormy": load_scaled_background(stormy_path, screen_size),
                }
                clamp_positions(all_movable, screen_size)
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
                        money.stop_drag()
                elif event.key == pygame.K_l:
                    show_lemonade = not show_lemonade
                    if not show_lemonade:
                        lemonade.stop_drag()
                elif event.key == pygame.K_SPACE:
                    random_positions(props, screen_size)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for sprite in reversed(active_sprites()):
                    if sprite.rect.collidepoint(event.pos):
                        sprite.start_drag(event.pos)
                        if sprite in props:
                            props.remove(sprite)
                            props.append(sprite)
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
