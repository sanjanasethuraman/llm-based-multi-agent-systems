class Tool:
    name = ""
    description = ""

    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, **kwargs):
        raise NotImplementedError("Subclasses must implement the execute method.")