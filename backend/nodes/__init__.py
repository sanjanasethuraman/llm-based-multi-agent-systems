from .input import InputNodeExecutor
from .output import OutputNodeExecutor
from .agent import AgentNodeExecutor
from .tool import ToolNodeExecutor
from .retriever import RetrieverNodeExecutor
from .vector_db import VectorDBNodeExecutor

NODE_EXECUTORS = {
    "input": InputNodeExecutor(),
    "output": OutputNodeExecutor(),
    "agent": AgentNodeExecutor(),
    "sub_agent": AgentNodeExecutor(),
    "tool": ToolNodeExecutor(),
    "retriever": RetrieverNodeExecutor(),
    "vector_db": VectorDBNodeExecutor(),
}

def get_node_executor(node_type):
    return NODE_EXECUTORS.get(node_type)
