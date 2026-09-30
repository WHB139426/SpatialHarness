"""Top-down camera and a screen-visible marker for the first-person pose."""

import math

import bpy
from mathutils import Matrix, Vector


def _material(name, color):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*color, 1)
    emission.inputs['Strength'].default_value = 2
    material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    return material


def _mesh(name, vertices, faces, material, parent):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(material)
    return obj


class OverheadView:
    def __init__(self, scene, corners, center, up):
        self.scene = scene
        self.corners = corners
        self.center = center
        self.up = up.normalized()
        reference = Vector((1, 0, 0)) if abs(self.up.x) < .99 else Vector((0, 1, 0))
        self.right = (reference - self.up * reference.dot(self.up)).normalized()
        self.screen_up = self.up.cross(self.right).normalized()

        data = bpy.data.cameras.new('Overhead map camera')
        data.type = 'ORTHO'
        data.clip_start = .001
        camera = bpy.data.objects.new('Overhead map camera', data)
        bpy.context.collection.objects.link(camera)
        camera.rotation_euler = Matrix((self.right, self.screen_up, self.up)).transposed().to_euler()
        self.camera = camera

        self.marker = bpy.data.objects.new('First-person position and heading', None)
        bpy.context.collection.objects.link(self.marker)
        self.marker.parent = camera
        orange = _material('Overhead position orange', (1, .42, .02))
        cyan = _material('Overhead direction cyan', (.02, .85, 1))
        segments = 24
        disk = [(0, 0, 0)] + [
            (.3 * math.cos(2 * math.pi * i / segments),
             .3 * math.sin(2 * math.pi * i / segments), 0)
            for i in range(segments)]
        _mesh('First-person position', disk,
              [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)],
              orange, self.marker)
        _mesh('First-person heading',
              [(-.13, .08, 0), (.13, .08, 0), (.13, .9, 0),
               (.45, .9, 0), (0, 1.55, 0), (-.45, .9, 0), (-.13, .9, 0)],
              [(0, 1, 2, 3, 4, 5, 6)], cyan, self.marker)
        self.marker.hide_render = True

    def update(self, position, forward):
        """Frame the whole cloud and project the first-person pose onto its map."""
        points = list(self.corners) + [position]
        horizontal = [(p - self.center).dot(self.right) for p in points]
        vertical = [(p - self.center).dot(self.screen_up) for p in points]
        x_mid = (min(horizontal) + max(horizontal)) / 2
        y_mid = (min(vertical) + max(vertical)) / 2
        span = max(max(horizontal) - min(horizontal),
                   max(vertical) - min(vertical), .01)
        self.camera.data.ortho_scale = span * 1.25
        self.camera.location = (self.center + self.right * x_mid
                                + self.screen_up * y_mid + self.up * (span * 2 + 1))
        self.camera.data.clip_end = span * 5 + 10

        x = (position - self.center).dot(self.right) - x_mid
        y = (position - self.center).dot(self.screen_up) - y_mid
        self.marker.location = (x, y, -.05)
        scale = self.camera.data.ortho_scale * .025
        self.marker.scale = (scale, scale, scale)
        heading_x = forward.dot(self.right)
        heading_y = forward.dot(self.screen_up)
        if math.hypot(heading_x, heading_y) > 1e-8:
            self.marker.rotation_euler.z = math.atan2(-heading_x, heading_y)
