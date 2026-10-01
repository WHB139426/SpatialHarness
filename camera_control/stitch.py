"""Combine two Blender renders and the nearest captured video frame into one PNG."""

from array import array
from pathlib import Path

import bpy


def stitch_views(first_path, overhead_path, reference_path, output_path):
    images = []
    try:
        assets = Path(__file__).resolve().parents[1] / 'assets'
        paths = (first_path, overhead_path, reference_path,
                 assets / 'first_person_label.png', assets / 'nearest_video_label.png')
        for path in paths:
            images.append(bpy.data.images.load(str(path), check_existing=False))
        first, overhead, reference, first_label, reference_label = images
        width, height = overhead.size
        panel_row = width * 4
        output_row = panel_row * 3

        first_scale = min(1.0, width / first.size[0], height / first.size[1])
        if first_scale < 1.0:
            first.scale(max(1, round(first.size[0] * first_scale)),
                        max(1, round(first.size[1] * first_scale)))
        first_width, first_height = first.size
        first_pixels = array('f', [0]) * (first_width * first_height * 4)
        overhead_pixels = array('f', [0]) * (panel_row * height)
        first.pixels.foreach_get(first_pixels)
        overhead.pixels.foreach_get(overhead_pixels)

        reference_scale = min(width / reference.size[0], height / reference.size[1])
        reference.scale(max(1, round(reference.size[0] * reference_scale)),
                        max(1, round(reference.size[1] * reference_scale)))
        reference_width, reference_height = reference.size
        reference_pixels = array('f', [0]) * (reference_width * reference_height * 4)
        reference.pixels.foreach_get(reference_pixels)

        combined_pixels = array('f', [0]) * (output_row * height)
        background = array('f', (0.02, 0.02, 0.02, 1.0)) * width
        for y in range(height):
            source = y * panel_row
            target = y * output_row
            combined_pixels[target:target + panel_row] = background
            combined_pixels[target + panel_row:target + 2 * panel_row] = overhead_pixels[source:source + panel_row]
            combined_pixels[target + 2 * panel_row:target + 3 * panel_row] = background

        first_x = (width - first_width) // 2
        first_y = (height - first_height) // 2
        for y in range(first_height):
            source = y * first_width * 4
            target = (first_y + y) * output_row + first_x * 4
            combined_pixels[target:target + first_width * 4] = first_pixels[source:source + first_width * 4]

        reference_x = (width - reference_width) // 2
        reference_y = (height - reference_height) // 2
        for y in range(reference_height):
            source = y * reference_width * 4
            target = (reference_y + y) * output_row + (2 * width + reference_x) * 4
            combined_pixels[target:target + reference_width * 4] = reference_pixels[source:source + reference_width * 4]

        for panel, label in ((0, first_label), (2, reference_label)):
            label_scale = width / 960
            label.scale(max(1, round(label.size[0] * label_scale)),
                        max(1, round(label.size[1] * label_scale)))
            label_width, label_height = label.size
            label_pixels = array('f', [0]) * (label_width * label_height * 4)
            label.pixels.foreach_get(label_pixels)
            label_x = panel * width + max(1, round(width * .02))
            label_y = height - label_height - max(1, round(height * .02))
            for y in range(label_height):
                source = y * label_width * 4
                target = (label_y + y) * output_row + label_x * 4
                combined_pixels[target:target + label_width * 4] = label_pixels[source:source + label_width * 4]

        combined = bpy.data.images.new('First-person, overhead, and video frame',
                                       width=width * 3, height=height, alpha=True)
        images.append(combined)
        combined.pixels.foreach_set(combined_pixels)
        combined.filepath_raw = str(output_path)
        combined.file_format = 'PNG'
        combined.save()
    finally:
        for image in images:
            bpy.data.images.remove(image)
