"""Camera state and actions shared by frontends."""

import copy
import math

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
        self.planning = {'target': None, 'look_at': None, 'route': []}
        self._undo_state = None

    def _commit(self, candidate, command, *, reset=False, planning=None, fresh=False):
        planning = self.planning if planning is None else planning
        paths = copy.deepcopy(self.path_segments)
        if fresh:
            paths = [[candidate['position'][:]]]
        elif reset:
            paths.append([candidate['position'][:]])
        elif candidate['position'] != self.state['position']:
            paths[-1].append(candidate['position'][:])
        try:
            self.navigator.apply(candidate)
            record = self.renderer.render(candidate, command, paths, planning)
        except Exception:
            self.navigator.apply(self.state)
            raise
        self.path_segments = paths
        self.state = candidate
        self.planning = planning
        return record

    def _map_point(self, point, observation_id):
        if (type(observation_id) is not int or observation_id != self.renderer.index
                or self.renderer.map_frame is None):
            raise ValueError('Use the observation_id of the latest rendered top-down image.')
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                       for v in point)):
            raise ValueError('A map point must be [x, y] with finite numbers in [0, 1]; origin is top-left.')
        return list(self.renderer.overhead.unproject(point, self.renderer.map_frame))

    def set_target(self, observation_id, point, look_at=None):
        # Setting a new target discards the previous route; null clears the whole plan.
        planning = {'target': None, 'look_at': None, 'route': []}
        if point is None:
            if look_at is not None:
                raise ValueError('look_at requires a target point.')
            self._map_point([.5, .5], observation_id)
        else:
            planning['target'] = self._map_point(point, observation_id)
            if look_at is not None:
                planning['look_at'] = self._map_point(look_at, observation_id)
        return self._commit(self.state, 'set_target', planning=planning)

    def set_route(self, observation_id, points):
        if not isinstance(points, list):
            raise ValueError('points must be an ordered list of [x, y] map points.')
        self._map_point([.5, .5], observation_id)
        route = [self._map_point(point, observation_id) for point in points]
        if route:
            route.insert(0, self.state['position'][:])
        planning = {**self.planning, 'route': route}
        return self._commit(self.state, 'set_route', planning=planning)

    def status(self):
        return copy.deepcopy(self.state)

    def observe(self, command='observe'):
        return self._commit(self.state, command)

    def reset(self, *, fresh=False):
        """Restore the initial pose; fresh also clears movement history and planning."""
        planning = {'target': None, 'look_at': None, 'route': []} if fresh else None
        record = self._commit(self.navigator.initial.copy(), 'new' if fresh else 'reset',
                              reset=True, planning=planning, fresh=fresh)
        self._undo_state = None
        return record

    def start_session(self, output):
        """Start a clean exploration in a new output directory using the loaded scene."""
        with self.renderer.new_session(output):
            return self.reset(fresh=True)

    def execute(self, key, magnitude=None, label=None):
        if key == 'undo':
            if magnitude is not None:
                raise ValueError('undo does not accept a magnitude.')
            if self._undo_state is None:
                raise ValueError('No camera action is available to undo.')
            record = self._commit(copy.deepcopy(self._undo_state), 'undo')
            self._undo_state = None
            return record
        candidate = self.navigator.step(self.state, key, magnitude)
        if label is None:
            label = key if magnitude is None else f'{key}{magnitude:g}'
        previous = copy.deepcopy(self.state)
        record = self._commit(candidate, label)
        self._undo_state = previous
        return record
