class AgentProvider:
    name = "base"

    def run(self, config, incoming, available_tools):
        raise NotImplementedError("Subclasses must implement the run method.")