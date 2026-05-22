import json
import unittest

from fastapi.testclient import TestClient

from research_agent.main import app


class McpContractTests(unittest.TestCase):
    def test_mcp_lists_standalone_tools_without_auth_fields(self):
        client = TestClient(app)
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        tools = body["result"]["tools"]
        names = {tool["name"] for tool in tools}

        self.assertIn("run_research", names)
        self.assertIn("get_research_result", names)
        self.assertIn("list_sources", names)
        self.assertIn("run_eval", names)

        schema_text = json.dumps(tools)
        self.assertIn("output_mode", schema_text)
        self.assertIn("context", schema_text)
        self.assertNotIn("bearerToken", schema_text)
        self.assertNotIn("accessToken", schema_text)

    def test_mcp_initialize_returns_server_info(self):
        client = TestClient(app)
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "initialize"})

        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertEqual(result["serverInfo"]["name"], "standalone-research-agent-mcp")
        self.assertIn("tools", result["capabilities"])


if __name__ == "__main__":
    unittest.main()
