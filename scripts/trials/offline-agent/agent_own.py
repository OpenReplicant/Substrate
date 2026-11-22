"""Own loop: the `mcp` SDK (stdio client) plus `openai` against a base URL. Our code makes every model call."""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI


async def run(task, base_url, key, mcp_cmd, gate):
    client = AsyncOpenAI(base_url=base_url, api_key=key)
    params = StdioServerParameters(command=mcp_cmd[0], args=mcp_cmd[1:])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                                   "parameters": t.input_schema}} for t in (await s.list_tools()).tools]
        msgs = [{"role": "user", "content": task}]
        while True:
            gate()   # our code decides, before every model call
            resp = await client.chat.completions.create(model="local/gemma", messages=msgs, tools=tools)
            m = resp.choices[0].message
            if not m.tool_calls:
                return m.content
            msgs.append({"role": "assistant", "content": m.content, "tool_calls": [c.model_dump() for c in m.tool_calls]})
            for c in m.tool_calls:
                res = await s.call_tool(c.function.name, json.loads(c.function.arguments))
                msgs.append({"role": "tool", "tool_call_id": c.id, "content": "".join(x.text for x in res.content)})
