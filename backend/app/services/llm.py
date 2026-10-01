"""
Unified LLM Provider Service.
Supports Groq (Llama 3.3 70B, Llama 3.1 8B), Gemini, and OpenAI with automatic JSON extraction.
"""

import json
import re
import structlog
from typing import Dict, Any, Optional, List, Union

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class LLMClient:
    """Unified LLM client interface for Groq, Gemini, and OpenAI."""

    def __init__(self):
        self.provider = settings.llm_provider.lower()
        self.openrouter_client = None
        self.hf_client = None
        self.nvidia_client = None
        self.groq_client = None
        self.gemini_model = None
        self.is_configured = False

        # 0. Initialize OpenRouter (Primary option)
        if settings.openrouter_api_key or self.provider == "openrouter":
            if settings.openrouter_api_key:
                try:
                    from openai import OpenAI
                    self.openrouter_client = OpenAI(
                        base_url=settings.openrouter_base_url,
                        api_key=settings.openrouter_api_key,
                        default_headers={
                            "HTTP-Referer": "https://github.com/research-assist",
                            "X-Title": "research_assist",
                        }
                    )
                    self.provider = "openrouter"
                    self.is_configured = True
                    logger.info("Initialized OpenRouter LLM client", model=settings.openrouter_model)
                except ImportError:
                    logger.warning("openai package not installed. Run `pip install openai`")
                except Exception as e:
                    logger.error("Failed to initialize OpenRouter client", error=str(e))

        # 1. Initialize Hugging Face (Alternative)
        if not self.is_configured and (settings.hf_api_key or self.provider == "huggingface"):
            if settings.hf_api_key:
                try:
                    from openai import OpenAI
                    self.hf_client = OpenAI(
                        base_url=settings.hf_base_url,
                        api_key=settings.hf_api_key,
                    )
                    self.provider = "huggingface"
                    self.is_configured = True
                    logger.info("Initialized Hugging Face LLM client", model=settings.hf_model)
                except ImportError:
                    logger.warning("openai package not installed. Run `pip install openai`")
                except Exception as e:
                    logger.error("Failed to initialize Hugging Face client", error=str(e))

        # 2. Initialize NVIDIA NIM (build.nvidia.com - Alternative)
        if not self.is_configured and (settings.nvidia_api_key or self.provider == "nvidia"):
            if settings.nvidia_api_key:
                try:
                    from openai import OpenAI
                    self.nvidia_client = OpenAI(
                        base_url=settings.nvidia_base_url,
                        api_key=settings.nvidia_api_key,
                    )
                    self.provider = "nvidia"
                    self.is_configured = True
                    logger.info("Initialized NVIDIA NIM LLM client (build.nvidia.com)", model=settings.nvidia_model)
                except ImportError:
                    logger.warning("openai package not installed. Run `pip install openai`")
                except Exception as e:
                    logger.error("Failed to initialize NVIDIA NIM client", error=str(e))

        # 3. Initialize Groq (Alternative)
        if not self.is_configured and settings.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=settings.groq_api_key)
                self.provider = "groq"
                self.is_configured = True
                logger.info("Initialized Groq LLM client", model=settings.groq_model)
            except ImportError:
                logger.warning("groq package not installed. Run `pip install groq`")
            except Exception as e:
                logger.error("Failed to initialize Groq client", error=str(e))

        # 4. Initialize Gemini (Alternative)
        if not self.is_configured and settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self.gemini_model = genai.GenerativeModel(settings.gemini_model)
                self.provider = "gemini"
                self.is_configured = True
                logger.info("Initialized Gemini LLM client", model=settings.gemini_model)
            except Exception as e:
                logger.error("Failed to initialize Gemini client", error=str(e))

        if not self.is_configured:
            logger.warning(
                "No LLM API key configured. System will operate in heuristic fallback mode."
            )

    @property
    def model_name(self) -> str:
        """Get the active model identifier."""
        if self.provider == "openrouter":
            return settings.openrouter_model
        elif self.provider == "huggingface":
            return settings.hf_model
        elif self.provider == "nvidia":
            return settings.nvidia_model
        elif self.provider == "groq":
            return settings.groq_model
        elif self.provider == "gemini":
            return settings.gemini_model
        return "heuristic-fallback"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        json_mode: bool = False,
        timeout: float = 300.0,
    ) -> str:
        """
        Generate completion text from the active LLM provider.
        """
        if not self.is_configured:
            raise ValueError(
                "No LLM API key configured. Please set OPENROUTER_API_KEY, HF_API_KEY, "
                "NVIDIA_API_KEY, or GROQ_API_KEY in your .env file."
            )

        # OpenRouter execution
        if self.provider == "openrouter" and self.openrouter_client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            extra_params = {}
            if json_mode:
                extra_params["response_format"] = {"type": "json_object"}

            response = self.openrouter_client.chat.completions.create(
                model=settings.openrouter_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **extra_params,
            )
            return response.choices[0].message.content or ""

        # Hugging Face execution
        if self.provider == "huggingface" and self.hf_client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.hf_client.chat.completions.create(
                model=settings.hf_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""

        # NVIDIA NIM execution (build.nvidia.com)
        if self.provider == "nvidia" and self.nvidia_client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            extra_params = {}
            if json_mode:
                extra_params["response_format"] = {"type": "json_object"}

            response = self.nvidia_client.chat.completions.create(
                model=settings.nvidia_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **extra_params,
            )
            return response.choices[0].message.content or ""

        # Groq execution
        if self.provider == "groq" and self.groq_client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            extra_params = {}
            if json_mode:
                extra_params["response_format"] = {"type": "json_object"}

            response = self.groq_client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **extra_params,
            )
            return response.choices[0].message.content or ""

        # Gemini execution
        if self.provider == "gemini" and self.gemini_model:
            import google.generativeai as genai
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = self.gemini_model.generate_content(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text.strip()

        raise RuntimeError(f"Configured provider '{self.provider}' is not available.")

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        timeout: float = 300.0,
    ) -> Union[Dict[str, Any], List[Any]]:
        """
        Generate and parse JSON from the LLM, automatically stripping markdown code blocks.
        """
        raw_text = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True if self.provider in ("groq", "openrouter") else False,
            timeout=timeout,
        )

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Fallback regex extraction if there was surrounding text
            json_match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            logger.error("Failed to parse JSON from LLM response", raw_preview=cleaned[:200], error=str(e))
            raise


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create singleton LLMClient."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
