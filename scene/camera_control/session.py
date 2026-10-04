"""Camera state and actions shared by frontends."""

import copy

from .navigation import Navigator


class CameraSession:
    """Commit a camera action only after its observation has rendered."""

    def __init__(self, renderer, *, position, direction, point_radius, move_step, look_step, point_step):
        self.renderer = renderer
        self.navigator = Navigator(
            renderer.camera, renderer.point_nodes, renderer.center, renderer.extent, renderer.up,
            point_radius if renderer.point_nodes else None,
            move_step, look_step, point_step, position, direction,
        )
        self.state = self.navigator.initial.copy()

    def _commit(self, candidate, command):
        try:
            self.navigator.apply(candidate)
            record = self.renderer.render(candidate, command)
        except Exception:
            self.navigator.apply(self.state)
            raise
        self.state = candidate
        return record

    def status(self):
        return copy.deepcopy(self.state)

    def observe(self, command='observe'):
        return self._commit(self.state, command)

    def reset(self):
        return self._commit(self.navigator.initial.copy(), 'reset')

    def execute(self, key, magnitude=None, label=None):
        candidate = self.navigator.step(self.state, key, magnitude)
        if label is None:
            label = key if magnitude is None else f'{key}{magnitude:g}'
        return self._commit(candidate, label)
