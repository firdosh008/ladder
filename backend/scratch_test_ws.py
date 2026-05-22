import asyncio
import json
import logging
from uuid import UUID

import websockets
import httpx

from app.config import settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def test_stream():
    url = "http://127.0.0.1:8001/mcp"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "run_research",
            "arguments": {
                "query": "Future of AI Agents",
                "context": {},
                "config": {"cost_ceiling": 0.01, "timeout_seconds": 60},
                "async": True
            }
        },
        "id": 1
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        print("MCP Initial Response:", data)
        
        result_obj = data.get("result", {})
        content = result_obj.get("content", [{}])[0].get("text", "{}")
        parsed = json.loads(content)
        run_data = parsed.get("data", {})
        
        run_id = run_data.get("run_id")
        ws_url = run_data.get("websocket_url")
        
        print(f"Run ID: {run_id}, WS: {ws_url}")
        
        if not ws_url:
            return
            
        full_ws_url = f"ws://127.0.0.1:8001{ws_url}"
        print(f"Connecting to {full_ws_url}")
        
        async with websockets.connect(full_ws_url) as ws:
            while True:
                msg = await ws.recv()
                print("WS EVENT:", msg)
                msg_data = json.loads(msg)
                
                # Check if it's finished via polling
                res = await client.post(url, json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "get_research_result", "arguments": {"run_id": run_id}},
                    "id": 2
                })
                r_data = res.json()
                r_content = r_data.get("result", {}).get("content", [{}])[0].get("text", "{}")
                r_parsed = json.loads(r_content).get("data", {})
                if r_parsed.get("status") in ("complete", "failed"):
                    print("Run Finished!", r_parsed.get("status"))
                    break

if __name__ == "__main__":
    asyncio.run(test_stream())
