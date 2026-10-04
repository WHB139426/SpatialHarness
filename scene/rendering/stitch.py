"""Combine two Blender renders and the nearest captured video frame into one PNG."""

from array import array
from pathlib import Path

import bpy


def stitch_views(first_path, overhead_path, reference_path, output_path):
    images = []
    try:
        assets = Path(__file__).resolve().parents[2] / 'assets'
        paths = (first_path, overhead_path, reference_path,
                 assets / 'first_person_label.png', assets / 'nearest_video_label.png')
        for path in paths:
            images.append(bpy.data.images.load(str(path), check_existing=False))
        first, overhead, reference, first_label, reference_label = images
        width, height = overhead.size
        output_row = width * 12
        reference_scale = min(width / reference.size[0], height / reference.size[1])
        reference.scale(max(1, round(reference.size[0] * reference_scale)),
                        max(1, round(reference.size[1] * reference_scale)))
        combined_pixels = array('f', (0.02, 0.02, 0.02, 1.0)) * (width * 3 * height)

        def paste(image, x, y):
            image_width, image_height = image.size
            row = image_width * 4
            pixels = array('f', [0]) * (row * image_height)
            image.pixels.foreach_get(pixels)
            for offset in range(image_height):
                source = offset * row
                target = (y + offset) * output_row + x * 4
                combined_pixels[target:target + row] = pixels[source:source + row]

        for panel, image in enumerate((first, overhead, reference)):
            image_width, image_height = image.size
            paste(image, panel * width + (width - image_width) // 2,
                  (height - image_height) // 2)

        for panel, label in ((0, first_label), (2, reference_label)):
            label_scale = width / 960
            label.scale(max(1, round(label.size[0] * label_scale)),
                        max(1, round(label.size[1] * label_scale)))
            label_x = panel * width + max(1, round(width * .02))
            label_y = height - label.size[1] - max(1, round(height * .02))
            paste(label, label_x, label_y)

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
