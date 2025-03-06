from typing import Dict

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, status

from argussight.logger import configure_logger

app = FastAPI()

# Active storages for available streams
active_streams: Dict[str, Dict[str, str]] = {}

logger = configure_logger("StreamsProxy", "streams_proxy")


@app.post("/add-stream")
async def add_stream(path: str, port: int, id: str) -> Dict[str, str]:
    if path in active_streams:
        return {"message": f"Stream already exists at path /{path}"}

    # Store the original WebSocket URL and path details
    original_ws_url = f"ws://localhost:{port}/ws/{id}"
    active_streams[path] = {"url": original_ws_url}
    logger.info(f"Stream added at path /{path}")
    return {"message": f"Stream added at path /{path}"}


@app.post("/remove-stream")
async def remove_stream(path: str) -> Dict[str, str]:
    if path not in active_streams:
        return {"message": "Stream not found"}

    del active_streams[path]
    logger.info(f"Stream removed at path /{path}")

    return {"message": f"Stream removed at path /{path}"}


@app.websocket("/ws/{path}")
async def websocket_proxy(websocket: WebSocket, path: str) -> None:
    # Check if stream available otherwise close connection
    stream_data = active_streams.get(path)
    if not stream_data:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Resource not available"
        )

    await websocket.accept()

    original_ws_url = stream_data["url"]

    try:
        # Connect to the original WebSocket server
        async with websockets.connect(original_ws_url) as original_ws:
            logger.info(f"Connected to original WebSocket stream at {original_ws_url}")

            # Relay data between original WebSocket and JSMpeg client
            while True:
                if active_streams.get(path) is None:
                    websocket.close(reason="Stream was removed")
                    break
                binary_data = await original_ws.recv()
                await websocket.send_bytes(binary_data)

    except WebSocketDisconnect:
        logger.info("Connection with client closed")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(f"Connection to original WebSocket stream closed: {e}")
        await remove_stream(path)
        await websocket.close()


def run(port: int = 7000) -> None:
    import uvicorn

    uvicorn.run(app, host="localhost", port=port)


if __name__ == "__main__":
    run()
