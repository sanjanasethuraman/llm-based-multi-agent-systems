from .uppercase import UppercaseTool
from .word_count import WordCountTool

TOOL_REGISTRY = {
    "uppercase": UppercaseTool(),
    "word_count": WordCountTool(),
}

def get_tool(name):
    return TOOL_REGISTRY.get(name)