"""Camera tools and internal media attachments for a running camera client."""

import mimetypes
from pathlib import Path

from .types import Tool, ToolOutput


def _view_media(path: str) -> ToolOutput:
    media_path = Path(path).expanduser().resolve(strict=True)
    if not media_path.is_file():
        raise ValueError(f"media path is not a file: {media_path}")
    mime_type = mimetypes.guess_type(media_path)[0] or ""
    if mime_type.startswith("image/"):
        content_type = "image_url"
    elif mime_type.startswith("video/"):
        content_type = "video_url"
    else:
        raise ValueError(f"unsupported media type: {mime_type or media_path.suffix}")
    return ToolOutput(
        value={"path": str(media_path), "mime_type": mime_type, "attached": True},
        messages=({
            "role": "user",
            "content": [{"type": content_type, content_type: {"url": media_path.as_uri()}}],
        },),
    )


def _observation(record) -> ToolOutput:
    content = []
    for view, tag in (('first_person', 'first_person_view'), ('top_down', 'top_down_view'),
                      ('nearest_video_frame', 'nearest_video_frame')):
        content.append({'type': 'text', 'text': f'<{tag}>'})
        content.extend(_view_media(record['images'][view]).messages[0]['content'])
        content.append({'type': 'text', 'text': f'</{tag}>'})
    content.append({'type': 'text', 'text': (
        'The first-person and top-down images show the current camera state. '
        'The nearest video frame is a captured reference matched to the current camera pose; '
        'it is not an exact view from the current camera. '
        'The top-down map also shows this session\'s movement history. '
        'Magenta lines and arrows show horizontal travel; yellow dots mark path starts. '
        'Reset starts a disconnected segment. Map framing includes all historical positions and may change between observations.'
    )})
    return ToolOutput(value=record, messages=({'role': 'user', 'content': content},))


def create_tools(camera) -> list[Tool]:
    """Bind environment tools to one CameraClient without owning its lifecycle."""
    action_keys = list('wjlik')

    def camera_action(key: str, magnitude: float | None = None) -> ToolOutput:
        if key not in action_keys:
            raise ValueError(f'Unsupported camera key: {key!r}; allowed keys: w, j, l, i, k')
        return _observation(camera.execute(key, magnitude))

    no_arguments = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    return [
        Tool(
            name='camera_action',
            description=(
                'Execute one camera action and return the updated state and three separate images: '
                'first-person view, top-down map with movement history, and matched reference video frame. '
                'All actions apply to the current first-person camera. '
                "Interpret directional keys from that camera's perspective, not the top-down "
                'image axes or the reference video frame. '
                "w: move forward; j: turn toward the camera's own left; l: turn toward its own right; "
                'i: tilt the view up; k: tilt the view down; '
                'To move sideways or return to an earlier position, turn toward it first, then use w. '
                "Horizontal movement is relative to the current first-person camera's horizontal heading, "
                'so the forward direction changes after turning. Forward movement preserves height, regardless of pitch.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'key': {
                        'type': 'string', 'enum': action_keys,
                        'description': 'One camera key. Pass magnitude separately; do not pass a key sequence or a combined command such as w0.3.',
                    },
                    'magnitude': {
                        'type': 'number', 'exclusiveMinimum': 0,
                        'description': (
                            'Optional positive finite distance for w in scene units '
                            '(approximately meters with metric scaling), or angle in degrees '
                            'for j/l/i/k. Omit to use the configured step.'
                        ),
                    },
                },
                'required': ['key'],
                'additionalProperties': False,
            },
            function=camera_action,
        ),
        Tool(
            name='camera_observe',
            description=('Render the current camera pose and return its state and three separate images: '
                         'first-person view, top-down map with movement history, and matched reference video frame.'),
            parameters=no_arguments,
            function=lambda: _observation(camera.observe()),
        ),
        Tool(
            name='camera_status',
            description='Return camera position, yaw, pitch and point radius without rendering.',
            parameters=no_arguments,
            function=camera.status,
        ),
        Tool(
            name='camera_reset',
            description=('Restore the initial camera pose and point radius; return state and three separate images. '
                         'Retain old trajectories and start a disconnected path segment at the initial position.'),
            parameters=no_arguments,
            function=lambda: _observation(camera.reset()),
        ),
    ]
