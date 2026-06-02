class AgentProvider:
    name = "base"

    def run(self, config, incoming):
        raise NotImplementedError("Subclasses must implement the run method.")