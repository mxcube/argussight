import base64
import json
import queue
import subprocess
import uuid
from logging import Logger
from multiprocessing import Queue
from typing import Any, Dict

import cv2
import redis

from argussight.core.video_processes.vprocess import FrameFormat, Vprocess


class Streamer(Vprocess):
    def __init__(
        self,
        collector_config,
        free_port,
        exposed_parameters: Dict[str, Any],
        logger: Logger,
    ) -> None:
        super().__init__(collector_config, exposed_parameters, logger)

        self._processed_frame = None  # this should be changed in process_frame
        self._frame_format = (
            FrameFormat.CV2
        )  # streamer processes should use the cv2 (BGR) image format

        self._stream_id = str(uuid.uuid1())
        self._redis_client = redis.StrictRedis(host="localhost", port=6379)
        self._currently_streaming = False
        self.free_port = free_port

    def get_stream_id(self) -> str:
        return self._stream_id

    def run(self, command_queue: Queue, response_queue: Queue) -> None:
        pubsub = self._client.pubsub()
        pubsub.subscribe(self._channel)

        try:
            for message in pubsub.listen():
                try:
                    order, args = command_queue.get(timeout=self._command_timeout)
                    self.handle_command(order, response_queue, args)
                except queue.Empty:
                    pass

                if message and message["type"] == "message":
                    self.read_frame(json.loads(message["data"]))
                    self.process_frame()
                    self.stream()
        except redis.exceptions.ConnectionError as e:
            self._logger.error("Connection error")
            self._logger.exception(e)

    def stream(self) -> None:
        if self._processed_frame is not None:
            _, buffer = cv2.imencode(".jpg", self._processed_frame)
            raw_image_data = buffer.tobytes()
            frame_dict = {
                "data": base64.b64encode(raw_image_data).decode("utf-8"),
                "size": self._processed_frame.shape,
            }
            self._redis_client.publish(self._stream_id, json.dumps(frame_dict))
            if not self._currently_streaming:
                self._video_stream_process = subprocess.Popen(
                    [
                        "video-streamer",
                        "-uri",
                        "redis://localhost:6379",
                        "-hs",
                        "localhost",
                        "-p",
                        str(self.free_port),
                        "-q",
                        "4",
                        "-s",
                        str(self._processed_frame.shape[0:2])
                        .replace("(", "")
                        .replace(")", ""),
                        "-of",
                        "MPEG1",
                        "-id",
                        self._stream_id,
                        "-irc",
                        self._stream_id,
                    ],
                    close_fds=True,
                )
                self._currently_streaming = True
