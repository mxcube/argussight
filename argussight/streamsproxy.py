import asyncio
import contextlib
import multiprocessing
import queue
import signal
from typing import Dict

import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from argussight.logger import configure_logger

app = FastAPI()

active_streams: Dict[str, Dict[str, any]] = {}
client_queues: Dict[WebSocket, asyncio.Queue] = {}

logger = configure_logger("StreamsProxy", "streams_proxy")
shutdown_event = asyncio.Event()


async def add_stream(path: str, port: int, id: str) -> Dict[str, str]:
    if path in active_streams:
        return {"message": f"Stream already exists at path /{path}"}

    # Store the original WebSocket URL and path details
    original_ws_url = f"ws://localhost:{port}/ws/{id}"
    active_streams[path] = {
        "url": original_ws_url,
        "clients": set(),
        "hidden": False,
        "reason_to_hide": "",
    }

    # Spawn the upstream worker
    task = asyncio.create_task(upstream_worker(path, original_ws_url))
    active_streams[path]["task"] = task

    logger.info(f"Stream added at path /{path}")
    return {"message": f"Stream added at path /{path}"}


async def remove_stream(path: str) -> Dict[str, str]:
    stream = active_streams.pop(path, None)

    if stream is None:
        return {"message": f"No stream exists at path /{path}"}

    task = stream.get("task", None)
    logger.info(
        f"Removing stream at path /{path} with {len(stream.get('clients', []))} active clients"
    )

    # First disconnect clients
    clients = stream.get("clients", set())
    for client in clients:
        client_queues.pop(client, None)
        await client.close(code=1000, reason="Stream removed by server")

    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    return {"message": f"Stream removed at path /{path}"}


async def hide_stream(path: str, reason_to_hide: str) -> Dict[str, str]:
    stream = active_streams.get(path)
    if not stream:
        return {"message": f"No stream exists at path /{path}"}

    stream["hidden"] = True
    stream["reason_to_hide"] = reason_to_hide
    logger.info(f"Stream hidden at path /{path}")
    return {"message": f"Stream hidden at path /{path}"}


async def show_stream(path: str) -> Dict[str, str]:
    stream = active_streams.get(path)
    if not stream:
        return {"message": f"No stream exists at path /{path}"}

    stream["hidden"] = False
    stream["reason_to_hide"] = ""
    logger.info(f"Stream shown at path /{path}")
    return {"message": f"Stream shown at path /{path}"}


async def command_consumer(command_queue: multiprocessing.Queue):
    while True:
        try:
            # Use asyncio.to_thread to call the blocking get method of the multiprocessing.Queue
            # We use a timeout to periodically check for cancellation and avoid blocking indefinitely
            command = await asyncio.to_thread(command_queue.get, timeout=1)
        except queue.Empty:
            if shutdown_event.is_set():
                logger.info("Server shutdown initiated, stopping command consumer...")
                break
            continue

        if not command["action"]:
            logger.warning("Received command without action")
            continue

        match command["action"]:
            case "add_stream":
                await add_stream(command["path"], command["port"], command["id"])
            case "remove_stream":
                await remove_stream(command["path"])
            case "shutdown_streams":
                await shutdown_streams()
            case "hide_stream":
                await hide_stream(command["path"], command["reason_to_hide"])
            case "show_stream":
                await show_stream(command["path"])
            case "shutdown_server":
                logger.info(
                    "Received shutdown command from spawner, initiating server shutdown..."
                )
                shutdown_event.set()
                await shutdown_streams()
                return
            case _:
                logger.warning(f"Unknown command action: {command['action']}")


async def upstream_worker(path: str, url: str):
    """Keeps a single upstream connection open and broadcasts to all clients."""
    reconnection_tries = 0
    while True:
        try:
            async with websockets.connect(url) as original_ws:
                logger.info(f"Connected upstream {url} for {path}")
                if shutdown_event.is_set():
                    logger.info(
                        f"Server shutdown initiated, stopping upstream worker for {path}..."
                    )
                    break
                async for data in original_ws:
                    clients = active_streams[path]["clients"].copy()
                    for client in clients:
                        q = client_queues.get(client)
                        if q:
                            try:
                                if active_streams[path]["hidden"]:
                                    q.put_nowait(active_streams[path]["reason_to_hide"])
                                else:
                                    q.put_nowait(data)
                                reconnection_tries = 0  # Reset on successful send
                            except asyncio.QueueFull:
                                logger.warning("Dropping frame for slow client")
        except asyncio.CancelledError:
            logger.info(f"Upstream worker for {path} cancelled")
            break
        except Exception as e:
            if shutdown_event.is_set():
                logger.info(
                    f"Server shutdown initiated, stopping upstream worker for {path}..."
                )
                break
            logger.error(f"Upstream worker for {path} failed: {e}")
            if reconnection_tries >= 3:
                logger.error(
                    f"Max reconnection attempts reached for {path}, shutting down."
                )
                logger.info(f"Removing stream at path /{path} due to upstream failure")
                await remove_stream(path)
                break
            reconnection_tries += 1
            logger.info(f"Reconnecting upstream for {path} in 2 seconds...")
            await asyncio.sleep(2)
            logger.info(f"Reconnecting upstream for {path}")


@app.websocket("/ws/{path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    stream_data = active_streams.get(path)
    if not stream_data:
        await websocket.close(code=4404, reason="Resource not available")
        return

    await websocket.accept()
    logger.info(f"Client connected to {path}")

    q = asyncio.Queue(maxsize=5)
    client_queues[websocket] = q
    stream_data["clients"].add(websocket)

    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=1.0)
                if isinstance(data, str):
                    await websocket.send_text(data)
                else:
                    await websocket.send_bytes(data)
            except asyncio.TimeoutError:
                if shutdown_event.is_set():
                    logger.info(
                        "Server shutdown initiated, closing client connection..."
                    )
                    break
                continue

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        stream_data["clients"].discard(websocket)
        client_queues.pop(websocket, None)
        await websocket.close()


async def shutdown_streams() -> Dict[str, str]:
    paths = list(active_streams.keys())
    try:
        logger.info(f"Shutting down all streams: {paths}")
        for path in paths:
            await remove_stream(path)
    except Exception as e:
        logger.error(f"Error shutting down streams: {str(e)}")
        return {"message": "Error shutting down streams"}
    return {"message": "All streams shutdown"}


def run(command_queue: multiprocessing.Queue, port: int = 7000) -> None:
    async def run_server(stop_event: asyncio.Event):
        config = uvicorn.Config(app, host="0.0.0.0", port=port)
        server = uvicorn.Server(config)

        @app.on_event("startup")
        async def startup():
            app.state.command_task = asyncio.create_task(
                command_consumer(command_queue)
            )

        async def stop_when_event_is_set():
            await stop_event.wait()
            server.should_exit = True

        watcher_task = asyncio.create_task(stop_when_event_is_set())

        try:
            await server.serve()
        finally:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task

    async def main():
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)

        await run_server(shutdown_event)

    asyncio.run(main())


if __name__ == "__main__":
    run()
