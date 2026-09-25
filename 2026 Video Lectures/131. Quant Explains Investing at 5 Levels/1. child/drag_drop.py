"""Simple pygame drag-and-drop scene.

- Uses `class.png` as the background.
- Every other image in this folder becomes a draggable sprite,
  placed at a random position on screen.

Controls:
  - Left click + drag : move an image around
  - R                 : reshuffle image positions
  - ESC / close window: quit
"""

import os
import random
import sys

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
BACKGROUND_NAME = "class.png"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

# Longest side (in pixels) each draggable image is scaled to fit within.
MAX_SPRITE_SIZE = 160


def load_scaled_background(path, size):
    """Load the background and scale it to fill the window."""
    image = pygame.image.load(path).convert()
    return pygame.transform.smoothscale(image, size)


def scale_to_fit(image, max_size):
    """Scale an image down so its longest side is at most `max_size`."""
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
    """Keep every sprite fully inside the current window bounds."""
    screen_w, screen_h = screen_size
    for sprite in sprites:
        max_x = max(0, screen_w - sprite.rect.width)
        max_y = max(0, screen_h - sprite.rect.height)
        sprite.rect.x = min(max(0, sprite.rect.x), max_x)
        sprite.rect.y = min(max(0, sprite.rect.y), max_y)


def main():
    pygame.init()
    pygame.display.set_caption("Child - Drag & Drop Classroom")

    bg_path = os.path.join(HERE, BACKGROUND_NAME)
    if not os.path.exists(bg_path):
        print(f"Background '{BACKGROUND_NAME}' not found in {HERE}")
        sys.exit(1)

    # Size the window to the background's native dimensions; allow resizing.
    raw_bg = pygame.image.load(bg_path)
    screen_size = raw_bg.get_size()
    screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)

    background = load_scaled_background(bg_path, screen_size)

    # Collect every other image in the folder as a draggable sprite.
    sprites = []
    for name in sorted(os.listdir(HERE)):
        if name == BACKGROUND_NAME:
            continue
        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue
        path = os.path.join(HERE, name)
        try:
            image = pygame.image.load(path).convert_alpha()
        except pygame.error:
            continue
        image = scale_to_fit(image, MAX_SPRITE_SIZE)
        sprites.append(Draggable(image, (0, 0)))

    random_positions(sprites, screen_size)

    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                new_size = (max(1, event.w), max(1, event.h))
                # Scale sprite positions proportionally to the new window size.
                sx = new_size[0] / screen_size[0]
                sy = new_size[1] / screen_size[1]
                for sprite in sprites:
                    sprite.rect.x = int(sprite.rect.x * sx)
                    sprite.rect.y = int(sprite.rect.y * sy)
                screen_size = new_size
                screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
                background = load_scaled_background(bg_path, screen_size)
                clamp_positions(sprites, screen_size)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    random_positions(sprites, screen_size)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Topmost sprite (drawn last) gets priority.
                for sprite in reversed(sprites):
                    if sprite.rect.collidepoint(event.pos):
                        sprite.start_drag(event.pos)
                        # Bring to front so it draws on top while dragging.
                        sprites.remove(sprite)
                        sprites.append(sprite)
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for sprite in sprites:
                    sprite.stop_drag()
            elif event.type == pygame.MOUSEMOTION:
                for sprite in sprites:
                    sprite.update_drag(event.pos)

        screen.blit(background, (0, 0))
        for sprite in sprites:
            sprite.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
