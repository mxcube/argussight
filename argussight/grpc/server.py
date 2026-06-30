import logging
import signal
import time
from concurrent import futures
from threading import Event

import grpc

import argussight.grpc.argus_service_pb2 as pb2
import argussight.grpc.argus_service_pb2_grpc as pb2_grpc
from argussight.core.config import CollectorConfiguration
from argussight.core.spawner import ProcessError, Spawner
from argussight.grpc.helper_functions import pack_to_any, unpack_from_any

logger = logging.getLogger("GRPC Server")


def check_shutdown_event(func):
    """
    Decorator to check if the shutdown event is set before processing the request.
    If the shutdown event is set, it aborts the request with a GRPC UNAVAILABLE status.
    """

    def wrapper(self, request, context, *args, **kwargs):
        if self.shutdown_event.is_set():
            context.abort(grpc.StatusCode.UNAVAILABLE, "Server is shutting down.")
        return func(self, request, context, *args, **kwargs)

    return wrapper


class SpawnerService(pb2_grpc.SpawnerServiceServicer):
    """
    gRPC service for managing processes.
    """

    def __init__(self, collector_config, shutdown_event: Event):
        """
        Intializes the SpawnerService

        Args:
            collector_config: Configuration for the collector.
            shutdown_event: Event to signal server shutdown.
        """
        self.spawner = Spawner(collector_config)
        self._min_waiting_time = 1
        self.shutdown_event = shutdown_event

    @check_shutdown_event
    def StartProcesses(self, request, context):
        """
        Starts a process based on the provided request.

        Args:
            request (pb2.StartProcessesRequest): gRPC request containing process details.
            context: gRPC context object.

        Returns:
            pb2.StartProcessesResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.start_process(request.name, request.type)
            return pb2.StartProcessesResponse(status="success")
        except ProcessError as e:
            logger.error(f"Error starting process {request.name}: {str(e)}")
            return pb2.StartProcessesResponse(
                status="failure", error_message="Failed to start process"
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error starting process {request.name}: {str(e)}"
            )
            return pb2.StartProcessesResponse(
                status="failure", error_message="An unexpected error occured"
            )

    @check_shutdown_event
    def TerminateProcesses(self, request, context):
        """
        Terminates one or more processes based on the provided request.

        Args:
            request (pb2.TerminateProcessesRequest): gRPC request containing process names.
            context: gRPC context object.

        Returns:
            pb2.TerminateProcessesResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.terminate_processes(request.names)
            return pb2.TerminateProcessesResponse(status="success")
        except ProcessError as e:
            logger.error(f"Error terminating processes {request.names}: {str(e)}")
            return pb2.TerminateProcessesResponse(
                status="failure", error_message="Failed to terminate processes"
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error terminating processes {request.names}: {str(e)}"
            )
            return pb2.TerminateProcessesResponse(
                status="failure", error_message="An unexpected error occured"
            )

    @check_shutdown_event
    def ManageProcesses(self, request, context):
        """
        Manages a process based on the provided request.

        Args:
            request (pb2.ManageProcessesRequest): gRPC request containing process command details.
            context: gRPC context object.

        Returns:
            pb2.ManageProcessesResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.manage_process(
                request.name,
                request.command,
                {},
            )
            return pb2.ManageProcessesResponse(status="success")
        except ProcessError as e:
            logger.error(f"Error managing process {request.name}: {str(e)}")
            return pb2.ManageProcessesResponse(
                status="failure", error_message="Unable to manage process"
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error managing process {request.name}: {str(e)}"
            )
            return pb2.ManageProcessesResponse(
                status="failure", error_message="An unexpected error occured"
            )

    @check_shutdown_event
    def GetProcesses(self, request, context):
        """
        Retrieves the currently running processes and available process types.

        Args:
            request (pb2.GetProcessesRequest): Empty gRPC request.
            context: gRPC context object.

        Returns:
            pb2.GetProcessesResponse: gRPC response containing running processes and available types.
        """
        try:
            running_processes, available_types, streams = self.spawner.get_processes()
            running_dict = {}
            for name, process in running_processes.items():
                settings = {}
                for key, setting in process["settings"].items():
                    settings[key] = pack_to_any(setting)
                running_dict[name] = pb2.RunningProcessDictionary(
                    type=process["type"],
                    commands=process["commands"],
                    settings=settings,
                )
            return pb2.GetProcessesResponse(
                status="success",
                running_processes=running_dict,
                available_process_types=available_types,
                streams=streams,
            )
        except Exception as e:
            logger.exception(f"Unexpected error retrieving processes: {str(e)}")
            return pb2.GetProcessesResponse(
                status="failure", error_message="Could not retrieve processes"
            )

    @check_shutdown_event
    def ChangeSettings(self, request, context):
        """
        Changes the settings of a process based on the provided request.

        Args:
            request (pb2.ChangeSettingsRequest): gRPC request containing process settings.
            context: gRPC context object.

        Returns:
            pb2.ChangeSettingsResponse: gRPC response indicating success or failure.
        """
        try:
            settings = {}
            for key, any_object in request.settings.items():
                settings[key] = unpack_from_any(any_object)
            self.spawner.manage_process(request.name, "settings", [settings])
            return pb2.ChangeSettingsResponse(status="success")
        except ProcessError as e:
            logger.error(f"Error changing settings {request.name}: {str(e)}")
            return pb2.ChangeSettingsResponse(
                status="failure", error_message="Could not change settings"
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error while changing settings of {request.name}: {str(e)}"
            )
            return pb2.ChangeSettingsResponse(
                status="failure", error_message="An unexpected error occured"
            )

    @check_shutdown_event
    def AddStream(self, request, context):
        """
        Adds a stream to a process based on the provided request.

        Args:
            request (pb2.AddStreamRequest): gRPC request containing stream details.
            context: gRPC context object.

        Returns:
            pb2.AddStreamResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.add_stream(request.name, request.port, request.stream_id)
            return pb2.AddStreamResponse(status="success")
        except Exception as e:
            logger.exception(f"Unexpected error while adding stream: {str(e)}")
            return pb2.AddStreamResponse(
                status="failure", error_message=f"Couldn't add stream {request.name}"
            )

    @check_shutdown_event
    def RemoveStream(self, request, context):
        """
        Removes a stream based on the provided request.

        Args:
            request (pb2.RemoveStreamRequest): gRPC request containing stream name.
            context: gRPC context object.

        Returns:
            pb2.RemoveStreamResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.remove_stream(request.name)
            return pb2.RemoveStreamResponse(status="success")
        except Exception as e:
            logger.exception(f"Unexpected error while removing stream: {str(e)}")
            return pb2.RemoveStreamResponse(
                status="failure", error_message=f"Couldn't remove stream {request.name}"
            )

    @check_shutdown_event
    def HideStream(self, request, context):
        """
        Hides a stream based on the provided request.

        Args:
            request (pb2.HideStreamRequest): gRPC request containing stream name and reason to hide.
            context: gRPC context object.

        Returns:
            pb2.HideStreamResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.hide_stream(request.name, request.reason_to_hide)
            return pb2.HideStreamResponse(status="success")
        except Exception as e:
            logger.exception(f"Unexpected error while hiding stream: {str(e)}")
            return pb2.HideStreamResponse(
                status="failure", error_message=f"Couldn't hide stream {request.name}"
            )

    @check_shutdown_event
    def ShowStream(self, request, context):
        """
        Shows a stream based on the provided request.

        Args:
            request (pb2.ShowStreamRequest): gRPC request containing stream name.
            context: gRPC context object.

        Returns:
            pb2.ShowStreamResponse: gRPC response indicating success or failure.
        """
        try:
            self.spawner.show_stream(request.name)
            return pb2.ShowStreamResponse(status="success")
        except Exception as e:
            logger.exception(f"Unexpected error while showing stream: {str(e)}")
            return pb2.ShowStreamResponse(
                status="failure", error_message=f"Couldn't show stream {request.name}"
            )


def serve(collector_config: CollectorConfiguration):
    """
    Starts the gRPC server and listens for incoming requests.

    Args:
        collector_config: Configuration for the collector.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    shutdown_event = Event()
    spawner_service = SpawnerService(collector_config, shutdown_event)
    pb2_grpc.add_SpawnerServiceServicer_to_server(spawner_service, server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logger.info("Server started on port 50051")

    def handle_shutdown_signal(signum, frame):
        logger.info(f"Received shutdown signal ({signum}). Initiating shutdown...")
        shutdown_event.set()  # this prevents server from threating new requests

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    try:
        while not shutdown_event.is_set():
            time.sleep(1)
    finally:
        logger.info("Server shutting down...")

        server.stop(grace=10)  # Allow server to finish processing current requests

        try:
            spawner_service.spawner.cleanup()
            logger.info("Spawner cleanup completed successfully.")
        except Exception as e:
            logger.error(f"Error during spawner cleanup: {str(e)}")

        logger.info("Server stopped.")
