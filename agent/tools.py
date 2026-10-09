"""Media viewing and camera tools bound to a running camera client."""

import mimetypes
from pathlib import Path

from .types import Tool, ToolOutput


def view_media(path: str) -> ToolOutput:
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


VIEW_MEDIA_TOOL = Tool(
    name="view_media",
    description="View a local image or video with the model's visual capability.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Local image or video path."}},
        "required": ["path"],
        "additionalProperties": False,
    },
    function=view_media,
)

TOOLS = [VIEW_MEDIA_TOOL]


def _observation(record) -> ToolOutput:
    content = []
    for view, tag in (('first_person', 'first_person_view'), ('top_down', 'top_down_view'),
                      ('nearest_video_frame', 'nearest_video_frame')):
        content.append({'type': 'text', 'text': f'<{tag}>'})
        content.extend(view_media(record['images'][view]).messages[0]['content'])
        content.append({'type': 'text', 'text': f'</{tag}>'})
    content.append({'type': 'text', 'text': (
        'The first-person and top-down images show the current camera state. '
        'The nearest video frame is a captured reference matched to the current camera pose; '
        'it is not an exact view from the current camera.'
    )})
    return ToolOutput(value=record, messages=({'role': 'user', 'content': content},))


def create_tools(camera) -> list[Tool]:
    """Bind environment tools to one CameraClient without owning its lifecycle."""
    def action(key: str, magnitude: float | None = None) -> ToolOutput:
        return _observation(camera.execute(key, magnitude))

    no_arguments = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    return [
        VIEW_MEDIA_TOOL,
        Tool(
            name='camera_action',
            description=(
                'Execute one camera action and return the updated state and three separate view images. '
                'w/s: forward/back; a/d: left/right; q/e: down/up; '
                'j/l: turn left/right; i/k: look up/down; +/-: increase/decrease point radius. '
                "WASD movement is relative to the current first-person camera's horizontal heading, "
                'not the top-down image axes or the reference video frame. Directions change after '
                'turning the camera. WASD movement stays horizontal and preserves height, regardless '
                "of pitch. q/e move along the scene's vertical axis, independently of camera pitch."
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'enum': list('wasdqeijkl+-')},
                    'magnitude': {
                        'type': 'number', 'exclusiveMinimum': 0,
                        'description': (
                            'Optional positive distance for w/s/a/d in scene units '
                            '(approximately meters with metric scaling), or angle in degrees '
                            'for i/j/k/l. Omit to use the configured step. q/e/+/- use fixed '
                            'steps and do not accept a magnitude.'
                        ),
                    },
                },
                'required': ['key'],
                'additionalProperties': False,
            },
            function=action,
        ),
        Tool(
            name='camera_observe',
            description='Render the current camera pose and return its state and three separate view images.',
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
            description='Restore the initial camera pose and point radius; return state and three separate view images.',
            parameters=no_arguments,
            function=lambda: _observation(camera.reset()),
        ),
    ]
