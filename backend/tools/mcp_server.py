from mcp.server.fastmcp import FastMCP
from backend.tools.word_count import WordCountTool
from backend.tools.uppercase import UppercaseTool
from inspect import Signature, Parameter

mcp = FastMCP("internal tools")

TOOLS = [
    WordCountTool(),
    UppercaseTool(),
]

for tool in TOOLS:
    def make_handler(tool):
        props = tool.parameters.get("properties", {}) if getattr(tool, "parameters", None) else {}
        params = [Parameter(name, Parameter.POSITIONAL_OR_KEYWORD) for name in props.keys()]
        async def handler(**kwargs):
            return tool.execute(**kwargs)
        handler.__name__ = tool.name
        handler.__doc__ = tool.description
        handler.__signature__ = Signature(params)
        return handler

    mcp.add_tool(
        make_handler(tool),
        name=tool.name,
        description=tool.description,
    )