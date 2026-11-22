"""OpenAI Agents SDK: Agent + OpenAIChatCompletionsModel + MCPServerStdio. Gate wired in by subclassing get_response()."""
from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI


async def run(task, base_url, key, mcp_cmd, gate):
    class Gated(OpenAIChatCompletionsModel):
        async def get_response(self, *a, **k):
            gate()
            return await super().get_response(*a, **k)

    model = Gated(model="local/gemma", openai_client=AsyncOpenAI(base_url=base_url, api_key=key))
    async with MCPServerStdio(params={"command": mcp_cmd[0], "args": mcp_cmd[1:]}) as srv:
        agent = Agent(name="a", instructions="Use tools.", model=model, mcp_servers=[srv])
        r = await Runner.run(agent, task)
    return r.final_output
