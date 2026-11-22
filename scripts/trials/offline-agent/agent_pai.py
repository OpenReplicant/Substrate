"""pydantic-ai: Agent + OpenAIChatModel + MCPToolset (stdio). Gate wired in by subclassing the model's request()."""
import sys
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


async def run(task, base_url, key, mcp_cmd, gate):
    class Gated(OpenAIChatModel):
        async def request(self, messages, model_settings, model_request_parameters):
            gate()
            return await super().request(messages, model_settings, model_request_parameters)

    model = Gated("local/gemma", provider=OpenAIProvider(base_url=base_url, api_key=key))
    tools = MCPToolset(StdioTransport(command=mcp_cmd[0], args=mcp_cmd[1:]))
    agent = Agent(model, toolsets=[tools])
    async with agent:
        r = await agent.run(task)
    return r.output
