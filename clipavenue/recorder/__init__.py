"""ClipAvenue Recorder Manager — live stream recording orchestration.

Wraps BililiveRecorder and biliup for B站/抖音 live stream capture.
Manages task lifecycle: watch → record → complete/fail.
"""

from clipavenue.recorder.manager import RecorderManager
from clipavenue.recorder.task import RecorderTask, RecorderStatus

__all__ = ["RecorderManager", "RecorderTask", "RecorderStatus"]