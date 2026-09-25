"""Grad school pygame drag-and-drop scene.

- Background: `nice.png`.
- M toggles four separate money images at once.
- Two baskets are shown by default.
- Every other image in the folder is a normal draggable prop.

Controls:
  - M                 : show / hide the four money images
  - Left click + drag : move an image around
  - SPACE             : reshuffle prop positions
  - ESC / close window: quit
"""

import os
import random
import sys

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))

BACKGROUND = "nice.png"
MONEY_SPRITE = "money.png"
BASKET_SPRITE = "basket.png"

MONEY_COUNT = 4
BASKET_COUNT = 2

# Files handled specially (not treated as generic props).
SPECIAL_FILES = {BACKGROUND, MONEY_SPRITE, BASKET_SPRITE}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

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
    pygame.display.set_caption("Grad School - Drag & Drop")

    bg_path = os.path.join(HERE, BACKGROUND)
    if not os.path.exists(bg_path):
        print(f"Background '{BACKGROUND}' not found in {HERE}")
        sys.exit(1)

    raw_bg = pygame.image.load(bg_path)
    screen_size = raw_bg.get_size()
    screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
    background = load_scaled_background(bg_path, screen_size)

    # Four money images toggled together with M.
    money_image = load_image(MONEY_SPRITE, MAX_SPRITE_SIZE)
    moneys = [Draggable(money_image, (0, 0)) for _ in range(MONEY_COUNT)]
    show_money = True

    # Two baskets shown by default.
    basket_image = load_image(BASKET_SPRITE, MAX_SPRITE_SIZE)
    baskets = [Draggable(basket_image, (0, 0)) for _ in range(BASKET_COUNT)]

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

    # Baskets are always-on props; moneys are toggled separately.
    props.extend(baskets)

    random_positions(props + moneys, screen_size)

    def active_sprites():
        sprites = list(props)
        if show_money:
            sprites.extend(moneys)
        return sprites

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
                all_movable = props + moneys
                for sprite in all_movable:
                    sprite.rect.x = int(sprite.rect.x * sx)
                    sprite.rect.y = int(sprite.rect.y * sy)
                screen_size = new_size
                screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
                background = load_scaled_background(bg_path, screen_size)
                clamp_positions(all_movable, screen_size)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_m:
                    show_money = not show_money
                    if not show_money:
                        for m in moneys:
                            m.stop_drag()
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

        screen.blit(background, (0, 0))
        for sprite in active_sprites():
            sprite.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
