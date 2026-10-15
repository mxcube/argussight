import contextlib
import importlib
import inspect
import multiprocessing
import os
import queue
import subprocess
import threading
import uuid
from logging import Logger
from typing import Any, Dict, List, Tuple

import psutil
import yaml

import argussight.streamsproxy as StreamsProxy
from argussight.core.config import CollectorConfiguration, StreamConfiguration
from argussight.core.helper_functions import (
    find_close_key,
    find_free_port,
    stop_with_parent,
)
from argussight.core.manager import Manager
from argussight.core.video_processes.streamer.streamer import Streamer
from argussight.core.video_processes.vprocess import ProcessError, Vprocess
from argussight.logger import configure_logger


class Spawner:
    def __init__(self, collector_config: CollectorConfiguration) -> None:
        self._processes = {}
        self._worker_classes = {}
        self._managers_dict = {}
        self._restricted_classes = []
        self._streamer_types = []
        self.collector_config = collector_config
        self._settings_manager = multiprocessing.Manager()
        self._streams = set([])
        self._stream_processes: Dict[str, subprocess.Popen] = {}
        # ports handed out to streams, which might not be listening yet
        self._reserved_ports: Dict[str, int] = {}

        self.load_config(os.path.join(collector_config.config_path, "config.yaml"))
        self._logger = configure_logger("Spawner", "Spawner", self.config["log_dir"])

        # the streams layer has to run before any stream can be added to it
        self._starts_stream_proxy()
        self.start_configured_processes()
        self.start_configured_streams()

    def cleanup(self):
        try:
            self._logger.info("Terminating all processes...")
            self.terminate_all_processes()
            self._logger.info("All processes terminated successfully.")
        except Exception as e:
            self._logger.error(f"Error terminating processes: {str(e)}")

        try:
            self._logger.info("Stopping all streams...")
            self.stop_streams(list(self._stream_processes.keys()))
            self._logger.info("All streams stopped successfully.")
        except Exception as e:
            self._logger.error(f"Error stopping streams: {str(e)}")

        self._logger.info("Terminating streams layer process...")
        self._proxy_command_queue.put({"action": "shutdown_server"})
        self.streams_layer_process.join(timeout=10)

        if self.streams_layer_process.is_alive():
            self._logger.warning(
                "Streams layer process did not shut down gracefully, terminating forcefully..."
            )
            self.streams_layer_process.terminate()
            self.streams_layer_process.join(timeout=10)

    def _starts_stream_proxy(self):
        self._proxy_command_queue = multiprocessing.Queue()
        self.streams_layer_process = multiprocessing.Process(
            target=StreamsProxy.run,
            args=(
                self._proxy_command_queue,
                self.config["streams_layer_port"],
                self.config["log_dir"],
            ),
        )

        self.streams_layer_process.start()

        self._logger.info(
            f"running stream_layer on port {self.config['streams_layer_port']}"
        )

    def load_config(self, path_config_file: str) -> None:
        with open(path_config_file, "r") as f:
            self.config = yaml.safe_load(f)
        self.load_worker_classes()

        # validate streams before anything is started
        self._configured_streams = [
            StreamConfiguration(**stream) for stream in self.config.get("streams") or []
        ]
        stream_names = [stream.name for stream in self._configured_streams]
        if len(stream_names) != len(set(stream_names)):
            raise ProcessError(f"Stream names must be unique, got {stream_names}")

    def start_configured_processes(self) -> None:
        for process in self.config["processes"]:
            self.start_process(process["name"], process["type"])

    def start_configured_streams(self) -> None:
        for stream in self._configured_streams:
            self.start_stream(stream)

    def start_stream(self, stream: StreamConfiguration) -> None:
        """Start a video-streamer for a camera and add it to the streams layer"""
        if stream.name in self._streams or stream.name in self._reserved_ports:
            raise ProcessError(
                f"Stream names must be unique. '{stream.name}' already exists."
            )
        if stream.port in self._reserved_ports.values():
            raise ProcessError(
                f"Port {stream.port} of stream '{stream.name}' is already in use."
            )

        port = stream.port or find_free_port(
            self.config["streams_starting_port"], self._reserved_ports.values()
        )
        stream_id = str(uuid.uuid1())
        stream_options = [
            "video-streamer",
            "-uri",
            stream.uri,
            "-hs",
            "localhost",
            "-p",
            str(port),
            "-of",
            "MPEG1",
            "-q",
            str(stream.quality),
            "-id",
            stream_id,
        ]
        if stream.size:
            stream_options.extend(["-s", stream.size])
        if stream.auth:
            stream_options.extend(
                [
                    "-auth",
                    stream.auth.type,
                    "-user",
                    stream.auth.username,
                    "-pass",
                    stream.auth.password,
                ]
            )

        self._stream_processes[stream.name] = subprocess.Popen(
            stream_options, close_fds=True, preexec_fn=stop_with_parent
        )
        self._reserved_ports[stream.name] = port
        self._logger.info(f"started stream {stream.name} on port {port}")
        self.add_stream(stream.name, port, stream_id)

    def stop_streams(self, names: List[str]) -> None:
        """Stop the video-streamers of the given streams and remove them from the
        streams layer. video-streamer stops its own children (ffmpeg, image
        polling) on SIGTERM, anything still alive after wait_time is killed"""
        stopping = []
        for name in names:
            process = self._stream_processes.pop(name)
            self.remove_stream(name)
            self._reserved_ports.pop(name, None)

            try:
                parent = psutil.Process(process.pid)
                # collect children now, they are reparented once the parent exits
                stopping.extend([parent] + parent.children(recursive=True))
            except psutil.NoSuchProcess:
                self._logger.warning(f"stream {name} was not running anymore")
                continue
            process.terminate()

        _, alive = psutil.wait_procs(stopping, timeout=self.config["wait_time"])
        for p in alive:
            self._logger.warning(f"Killing stream process {p.pid}, did not stop")
            with contextlib.suppress(psutil.NoSuchProcess):
                p.kill()
        psutil.wait_procs(alive, timeout=self.config["wait_time"])
        self._logger.info(f"stopped streams {names}")

    def load_worker_classes(self):
        worker_classes_config = self.config["worker_classes"]
        modules_path = self.config["modules_path"]
        for key, worker_class in worker_classes_config.items():
            class_path = worker_class["location"]
            module_name, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(modules_path + "." + module_name)
            self._worker_classes[key] = getattr(module, class_name)
            if not worker_class["accessible"]:
                self._restricted_classes.append(key)
            if issubclass(self._worker_classes[key], Streamer):
                self._streamer_types.append(key)

    def create_worker(
        self, worker_type: str, free_port, settings: Dict[str, Any], logger: Logger
    ) -> Vprocess:
        if worker_type in self._streamer_types:
            return self._worker_classes.get(worker_type)(
                self.collector_config, free_port, settings, logger
            )
        return self._worker_classes.get(worker_type)(
            self.collector_config, settings, logger
        )

    def add_process(
        self,
        name: str,
        worker_type: str,
        process: multiprocessing.Process,
        command_queue: multiprocessing.Queue,
        response_queue: multiprocessing.Queue,
        settings: Dict[str, Any],
    ) -> None:
        self._processes[name] = {
            "process_instance": process,
            "command_queue": command_queue,
            "response_queue": response_queue,
            "type": worker_type,
            "settings": settings,
        }

    # This function checks if worker_type can be accessed
    def check_restricted_access(self, worker_type: str) -> bool:
        # First check if access is restricted
        if worker_type not in self._restricted_classes:
            return True

        # If access is restricted, check if the caller is the server
        stack = inspect.stack()

        # The caller's frame will be two levels up in the stack:
        # - The current frame
        # - The frame of the function that called check_restricted_access
        # - The frame of the function that called that function (the original caller)
        caller_frame = stack[2]

        # Get the calling function's name and module
        caller_module = inspect.getmodule(caller_frame.frame)

        # Check if the caller is a method in the same class
        if caller_module and caller_module.__name__ == self.__class__.__module__:
            caller_class = caller_frame.frame.f_locals.get("self")
            if isinstance(caller_class, self.__class__):
                return True

        return False

    def add_stream(self, name, port, stream_id) -> None:
        self._proxy_command_queue.put(
            {"action": "add_stream", "path": name, "port": port, "id": stream_id}
        )
        self._streams.add(name)

    def remove_stream(self, name) -> None:
        self._proxy_command_queue.put({"action": "remove_stream", "path": name})
        self._streams.discard(name)

    def close_all_streams(self) -> None:
        self._proxy_command_queue.put({"action": "shutdown_streams"})

    def hide_stream(self, name, reason_to_hide) -> None:
        self._proxy_command_queue.put(
            {"action": "hide_stream", "path": name, "reason_to_hide": reason_to_hide}
        )

    def show_stream(self, name) -> None:
        self._proxy_command_queue.put({"action": "show_stream", "path": name})

    def start_process(self, name: str, type: str) -> None:
        if name in self._processes:
            raise ProcessError(
                f"Process names must be unique. '{name}' already exists. Either terminate '{name}' or choose a different unique name"
            )
        if type in self._streamer_types and name in self._streams:
            raise ProcessError(
                f"Stream names must be unique. A stream '{name}' already exists."
            )
        if type not in self._worker_classes:
            raise ProcessError(f"Type {type} does not exist")
        # check if somebody tries to start a restricted worker type from outside this class
        if not self.check_restricted_access(type):
            raise ProcessError(f"Worker of type {type} can only be started by server.")

        free_port = find_free_port(
            self.config["streams_starting_port"], self._reserved_ports.values()
        )
        settings = self._settings_manager.dict()
        logger = configure_logger(name, type, self.config["log_dir"])
        worker_instance = self.create_worker(type, free_port, settings, logger)
        command_queue = multiprocessing.Queue()
        response_queue = multiprocessing.Queue()
        p = multiprocessing.Process(
            target=worker_instance.run, args=(command_queue, response_queue)
        )
        self._logger.info(f"started {name} of type {type}")
        p.start()
        if isinstance(worker_instance, Streamer):
            self._reserved_ports[name] = free_port
            self.add_stream(name, free_port, worker_instance.get_stream_id())
        self.add_process(name, type, p, command_queue, response_queue, settings)

    # check if process is running otherwise throw ProcessError
    def check_for_running_process(self, name: str) -> None:
        if name not in self._processes:
            errorMessage = f"{name} is not a running process."
            closest_key = find_close_key(self._processes, name)
            if closest_key:
                errorMessage += f" Did you mean: {closest_key}"

            raise ProcessError(errorMessage)

    def find_process_in_config_by_name(self, name: str) -> Dict:
        for process in self.config["processes"]:
            if process["name"] == name:
                return process
        return None

    def terminate_processes(self, names: List[str], ignore_restrictions=False) -> None:
        for name in names:
            self.check_for_running_process(name)
            worker_type = self._processes[name]["type"]
            # check if somebody tries to kill a restricted worker type from outside this class
            if not self.check_restricted_access(worker_type):
                raise ProcessError(
                    f"Worker of type {worker_type} can only be terminated by server."
                )

        for name in names:
            p = self._processes[name]["process_instance"]
            worker_type = self._processes[name]["type"]
            # first kill all possible children
            parent = psutil.Process(p.pid)
            children = parent.children(recursive=True)
            for child in children:
                self._logger.info(f"Terminating child process: {child.pid}")
                child.terminate()
            # now kill the process itself and clean up
            p.terminate()
            p.join()
            del self._processes[name]["settings"]
            del self._processes[name]

            if worker_type in self._streamer_types:
                self.remove_stream(name)
                self._reserved_ports.pop(name, None)

            self._logger.info(f"terminated {name} of type {worker_type}")
            if (
                worker_type in self._restricted_classes
                and self.check_restricted_access(worker_type)
                and not ignore_restrictions
            ):
                process = self.find_process_in_config_by_name(name)
                self.start_process(process["name"], process["type"])

    def terminate_all_processes(self) -> None:
        self.terminate_processes(list(self._processes.keys()), ignore_restrictions=True)
        self._settings_manager.shutdown()
        self._settings_manager.join()
        self._logger.info("terminated all processes")

    def wait_for_manager(
        self,
        finished_event: threading.Event,
        failed_event: threading.Event,
        name: str,
        manager: threading.Thread,
    ) -> None:
        while manager.is_alive():
            finished_event.wait(timeout=1000)
            if finished_event.is_set():
                del self._managers_dict[name]
                if failed_event.is_set():
                    self.terminate_processes([name])
                return

        if name in self._managers_dict:
            del self._managers_dict[name]
            self._logger.error("manager is not alive anymore but hasn't finished")

    def send_command_to_manager(
        self, name: str, command: str, args
    ) -> Tuple[threading.Event, queue.Queue]:
        processed_event = threading.Event()
        response_queue = queue.Queue()

        self._managers_dict[name]["manager"].receive_command(
            command, self.config["wait_time"], processed_event, response_queue, args
        )

        return processed_event, response_queue

    # this function should only be called by the spawner service and used as Thread
    def manage_process(self, name: str, command: str, args) -> None:
        self.check_for_running_process(name)

        # Check if manager already exists
        if name not in self._managers_dict:
            finished_event = threading.Event()
            failed_event = threading.Event()
            self._managers_dict[name] = {
                "manager": Manager(
                    self._processes[name]["command_queue"],
                    self._processes[name]["response_queue"],
                    finished_event,
                    failed_event,
                ),
                "failed_event": failed_event,
            }
            processed_event, result_queue = self.send_command_to_manager(
                name, command, args
            )

            manager_thread = threading.Thread(
                target=self._managers_dict[name]["manager"].handle_commands
            )
            waiter_thread = threading.Thread(
                target=self.wait_for_manager,
                args=(finished_event, failed_event, name, manager_thread),
            )
            manager_thread.start()
            waiter_thread.start()
        else:
            try:
                processed_event, result_queue = self.send_command_to_manager(
                    name, command, args
                )
                failed_event = self._managers_dict[name]["failed_event"]
            except ProcessError as e:
                e.message += f" for {name}. Try again later"

        is_processing = processed_event.wait(timeout=self.config["wait_time"])
        if is_processing:
            try:
                result = result_queue.get(timeout=self.config["wait_time"])
                if isinstance(result, Exception):
                    raise result

                return
            except queue.Empty:
                wait_time = self.config["wait_time"]
                raise ProcessError(
                    f"Command {command} could not be executed in time {wait_time}. Hence process {name} is getting terminated"
                )

        elif failed_event.is_set():
            raise ProcessError(
                f"An error occured in process {name}. Process is no longer alive."
            )
        else:
            raise ProcessError(
                f"Process {name} is busy and could not start command in time. Try again later."
            )

    def get_processes(self):
        running_processes = {}
        for uname, process in self._processes.items():
            type = process["type"]
            current_class = self._worker_classes[type]
            commands = [
                command
                for command in current_class.create_commands_dict().keys()
                if command != "settings" and command != "default_settings"
            ]
            settings = dict(process["settings"])
            running_processes[uname] = {
                "type": type,
                "commands": commands,
                "settings": settings,
            }

        available_types = [
            type
            for type in self._worker_classes
            if type not in self._restricted_classes
        ]

        return running_processes, available_types, self._streams
