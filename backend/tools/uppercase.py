from .base import Tool

class UppercaseTool(Tool):
    name = "uppercase"
    description = "Converts input string to uppercase"

    parameters = {
        "type": "object",
        "properties": {
           "input_str": {
               "type": "string",
               "description": "The text to convert to uppercase"
           }
        },
        "required": ["input_str"]
    }


    def execute(self, input_str, **kwargs):
        return input_str.upper()