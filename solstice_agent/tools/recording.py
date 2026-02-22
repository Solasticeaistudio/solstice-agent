"""
Screen + Camera Recording Tools
=================================
Screen recording (video), webcam capture, camera enumeration.
Requires: pip install mss opencv-python-headless Pillow
"""

import logging
import os
import tempfile
import threading
import time
from typing import Optional

log = logging.getLogger("solstice.tools.recording")

# Module-level state for screen recording
_recording_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_recording_state = {
    "active": False,
    "output_path": "",
    "start_time": 0.0,
    "frame_count": 0,
    "fps": 10,
}

_QUALITY_PRESETS = {
    "low": {"fps": 5, "scale": 0.5},
    "medium": {"fps": 10, "scale": 0.75},
    "high": {"fps": 15, "scale": 1.0},
}


# ---------------------------------------------------------------------------
# Screen recording
# ---------------------------------------------------------------------------

def _record_loop(monitor, fps, scale, output_path, max_duration):
    """Background thread: capture frames and write to video file."""
    try:
        import mss
        import numpy as np
        import cv2
    except ImportError:
        _recording_state["active"] = False
        return

    with mss.mss() as sct:
        monitors = sct.monitors[1:]
        if monitor < 0 or monitor >= len(monitors):
            monitor = 0
        mon = monitors[monitor]

        # Capture one frame to get dimensions
        raw = sct.grab(mon)
        frame = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4)
        frame = frame[:, :, :3]  # Drop alpha

        h, w = frame.shape[:2]
        if scale < 1.0:
            w = int(w * scale)
            h = int(h * scale)

        # Try mp4v codec, fall back to XVID
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
        if not writer.isOpened():
            # Fallback
            alt_path = output_path.rsplit(".", 1)[0] + ".avi"
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(alt_path, fourcc, fps, (w, h))
            _recording_state["output_path"] = alt_path

        frame_interval = 1.0 / fps
        _recording_state["start_time"] = time.time()

        while not _stop_event.is_set():
            loop_start = time.time()

            # Check max duration
            elapsed = loop_start - _recording_state["start_time"]
            if elapsed >= max_duration:
                break

            raw = sct.grab(mon)
            frame = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4)
            frame = frame[:, :, :3]

            if scale < 1.0:
                frame = cv2.resize(frame, (w, h))

            # mss captures in BGRA, OpenCV uses BGR — already correct after dropping alpha
            writer.write(frame)
            _recording_state["frame_count"] += 1

            # Sleep to maintain target FPS
            capture_time = time.time() - loop_start
            sleep_time = frame_interval - capture_time
            if sleep_time > 0:
                _stop_event.wait(sleep_time)

        writer.release()
        _recording_state["active"] = False


def recording_start(
    fps: int = 10,
    monitor: int = 0,
    region: Optional[str] = None,
    output_path: Optional[str] = None,
    max_duration: int = 300,
    quality: str = "medium",
) -> str:
    """Start recording the screen as a video file."""
    global _recording_thread

    try:
        import mss  # noqa: F401
        import numpy as np  # noqa: F401
        import cv2  # noqa: F401
    except ImportError:
        return "Error: Screen recording requires: pip install mss opencv-python-headless numpy"

    if _recording_state["active"]:
        return "Error: Recording already in progress. Use recording_stop first."

    preset = _QUALITY_PRESETS.get(quality, _QUALITY_PRESETS["medium"])
    actual_fps = fps if fps != 10 else preset["fps"]
    scale = preset["scale"]

    out = output_path or os.path.join(
        tempfile.gettempdir(), f"sol_recording_{int(time.time())}.mp4"
    )

    _stop_event.clear()
    _recording_state.update({
        "active": True,
        "output_path": out,
        "start_time": time.time(),
        "frame_count": 0,
        "fps": actual_fps,
    })

    _recording_thread = threading.Thread(
        target=_record_loop,
        args=(monitor, actual_fps, scale, out, max_duration),
        daemon=True,
    )
    _recording_thread.start()

    return f"Recording started: {out} ({actual_fps} fps, quality={quality}, max {max_duration}s)"


def recording_stop() -> str:
    """Stop the current screen recording and finalize the video."""
    global _recording_thread

    if not _recording_state["active"]:
        return "Not recording. Nothing to stop."

    _stop_event.set()
    if _recording_thread and _recording_thread.is_alive():
        _recording_thread.join(timeout=10)
    _recording_thread = None

    duration = time.time() - _recording_state["start_time"]
    out = _recording_state["output_path"]
    frames = _recording_state["frame_count"]
    size_mb = os.path.getsize(out) / (1024 * 1024) if os.path.isfile(out) else 0

    _recording_state["active"] = False
    return (
        f"Recording saved: {out}\n"
        f"  Duration: {duration:.1f}s | Frames: {frames} | Size: {size_mb:.1f} MB"
    )


def recording_status() -> str:
    """Get the current recording status."""
    if not _recording_state["active"]:
        return "Status: idle (not recording)"

    elapsed = time.time() - _recording_state["start_time"]
    out = _recording_state["output_path"]
    frames = _recording_state["frame_count"]
    size_mb = os.path.getsize(out) / (1024 * 1024) if os.path.isfile(out) else 0

    return (
        f"Status: recording\n"
        f"  Output: {out}\n"
        f"  Duration: {elapsed:.1f}s | Frames: {frames} | "
        f"FPS: {_recording_state['fps']} | Size: {size_mb:.1f} MB"
    )


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def camera_capture(
    device_index: int = 0,
    output_path: Optional[str] = None,
) -> str:
    """Capture a single frame from a webcam."""
    try:
        import cv2
    except ImportError:
        return "Error: Camera capture requires: pip install opencv-python-headless"

    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        return f"Error: Cannot open camera device {device_index}"

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return f"Error: Failed to capture frame from camera {device_index}"

    out = output_path or os.path.join(
        tempfile.gettempdir(), f"sol_camera_{int(time.time())}.jpg"
    )

    cv2.imwrite(out, frame)
    h, w = frame.shape[:2]
    return f"Camera frame saved: {out} ({w}x{h})"


def camera_list() -> str:
    """List available camera devices."""
    try:
        import cv2
    except ImportError:
        return "Error: Camera listing requires: pip install opencv-python-headless"

    devices = []
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            devices.append(f"  [{i}] {w}x{h}")
            cap.release()
        else:
            cap.release()

    if not devices:
        return "No camera devices found."

    return f"Camera devices ({len(devices)}):\n" + "\n".join(devices)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "recording_start": {
        "name": "recording_start",
        "description": (
            "Start recording the screen as a video file (MP4). "
            "Quality presets: low (5fps/50%), medium (10fps/75%), high (15fps/100%)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fps": {"type": "integer", "description": "Frames per second (default from quality preset)"},
                "monitor": {"type": "integer", "description": "Monitor index (default 0 = primary)"},
                "region": {"type": "string", "description": "Region as 'x,y,width,height'"},
                "output_path": {"type": "string", "description": "Output file path (default: temp dir)"},
                "max_duration": {"type": "integer", "description": "Max duration in seconds (default 300)"},
                "quality": {"type": "string", "description": "Quality: 'low', 'medium', 'high'"},
            },
            "required": [],
        },
    },
    "recording_stop": {
        "name": "recording_stop",
        "description": "Stop the current screen recording and finalize the video file.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "recording_status": {
        "name": "recording_status",
        "description": "Get the current recording status: active/idle, duration, file size.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "camera_capture": {
        "name": "camera_capture",
        "description": "Capture a single frame from a webcam/camera.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_index": {"type": "integer", "description": "Camera device index (default 0)"},
                "output_path": {"type": "string", "description": "Where to save (default: temp dir)"},
            },
            "required": [],
        },
    },
    "camera_list": {
        "name": "camera_list",
        "description": "List available camera devices with resolution.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def register_recording_tools(registry):
    """Register screen/camera recording tools."""
    registry.register("recording_start", recording_start, _SCHEMAS["recording_start"])
    registry.register("recording_stop", recording_stop, _SCHEMAS["recording_stop"])
    registry.register("recording_status", recording_status, _SCHEMAS["recording_status"])
    registry.register("camera_capture", camera_capture, _SCHEMAS["camera_capture"])
    registry.register("camera_list", camera_list, _SCHEMAS["camera_list"])
