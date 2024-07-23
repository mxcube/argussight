import yaml
import multiprocessing
from multiprocessing.managers import DictProxy
from multiprocessing.synchronize import Lock
from typing import List, Dict, Any, Union, Tuple
import importlib
import os
import Levenshtein
import queue
from argussight.core.manager import Manager
import threading
import inspect

from argussight.core.video_processes.vprocess import Vprocess, ProcessError

# Return first key in dict whose Levenshtein distance to key is <= max_distance
def find_close_key(d: dict, key: str, max_distance: int = 3) -> Union[str, None]:
    min_distance = float('inf')
    closest_key = None
    
    for dict_key in d:
        distance = Levenshtein.distance(key, dict_key)
        if distance < min_distance:
            min_distance = distance
            closest_key = dict_key
    
    if min_distance<=max_distance:
        return closest_key
    
    return None

class Spawner:
    def __init__(self, shared_dict: DictProxy, lock: Lock) -> None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self._config_file = os.path.join(current_dir, 'video_processes/config.yaml')
        self._processes = {}
        self._worker_classes = {}
        self.shared_dict = shared_dict
        self.lock = lock
        self._managers_dict = {}
        self._restricted_classes = []
        
        self.load_config()

    def load_config(self) -> None:
        with open(self._config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        self.load_worker_classes()
        self.start_processes(self.config["processes"])

    def load_worker_classes(self):
        worker_classes_config = self.config['worker_classes']
        modules_path = self.config['modules_path']
        for key, worker_class in worker_classes_config.items():
            class_path = worker_class["location"]
            module_name, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(modules_path + '.' + module_name)
            self._worker_classes[key] = getattr(module, class_name)
            if not worker_class["accessible"]:
                self._restricted_classes.append(key)
                print(self._restricted_classes)
        
    def create_worker(self, worker_type: str, *args) -> Vprocess:
        return self._worker_classes.get(worker_type)(self.shared_dict, self.lock, *args)
    
    def add_process(self, name: str, worker_type: str, process: multiprocessing.Process, command_queue: multiprocessing.Queue, response_queue: multiprocessing.Queue) -> None:
        self._processes[name] = {
            "process_instance": process,
            "command_queue": command_queue,
            "response_queue": response_queue,
            "type": worker_type,
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
            caller_class = caller_frame.frame.f_locals.get('self')
            if isinstance(caller_class, self.__class__):
                return True
        
        return False

    def start_processes(self, processes: List[Dict[str, Any]]) -> None:
        for process in processes:
            worker_type = process["type"]
            name = process["name"]
            if name in self._processes:
                raise ProcessError(f"Process names must be unique. '{name}' already exists. Either terminate '{name}' or choose a different unique name")
            if worker_type not in self._worker_classes:
                raise ProcessError(f"Type {worker_type} does not exist")
            # check if somebody tries to start a restricted worker type from outside this class
            if not self.check_restricted_access(worker_type):
                raise ProcessError(f"Worker of type {worker_type} can only be started by server.")
            
        for process in processes:
            worker_type = process["type"]
            name = process["name"]
            args = process["args"] if process['args'] else []
            worker_instance = self.create_worker(worker_type, *args)
            command_queue = multiprocessing.Queue()
            response_queue = multiprocessing.Queue()
            p = multiprocessing.Process(target=worker_instance.run, args=(command_queue, response_queue))
            p.start()
            print(f"started {name} of type {worker_type}")
            self.add_process(name, worker_type, p, command_queue, response_queue)

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

    def terminate_processes(self, names: List[str]) -> None:
        for name in names:
            self.check_for_running_process(name)
            worker_type = self._processes[name]["type"]
            # check if somebody tries to kill a restricted worker type from outside this class
            if not self.check_restricted_access(worker_type):
                raise ProcessError(f"Worker of type {worker_type} can only be terminated by server.")
        
        for name in names:
            p = self._processes[name]["process_instance"]
            worker_type = self._processes[name]["type"]
            p.terminate()
            p.join()
            del self._processes[name]
            print(f"terminated {name} of type {worker_type}")
            if worker_type in self._restricted_classes and self.check_restricted_access(worker_type):
                self.start_processes([self.find_process_in_config_by_name(name)])

    def wait_for_manager(self, finished_event: threading.Event, failed_event: threading.Event, name: str, manager: threading.Thread) -> None:
        while manager.is_alive():
            finished_event.wait(timeout=1000)
            if finished_event.is_set():
                del self._managers_dict[name]
                if failed_event.is_set():
                    self.terminate_processes([name])
                return
            
        if name in self._managers_dict:
            del self._managers_dict[name]
            print("manager is not alive anymore but hasn't finished")
        
    def send_command_to_manager(self, name: str, command: str, max_wait_time: int, args) -> Tuple[threading.Event, queue.Queue]:
        processed_event = threading.Event()
        response_queue = queue.Queue()

        self._managers_dict[name]["manager"].receive_command(command, max_wait_time, processed_event, response_queue, args)

        return processed_event, response_queue

    # this function should only be called by the spawner service and used as Thread
    def manage_process(self, name: str, command: str, max_wait_time: int, args) -> None:
        self.check_for_running_process(name)

        # Check if manager already exists
        if name not in self._managers_dict:
            finished_event = threading.Event()
            failed_event = threading.Event()
            self._managers_dict[name] = {
                "manager": Manager(self._processes[name]["command_queue"], self._processes[name]["response_queue"], finished_event, failed_event),
                "failed_event": failed_event,
            }
            processed_event, result_queue = self.send_command_to_manager(name, command, max_wait_time, args)

            manager_thread= threading.Thread(target=self._managers_dict[name]["manager"].handle_commands)
            waiter_thread = threading.Thread(target=self.wait_for_manager, args=(finished_event, failed_event, name, manager_thread))
            manager_thread.start()
            waiter_thread.start()
        else:
            try:
                processed_event, result_queue = self.send_command_to_manager(name, command, max_wait_time, args)
                failed_event = self._managers_dict[name]["failed_event"]
            except ProcessError as e:  
                e.message += f" for {name}. Try again later"

        is_processing = processed_event.wait(timeout=max_wait_time)
        if is_processing:
            try: 
                result = result_queue.get(timeout= max_wait_time)
                if isinstance(result, Exception):
                    raise result
                
                return
            except queue.Empty:
                raise ProcessError(f"Command {command} could not be executed in time {max_wait_time}. Hence process {name} is getting terminated")
            
        elif failed_event.is_set():
            raise ProcessError(f"An error occured in process {name}. Process is no longer alive.")
        else:
            raise ProcessError(f"Process {name} is busy and could not start command in time. Try again later.")
