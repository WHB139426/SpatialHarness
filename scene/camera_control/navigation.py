"""First-person camera orientation and horizontal walking controls."""

import math

from mathutils import Matrix, Vector

from .actions import MAGNITUDE_KEYS, SIMPLE_KEYS

MOVEMENT = {'w': (0, 0, -1), 's': (0, 0, 1),
            'a': (-1, 0, 0), 'd': (1, 0, 0)}


class Navigator:
    def __init__(self, camera, point_nodes, center, extent, up,
                 radius, move_step, look_step, point_step, position, direction):
        self.camera = camera
        self.point_nodes = point_nodes
        self.center = center
        self.extent = extent
        self.up = up
        self.move_step = move_step
        self.look_step = look_step
        self.point_step = point_step
        reference = Vector((1, 0, 0)) if abs(up.x) < .99 else Vector((0, 1, 0))
        self.horizontal_x = (reference - up * reference.dot(up)).normalized()
        self.horizontal_y = up.cross(self.horizontal_x).normalized()

        horizontal = direction - up * direction.dot(up)
        if horizontal.length < 1e-8:
            horizontal = self.horizontal_x
        yaw = math.degrees(math.atan2(horizontal.dot(self.horizontal_y),
                                      horizontal.dot(self.horizontal_x))) % 360
        self.initial = {'position': list(position), 'yaw': yaw, 'pitch': 0.0,
                        'point_radius': radius}
        self.apply(self.initial)

    def forward(self, state):
        yaw, pitch = math.radians(state['yaw']), math.radians(state['pitch'])
        return (self.horizontal_x * (math.cos(pitch) * math.cos(yaw))
                + self.horizontal_y * (math.cos(pitch) * math.sin(yaw))
                + self.up * math.sin(pitch)).normalized()

    def apply(self, state):
        for points in self.point_nodes:
            points.inputs['Radius'].default_value = state['point_radius']
        backward = -self.forward(state)
        right = self.up.cross(backward).normalized()
        screen_up = backward.cross(right).normalized()
        self.camera.location = Vector(state['position'])
        self.camera.rotation_euler = Matrix((right, screen_up, backward)).transposed().to_euler()
        self.camera.data.clip_end = max(
            self.extent * 20, (self.camera.location - self.center).length + self.extent * 2)

    def step(self, state, key, magnitude=None):
        if key not in MAGNITUDE_KEYS | SIMPLE_KEYS:
            raise ValueError(f'Unknown camera action: {key!r}')
        if magnitude is not None and key not in MAGNITUDE_KEYS:
            raise ValueError('Only movement and look keys accept a magnitude')
        if magnitude is not None and (not math.isfinite(magnitude) or magnitude <= 0):
            raise ValueError('Action magnitude must be finite and positive')
        candidate = state.copy()
        if key in MOVEMENT:
            forward = self.forward(candidate)
            forward = (forward - self.up * forward.dot(self.up)).normalized()
            right = forward.cross(self.up).normalized()
            x, _, z = MOVEMENT[key]
            delta = (right * x - forward * z) * (self.move_step if magnitude is None else magnitude)
            candidate['position'] = list(Vector(candidate['position']) + delta)
        elif key in ('q', 'e'):
            direction = 1 if key == 'e' else -1
            candidate['position'] = list(Vector(candidate['position'])
                                         + self.up * (direction * self.move_step))
        elif key in ('+', '-'):
            if not self.point_nodes:
                raise ValueError('Point size applies only to point clouds')
            direction = 1 if key == '+' else -1
            next_radius = round(candidate['point_radius'] + direction * self.point_step, 6)
            if next_radius <= 0:
                raise ValueError('Point radius must stay positive')
            candidate['point_radius'] = next_radius
        else:
            turns = {'j': ('yaw', 1), 'l': ('yaw', -1),
                     'i': ('pitch', 1), 'k': ('pitch', -1)}
            angle, direction = turns[key]
            candidate[angle] += direction * (self.look_step if magnitude is None else magnitude)
            if angle == 'pitch' and not -89.9 <= candidate['pitch'] <= 89.9:
                raise ValueError('Pitch must stay between -89.9 and 89.9 degrees')
            if angle == 'yaw':
                candidate['yaw'] %= 360
        return candidate
