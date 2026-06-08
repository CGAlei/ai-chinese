# app/openrouter_client.py

import os
import yaml
import json
import re
from openai import AsyncOpenAI

class OpenRouterClient:
    def __init__(self, api_key: str = None, default_model: str = None, config_path: str = "config/prompts.yaml"):
        # Resolve path relative to generator folder
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_config_path = os.path.join(base_dir, config_path)
        
        with open(abs_config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.global_config = self.config.get("global", {})
        self.default_model = default_model or self.global_config.get("default_model", "moonshotai/kimi-k2.6:free")
        self.default_temp = self.global_config.get("default_temperature", 0.7)
        self.extra_headers = self.global_config.get("openrouter_headers", {})
        
        resolved_api_key = api_key or os.getenv("OPENROUTER_API_KEY", "") or "dummy_key_to_avoid_sdk_exception"
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=resolved_api_key,
            default_headers=self.extra_headers
        )

    async def _call_with_retry(self, model: str, messages: list, temperature: float) -> tuple[str, int, int]:
        import asyncio
        import random
        max_attempts = 8  # Increased from 5 to 8 to handle free tier rate limits
        for attempt in range(max_attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response received from the model.")
                
                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, 'usage') and response.usage:
                    prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
                    completion_tokens = getattr(response.usage, 'completion_tokens', 0)
                
                return content, prompt_tokens, completion_tokens
            except Exception as e:
                err_str = str(e).lower()
                is_empty_response = isinstance(e, ValueError) and "empty response" in err_str
                is_rate_limit = "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str or "too many requests" in err_str
                
                if (is_rate_limit or is_empty_response) and attempt < max_attempts - 1:
                    wait_time = (2 ** attempt) + random.uniform(0.5, 2.5)
                    reason = "Empty response" if is_empty_response else "Rate limited (429)"
                    print(f"{reason} on {model}. Retrying in {wait_time:.2f}s... (Attempt {attempt + 1}/{max_attempts})")
                    await asyncio.sleep(wait_time)
                    continue
                raise e

    async def get_structured_data(self, word: str, card_type: str = "bisilabo", model: str = None, log_callback=None) -> tuple[dict, int, int]:
        cfg = self.config.get("templates", {}).get(card_type, {}).get("structured_data", {})
        if not cfg:
            raise ValueError(f"Structured data configuration not found for card type '{card_type}'")

        sys_prompt = cfg.get("system_prompt", "")
        user_prompt = cfg.get("user_prompt", "").format(word=word)
        temp = cfg.get("temperature", 0.1)
        target_model = model or cfg.get("model") or self.default_model

        if log_callback:
            await log_callback(f"Calling OpenRouter structured data extract (Card Type: {card_type}, Model: {target_model})...")

        content, prompt_tokens, completion_tokens = await self._call_with_retry(
            model=target_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temp
        )

        match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        json_str = match.group(1).strip() if match else content.strip()
        return json.loads(json_str), prompt_tokens, completion_tokens

    async def get_narrative_section(self, word: str, pinyin: str, section_name: str, card_type: str = "bisilabo", model: str = None, log_callback=None) -> tuple[str, int, int]:
        cfg = self.config.get("templates", {}).get(card_type, {}).get(section_name, {})
        if not cfg:
            raise ValueError(f"Section '{section_name}' not found for card type '{card_type}' in configuration")

        sys_prompt = cfg.get("system_prompt", "")
        user_prompt = cfg.get("user_prompt", "").format(word=word, pinyin=pinyin)
        temp = cfg.get("temperature", self.default_temp)
        target_model = model or cfg.get("model") or self.default_model

        if log_callback:
            await log_callback(f"Generating narrative section '{section_name}' (Card Type: {card_type}, Model: {target_model})...")

        content, prompt_tokens, completion_tokens = await self._call_with_retry(
            model=target_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temp
        )

        return content.strip(), prompt_tokens, completion_tokens

