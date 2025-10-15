import asyncio
import signal
from typing import Dict

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from argussight.logger import configure_logger

app = FastAPI()

active_streams: Dict[str, Dict[str, any]] = {}
client_queues: Dict[WebSocket, asyncio.Queue] = {}

logger = configure_logger("StreamsProxy", "streams_proxy")


async def shutdown(loop, signal=None):
    logger.info(
        f"Received exit signal {signal.name if signal else 'unknown'}, shutting down..."
    )
    # Cancel all active tasks
    for path, info in active_streams.items():
        task = info.get("task")
        if task:
            task.cancel()
    # Wait for them to finish
    await asyncio.gather(
        *(t["task"] for t in active_streams.values()), return_exceptions=True
    )
    loop.stop()


@app.post("/add-stream")
async def add_stream(path: str, port: int, id: str) -> Dict[str, str]:
    if path in active_streams:
        return {"message": f"Stream already exists at path /{path}"}

    # Store the original WebSocket URL and path details
    original_ws_url = f"ws://localhost:{port}/ws/{id}"
    active_streams[path] = {"url": original_ws_url, "clients": set()}

    # Spawn the upstream worker
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(loop, s)))
    task = loop.create_task(upstream_worker(path, original_ws_url))
    active_streams[path]["task"] = task

    logger.info(f"Stream added at path /{path}")
    return {"message": f"Stream added at path /{path}"}


@app.post("/remove-stream")
async def remove_stream(path: str) -> Dict[str, str]:
    if path not in active_streams:
        return {"message": "Stream not found"}

    del active_streams[path]
    logger.info(f"Stream removed at path /{path}")

    return {"message": f"Stream removed at path /{path}"}


async def upstream_worker(path: str, url: str):
    """Keeps a single upstream connection open and broadcasts to all clients."""
    try:
        async with websockets.connect(url) as original_ws:
            logger.info(f"Connected upstream {url} for {path}")

            async for data in original_ws:
                clients = active_streams[path]["clients"].copy()
                for client in clients:
                    q = client_queues.get(client)
                    if q:
                        try:
                            q.put_nowait(data)
                        except asyncio.QueueFull:
                            logger.warning("Dropping frame for slow client")

    except Exception as e:
        logger.error(f"Upstream worker for {path} failed: {e}")
    finally:
        logger.info(f"Upstream for {path} closed")
        for client in active_streams.get(path, {}).get("clients", []):
            await client.close()
        active_streams.pop(path, None)


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
            data = await q.get()
            if isinstance(data, str):
                await websocket.send_text(data)
            else:
                await websocket.send_bytes(data)

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        stream_data["clients"].discard(websocket)
        client_queues.pop(websocket, None)
        await websocket.close()


def run(port: int = 7000) -> None:
    import uvicorn

    uvicorn.run(app, host="localhost", port=port)


if __name__ == "__main__":
    run()
