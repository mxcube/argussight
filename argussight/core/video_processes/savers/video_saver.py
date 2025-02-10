import base64
import concurrent.futures
import os
from datetime import datetime
from enum import Enum
from logging import Logger
from multiprocessing import Queue
from typing import Any, Dict, Iterable, Tuple

import cv2
import numpy as np
from PIL import Image

from argussight.core.video_processes.vprocess import ProcessError, Vprocess


class SaveFormat(Enum):
    VIDEO = "video"
    FRAMES = "frames"
    BOTH = "both"


class VideoSaver(Vprocess):
    def __init__(
        self, collector_config, exposed_parameters: Dict[str, Any], logger: Logger
    ) -> None:
        super().__init__(collector_config, exposed_parameters, logger)
        self._command_timeout = 0.04
        self._recording_start_time = None

        # saving videos and frames might take some time, the ThreadPool can be used
        # to excute these processes in a seperate thread
        # Normal threading doesn't work due to redis pubsub listener blocking
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

    def save_frame(self, frame: dict, folder_path: str):
        img = Image.frombytes("RGB", frame["size"], frame["frame"], "raw")
        img.save(
            os.path.join(folder_path, "img" + frame["time_stamp"] + ".jpg"),
            format="JPEG",
        )

    def is_within_main(self, target: str):
        abs_main = os.path.abspath(self._parameters["main_save_folder"])
        abs_target = os.path.abspath(target)

        common_prefix = os.path.commonpath([abs_main])
        target_prefix = os.path.commonpath([abs_main, abs_target])

        return common_prefix == target_prefix

    def get_frame_from_element(
        self, element: Any
    ) -> Tuple[Tuple[int, int], bytes, str]:
        return element["size"], element["frame"], element["time_stamp"]

    def save_iterable_as_video(self, iterable: Iterable, save_folder: str) -> None:
        video_folder = os.path.join(save_folder, "videos")
        if not os.path.exists(video_folder):
            os.makedirs(video_folder, exist_ok=True)
        size_first, _, time_first = self.get_frame_from_element(iterable[0])
        _, _, time_last = self.get_frame_from_element(iterable[-1])
        output_file = os.path.join(video_folder, f"video_{time_first}-{time_last}.avi")

        out = cv2.VideoWriter(
            output_file, cv2.VideoWriter_fourcc(*"MJPG"), 30, size_first
        )

        for element in iterable:
            size, data, _ = self.get_frame_from_element(element)
            img = Image.frombytes("RGB", size, data, "raw")
            open_cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            out.write(open_cv_image)

        out.release()
        cv2.destroyAllWindows()

    def save_iterable(self, iterable: Iterable) -> None:
        save_folder = os.path.join(
            self._parameters["main_save_folder"], self._parameters["personnal_folder"]
        )
        save_format = self._parameters["save_format"]

        if not self.is_within_main(save_folder):
            raise ProcessError("Your path should not leave the main folder")
        if (
            save_format == SaveFormat.FRAMES.value
            or save_format == SaveFormat.BOTH.value
        ):
            _, _, time_first = self.get_frame_from_element(iterable[0])
            _, _, time_last = self.get_frame_from_element(iterable[-1])
            frames_folder = os.path.join(
                save_folder, f"frames_{time_first}-{time_last}"
            )
            if not os.path.exists(frames_folder):
                os.makedirs(frames_folder, exist_ok=True)

            for element in iterable:
                size, data, time = self.get_frame_from_element(element)
                frame = {"size": size, "frame": data, "time_stamp": time}
                self.save_frame(frame, frames_folder)

        if (
            save_format == SaveFormat.VIDEO.value
            or save_format == SaveFormat.BOTH.value
        ):
            self.save_iterable_as_video(iterable, save_folder)

    def add_to_iterable(self, frame: Dict) -> None:
        pass

    def _max_recording_callback(self) -> None:
        pass

    def read_frame(self, frame) -> None:
        current_frame_number = frame["frame_number"]
        if self._current_frame_number != -1:
            self._missed_frames += current_frame_number - self._current_frame_number - 1
            if current_frame_number > self._current_frame_number + 1:
                self._logger.warning(f"Frames Missed in Total: {self._missed_frames}")
        else:
            self._logger.info(f"Started reading at frame {current_frame_number}")
        self._current_frame_number = current_frame_number

        if self._parameters["recording"]:
            current_time = datetime.strptime(frame["time"], self._date_format)
            if not self._recording_start_time:
                self._recording_start_time = current_time
            elif self._parameters["max_recording_time"] != 0:
                total_seconds = int(
                    (current_time - self._recording_start_time).total_seconds()
                )
                if total_seconds > self._parameters["max_recording_time"]:
                    self._recording_start_time = None
                    self._max_recording_callback()
                    return

            frame["time_stamp"] = current_time.strftime(self._date_format)
            frame["frame"] = base64.b64decode(frame["data"])
            self.add_to_iterable(frame)

    # override run to correctly shutdown executor
    def run(self, command_queue: Queue, response_queue: Queue) -> None:
        try:
            super().run(command_queue, response_queue)
        finally:
            self.executor.shutdown(wait=True)

    def _get_all_parameters(self) -> Dict[str, Any]:
        # The "recording" parameter state, should be kept in exposed_parameters and _parameters,
        # so that clients know about the state
        if "recording" not in self.exposed_parameters.keys():
            self.exposed_parameters["recording"] = (
                True  # we set to true, as we want to continuously save to iterable
            )

        all_params = super()._get_all_parameters()
        all_params["recording"] = self.exposed_parameters["recording"]
        return all_params

    def change_settings(self, dict: Dict) -> None:
        # make sure that "recording" parameter is only set by commands
        if "recording" in dict.keys():
            raise ProcessError(
                "Cannot set recording via settings. Use respective process commands!"
            )
        return super().change_settings(dict)
