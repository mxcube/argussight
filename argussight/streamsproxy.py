import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from argussight.logger import configure_logger

app = FastAPI()

# Active streams storage for tracking different paths
active_streams = {}

logger = configure_logger("StreamsProxy", "streams_proxy")


@app.post("/add-stream")
async def add_stream(path: str, port: int, id: str):
    # Store the original WebSocket URL and path details
    original_ws_url = f"ws://localhost:{port}/ws/{id}"
    active_streams[path] = {"url": original_ws_url}
    return {"message": f"Stream added at path /{path}"}


@app.post("/remove-stream")
async def remove_stream(path: str):
    if path not in active_streams:
        return {"message": "Stream not found"}
    del active_streams[path]
    return {"message": f"Stream removed at path /{path}"}


@app.websocket("/ws/{path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    # Accept the connection from the JSMpeg client
    await websocket.accept()

    stream_data = active_streams.get(path)
    if not stream_data:
        await websocket.send_text("Stream not found")
        await websocket.close()
        return

    original_ws_url = stream_data["url"]

    try:
        # Connect to the original WebSocket server
        async with websockets.connect(original_ws_url) as original_ws:
            logger.info(f"Connected to original WebSocket stream at {original_ws_url}")

            # Relay data between original WebSocket and JSMpeg client
            while True:
                binary_data = await original_ws.recv()
                await websocket.send_bytes(binary_data)
    except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed) as e:
        logger.error(f"WebSocket disconnected: {e}")
    finally:
        await websocket.close()
        logger.info("Connection with JSMpeg client closed")


def run(port: int = 7000) -> None:
    import uvicorn

    uvicorn.run(app, host="localhost", port=port)


if __name__ == "__main__":
    run()
