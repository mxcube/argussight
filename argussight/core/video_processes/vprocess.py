import base64
import inspect
import json
import os
import queue
import time
import warnings
from datetime import datetime
from enum import Enum
from logging import Logger
from multiprocessing import Queue
from typing import Any, Dict, Tuple

import cv2
import numpy as np
import redis
import yaml
from PIL import Image

CONFIG_BASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../configurations/processes"
)
CONFIGS_EXTENSION = ".yaml"


class ProcessError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FrameFormat(Enum):
    CV2 = "cv2"
    PIL = "pil"
    RAW = "raw"


class Vprocess:
    def __init__(
        self, collector_config, exposed_parameters: Dict[str, Any], logger: Logger
    ) -> None:
        self._current_frame_number = -1
        self._current_frame = None
        self._missed_frames = 0
        self._logger = logger

        # Please change the following three variables (if you need to) in your subclasses (not here!)
        self._frame_format: FrameFormat = (
            FrameFormat.RAW
        )  # Format your frames should convert to
        self._time_stamp_used = (
            False  # If you need self._current_frame_time, set this to true
        )
        self._command_timeout = (
            1  # Time the process waits for new commands to arrive in seconds
        )

        # Dictionary of all commands that can be executed via command_queue
        self._commands = self.create_commands_dict()
        self._date_format = "%H:%M:%S.%f"

        self._client = redis.StrictRedis(
            host=collector_config.redis.host, port=collector_config.redis.port
        )
        self._channel = collector_config.redis.channel
        self._config = self.load_config_from_file()
        self.exposed_parameters = exposed_parameters
        self._parameters = self._get_all_parameters()

    def merge_dicts(self, base_dict, new_dict):
        merged = base_dict.copy()
        merged["parameters"].update(new_dict["parameters"])
        return merged

    def load_config_from_file(self) -> Dict:
        class_hierarchy = self.__class__.mro()[:-1]
        final_config = {"parameters": {}}
        for klass in reversed(class_hierarchy):
            file_name = os.path.splitext(self.get_class_file(klass))[0]
            config_path = self.__class__.find_config_file(
                CONFIG_BASE_PATH, file_name + CONFIGS_EXTENSION
            )

            if not config_path:
                raise FileNotFoundError(f"Config file not found for {file_name}")

            with open(config_path, "r") as config_file:
                config_data = yaml.safe_load(config_file) or {}
                final_config = self.merge_dicts(final_config, config_data)
        return final_config

    @staticmethod
    def find_config_file(base_path, file_name):
        # check if file is directly in base_path
        direct_path = os.path.join(base_path, file_name)
        if os.path.isfile(direct_path):
            return direct_path

        # check if file is inside a folder of base_path
        for root, _, files in os.walk(base_path):
            if file_name in files:
                return os.path.join(root, file_name)
        return None

    def get_class_file(self, cls):
        module = inspect.getmodule(cls)
        if module:
            return os.path.basename(module.__file__).replace(".py", ".yaml")
        return None

    @classmethod
    def create_commands_dict(cls) -> Dict[str, Any]:
        return {
            "settings": cls.change_settings,
            "default_settings": cls.set_default_settings,
        }

    def set_default_settings(self) -> None:
        self._parameters = self._get_all_parameters()

    def change_settings(self, dict: Dict) -> None:
        if not set(dict.keys()).issubset(self.exposed_parameters.keys()):
            raise ProcessError(
                f"The given settings {dict.keys()} do not exist. Allowed settings are {self.exposed_parameters.keys()}"
            )

        params_copy = self._parameters.copy()
        params_copy.update(dict)
        self.check_conflict(params_copy)

        self._prepare_settings_change(dict)
        self.exposed_parameters.update(dict)
        self._parameters.update(dict)

    def _prepare_settings_change(self, dict: Dict) -> None:
        for key, value in dict.items():
            if value != self._parameters[key]:
                self.prepare_setting_change(key)

    def check_conflict(self, dict: Dict) -> None:
        pass

    def prepare_setting_change(self, key: str) -> None:
        pass

    def _get_all_parameters(self) -> Dict[str, Any]:
        all_params = {
            param: data["value"]
            for param, data in self._config.get("parameters", {}).items()
        }

        # Fill in all the exposed_params from yml
        for param, data in self._config.get("parameters", {}).items():
            if "exposed" not in data:
                warnings.warn(
                    f"Parameter '{param}' is missing the 'exposed' flag. Defaulting to False."
                )
            elif data["exposed"]:
                self.exposed_parameters[param] = data["value"]
        return all_params

    def read_frame(self, frame) -> bool:
        current_frame_number = frame["frame_number"]
        if self._time_stamp_used:
            self._current_frame_time = datetime.strptime(
                frame["time"], self._date_format
            )

        self.copy_frame(base64.b64decode(frame["data"]), frame["size"])
        if self._current_frame_number != -1:
            self._missed_frames += current_frame_number - self._current_frame_number - 1
            if current_frame_number > self._current_frame_number + 1:
                self._logger.warning(f"Frames Missed in Total: {self._missed_frames}")
        else:
            self._logger.info(f"Started reading at frame {current_frame_number}")
        self._current_frame_number = current_frame_number

    def copy_frame(self, frame_data: bytes, frame_size: Tuple[int, int, int]) -> None:
        match self._frame_format:
            case FrameFormat.RAW:
                self._current_frame = frame_data
            case FrameFormat.PIL:
                self._current_frame = Image.frombytes(
                    "RGB", frame_size, frame_data, "raw"
                )
            case FrameFormat.CV2:
                img = Image.frombytes("RGB", frame_size, frame_data, "raw")
                self._current_frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            case _:
                raise TypeError(f"FrameFormat has no type: {self._frame_format}")

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
        except redis.exceptions.ConnectionError as e:
            self._logger.error("Cannot establish redis connection")
            self._logger.exception(f"{e}")

    def process_frame(self) -> None:
        pass

    def handle_command(self, order: str, response_queue: Queue, args) -> None:
        if order not in self._commands:
            response_queue.put(
                ProcessError(
                    f"Order {order} is not known for process of type {type(self)}."
                )
            )
            return
        try:
            self._commands[order](self, *args)
            response_queue.put("Order {order} succeeded")
        except Exception as e:
            response_queue.put(e)

    def get_stream_id(self):
        return ""


class Test(Vprocess):
    def __init__(self, collector_config, exposed_parameters: Dict[str, Any]) -> None:
        super().__init__(collector_config, exposed_parameters)
        self._commands["print"] = self.print

    def run(self, command_queue: Queue, response_queue: Queue) -> None:
        self._logger.info("Running test process")
        try:
            order, args = command_queue.get(timeout=self._command_timeout)
            self.handle_command(order, response_queue, args)
        except queue.Empty:
            pass

    def print(self, text: str):
        print(text)
        time.sleep(2)

    def process_frame(self) -> None:
        time.sleep(3)
