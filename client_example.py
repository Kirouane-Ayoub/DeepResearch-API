# import asyncio
import json

import aiohttp


class ResearchAPIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    async def start_research(
        self, topic: str, max_review_cycles: int = 3, timeout: int = 300
    ) -> str:
        """Start a new research session"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "topic": topic,
                "max_review_cycles": max_review_cycles,
                "timeout": timeout,
            }

            async with session.post(
                f"{self.base_url}/research/start", json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["session_id"]
                else:
                    raise Exception(f"Failed to start research: {response.status}")

    async def get_status(self, session_id: str) -> dict:
        """Get research session status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/research/{session_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get status: {response.status}")

    async def get_result(self, session_id: str) -> dict:
        """Get research result"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/research/{session_id}/result"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get result: {response.status}")

    async def stream_progress(self, session_id: str, callback=None):
        """Stream progress updates via WebSocket"""
        import websockets

        uri = f"ws://localhost:8000/research/{session_id}/ws"

        try:
            async with websockets.connect(uri) as websocket:
                async for message in websocket:
                    data = json.loads(message)
                    if callback:
                        await callback(data)
                    else:
                        print(f"Progress: {data}")
        except Exception as e:
            print(f"WebSocket error: {e}")


# # Example usage
# async def main():
#     client = ResearchAPIClient()

#     # Start research
#     session_id = await client.start_research(
#         topic="Brief history of machine learning development",
#         max_review_cycles=2
#     )
#     print(f"Started research session: {session_id}")

#     # Stream progress
#     async def progress_callback(data):
#         print(f"[{data['type']}] {data.get('message', '')}")

#         if data['type'] == 'completed':
#             print("Research completed!")
#             print(f"Result: {data['result'][:200]}...")

#     await client.stream_progress(session_id, progress_callback)

# if __name__ == "__main__":
#     asyncio.run(main())
