"""Camera-fixed English labels for the two rendered views."""

from pathlib import Path

import bpy



def _emission(name, color):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    shader = nodes.new('ShaderNodeEmission')
    shader.inputs['Color'].default_value = (*color, 1)
    material.node_tree.links.new(shader.outputs[0], output.inputs['Surface'])
    return material


class ViewLabel:
    def __init__(self, camera, scene, title):
        self.root = bpy.data.objects.new(f'{title} label', None)
        scene.collection.objects.link(self.root)
        self.root.parent = camera

        letters = bpy.data.curves.new(f'{title} text', 'FONT')
        letters.body = title
        letters.size = .055
        letters.materials.append(_emission(f'{title} white text', (1, 1, 1)))
        font_file = Path(__file__).resolve().parents[1] / 'assets' / 'fonts' / 'DejaVuSans-Bold.ttf'
        letters.font = bpy.data.fonts.load(str(font_file), check_existing=True)
        text = bpy.data.objects.new(f'{title} text', letters)
        scene.collection.objects.link(text)
        text.parent = self.root
        text.location.z = .001  # Closer to the camera than the panel.
        bpy.context.view_layer.update()

        right = text.dimensions.x + .012
        top = max(.038, text.dimensions.y + .008)
        background = bpy.data.meshes.new(f'{title} label background')
        background.from_pydata(
            [(-.008, -.010, 0), (right, -.010, 0),
             (right, top, 0), (-.008, top, 0)],
            [], [(0, 1, 2, 3)])
        background.update()
        background.materials.append(_emission(f'{title} dark background', (.012, .012, .012)))
        panel = bpy.data.objects.new(f'{title} label background', background)
        scene.collection.objects.link(panel)
        panel.parent = self.root

    def update(self, frame_width, depth):
        self.root.location = (-.47 * frame_width, .43 * frame_width, -depth)
        self.root.scale = (frame_width,) * 3
