class WordCountTool:
    def run(self, input_str, conf):
        return f"{conf.get('name', 'WordCountTool')} counted {len(input_str.split())} words."