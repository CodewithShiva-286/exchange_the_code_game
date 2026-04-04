import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8000/ws/run-code") as ws:
        await ws.send(json.dumps({
            "event": "start",
            "code": "name = input('enter name: ')\nprint('hello', name)",
            "language": "python"
        }))
        
        while True:
            try:
                res = await ws.recv()
                print("RECV:", res)
                data = json.loads(res)
                if data["type"] == "output" and "enter name" in data["data"]:
                    await ws.send(json.dumps({"event": "input", "data": "John\n"}))
            except websockets.exceptions.ConnectionClosed:
                print("CLOSED")
                break

asyncio.run(test())
