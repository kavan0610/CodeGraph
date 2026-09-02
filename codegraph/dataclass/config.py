import os
import json
from dataclasses import dataclass, asdict
from typing import Optional

CONFIG_DIR = os.path.expanduser("~/.codegraph")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

@dataclass
class LLMConfig:
    provider: str        # 'openai', 'anthropic', 'gemini', 'ollama', 'custom'
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    @classmethod
    def load(cls) -> Optional["LLMConfig"]:
        if not os.path.exists(CONFIG_FILE):
            return None
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except Exception:
            return None

    @classmethod
    def show_current(cls):
        config = cls.load()
        if not config:
            print("No configuration found. Run 'codegraph config' to set one up.")
            return
        print("\nCurrent CodeGraph Configuration:")
        print("-" * 35)
        print(f"Provider : {config.provider}")
        print(f"Model    : {config.model}")
        print(f"Base URL : {config.base_url or 'Default'}")
        masked_key = (config.api_key[:6] + "..." + config.api_key[-4:]) if config.api_key and len(config.api_key) > 10 else ("Set" if config.api_key else "None")
        print(f"API Key  : {masked_key}")
        print(f"Config File: {CONFIG_FILE}\n")

    @classmethod
    def configure_interactive(cls) -> "LLMConfig":
        print("\nCodeGraph LLM Setup")
        print("-" * 35)
        print("Select your provider:")
        print(" [1] OpenAI (GPT-4o, etc.)")
        print(" [2] Anthropic Claude (Claude 3.5 Sonnet, etc.)")
        print(" [3] Google Gemini (Gemini 1.5 Pro/Flash, etc.)")
        print(" [4] Ollama (Local / Free)")
        print(" [5] Custom OpenAI-Compatible (Groq, DeepSeek, LM Studio, etc.)")

        choice = input("\nSelect [1-5]: ").strip()

        provider_map = {
            "1": ("openai", "gpt-4o-mini", None),
            "2": ("anthropic", "claude-3-5-sonnet-20241022", None),
            "3": ("gemini", "gemini-1.5-flash", None),
            "4": ("ollama", "llama3.1", "http://localhost:11434"),
            "5": ("custom", "", "")
        }

        provider, default_model, default_url = provider_map.get(choice, ("custom", "", ""))

        model = input(f"Enter model name [{default_model}]: ").strip() or default_model
        
        base_url = None
        if provider in ("ollama", "custom"):
            base_url = input(f"Enter Base URL [{default_url}]: ").strip() or default_url

        api_key = None
        if provider != "ollama":
            api_key = input("Enter API Key: ").strip()

        os.makedirs(CONFIG_DIR, exist_ok=True)
        config_obj = cls(provider=provider, model=model, api_key=api_key, base_url=base_url)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(config_obj), f, indent=2)

        print(f"\nConfiguration saved to {CONFIG_FILE}\n")
        return config_obj