from collections import deque
from logging import Logger
from typing import Any, Dict

from argussight.core.video_processes.savers.video_saver import VideoSaver


class StreamBuffer(VideoSaver):
    def __init__(
        self, collector_config, exposed_parameters: Dict[str, Any], logger: Logger
    ) -> None:
        super().__init__(collector_config, exposed_parameters, logger)
        self._queue = deque(maxlen=self._parameters["max_queue_len"])

    @classmethod
    def create_commands_dict(cls) -> Dict[str, Any]:
        result = super().create_commands_dict()
        result.update({"save": cls.save_queue})
        return result

    def save_queue(self) -> None:
        queue = self._queue.copy()
        self.executor.submit(
            self.save_iterable,
            queue,
        )

    def add_to_iterable(self, frame: Dict) -> None:
        self._queue.append(frame)

    def _max_recording_callback(self) -> None:
        self.save_queue()
        # this should normally not be called but if it is,
        # there is no way to reset recording except by restarting the server
        self._parameters["recording"] = False
