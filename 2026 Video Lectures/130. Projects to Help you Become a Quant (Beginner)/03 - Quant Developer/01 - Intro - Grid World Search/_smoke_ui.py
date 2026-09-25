"""Headless smoke test for the pygame UI (no visible window).

Uses SDL's 'dummy' video driver so the whole render + interaction path runs in
CI without a display. Not part of the shipped project's core tests -- it is a
belt-and-braces check that main.py's rendering code executes without exceptions.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import main  # noqa: E402


def run() -> None:
    app = main.GridWorldApp()

    # Exercise grid editing helpers.
    app.grid.generate_maze(app.rng)
    app.grid.scatter_weights(rng=app.rng)

    # Run each algorithm to completion through the animation driver + renderer.
    for key in ("bfs", "dfs", "dijkstra", "astar", "greedy"):
        app.algo_key = key
        app.start_search()
        frames = 0
        while not app.done and frames < 5000:
            app._advance(32)
            app.draw()
            frames += 1
        assert app.done, f"{key} did not finish within frame budget"
        print(f"ok  {key}: done={app.done} found={app.found} "
              f"expanded={app.expanded} path={max(0, len(app.path) - 1)} steps "
              f"frames={frames}")

    # Exercise a few synthetic events (keys + mouse) to hit those code paths.
    def key(k):
        return pygame.event.Event(pygame.KEYDOWN, {"key": k, "mod": 0, "unicode": ""})

    for k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
              pygame.K_m, pygame.K_g, pygame.K_c, pygame.K_w, pygame.K_h,
              pygame.K_UP, pygame.K_DOWN, pygame.K_r, pygame.K_SPACE):
        assert app.handle_event(key(k)) is True
    app.draw()

    # Mouse: paint a wall then erase it.
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (main.MARGIN + 5 * main.CELL,
                                                               main.MARGIN + 5 * main.CELL),
                                                       "button": 1})
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (0, 0), "button": 1})
    app.handle_event(down)
    app.handle_event(up)
    app.draw()

    pygame.quit()
    print("\nUI smoke test passed: rendering + events ran with no exceptions.")


if __name__ == "__main__":
    run()
