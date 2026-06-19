from .base import Tool

class WordCountTool(Tool):
    name="word_count"
    description="Counts the number of words in the input string."
    parameters = {
        "type": "object",
        "properties": {
            "input_str": {
                "type": "string",
                "description": "The text to count words in."
            }
        },
        "required": ["input_str"]
    }

    def execute(self, input_str, **kwargs):
        return f"{self.name} counted {len(input_str.split())} words."