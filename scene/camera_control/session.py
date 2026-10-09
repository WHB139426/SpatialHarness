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
        self.path_segments = [[self.state['position'][:]]]

    def _commit(self, candidate, command, *, reset=False):
        paths = copy.deepcopy(self.path_segments)
        if reset:
            paths.append([candidate['position'][:]])
        elif candidate['position'] != self.state['position']:
            paths[-1].append(candidate['position'][:])
        try:
            self.navigator.apply(candidate)
            record = self.renderer.render(candidate, command, paths)
        except Exception:
            self.navigator.apply(self.state)
            raise
        self.path_segments = paths
        self.state = candidate
        return record

    def status(self):
        return copy.deepcopy(self.state)

    def observe(self, command='observe'):
        return self._commit(self.state, command)

    def reset(self):
        return self._commit(self.navigator.initial.copy(), 'reset', reset=True)

    def execute(self, key, magnitude=None, label=None):
        candidate = self.navigator.step(self.state, key, magnitude)
        if label is None:
            label = key if magnitude is None else f'{key}{magnitude:g}'
        return self._commit(candidate, label)
