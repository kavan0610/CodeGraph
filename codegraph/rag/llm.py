import os
from codegraph.dataclass.config import LLMConfig

class CodebaseAgent:
    def __init__(self):
        config = LLMConfig.load()
        if not config:
            config = LLMConfig.configure_interactive()

        self.config = config

        if config.api_key:
            if config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.api_key
            elif config.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = config.api_key
            elif config.provider == "gemini":
                os.environ["GEMINI_API_KEY"] = config.api_key
            elif config.provider in ("ollama", "custom"):
                os.environ["OPENAI_API_KEY"] = config.api_key

    def _get_formatted_model_string(self) -> str:
        """Formats model names into standard LiteLLM format."""
        p = self.config.provider
        m = self.config.model
        
        if p == "anthropic" and not m.startswith("anthropic/"):
            return f"anthropic/{m}"
        if p == "gemini" and not m.startswith("gemini/"):
            return f"gemini/{m}"
        if p == "ollama" and not m.startswith("ollama/"):
            return f"ollama/{m}"
        if p == "custom" and not m.startswith("openai/"):
            return f"openai/{m}"
            
        return m

    def chat(self, question: str, context: str):
        system_prompt = (
            "You are an elite software engineer analyzing a codebase.\n"
            "Answer questions strictly using the provided GraphRAG context.\n"
            "Always cite relevant file names, class names, and function names."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GRAPH CONTEXT:\n{context}\n\nQUESTION:\n{question}"}
        ]

        model_identifier = self._get_formatted_model_string()
        print(f"\nRunning inference with [{self.config.provider.upper()}: {self.config.model}]...\n")

        try:
            import litellm
            litellm.suppress_debug_info = True

            response = litellm.completion(
                model=model_identifier,
                messages=messages,
                api_base=self.config.base_url,
                temperature=0.2,
                stream=True
            )

            print("-" * 60)
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
            print("\n" + "-" * 60 + "\n")

        except Exception as e:
            error_msg = f"\nError contacting {self.config.provider} (or offline): {e}"
            print(error_msg)
            return error_msg