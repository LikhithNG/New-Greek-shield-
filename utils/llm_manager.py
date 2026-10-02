#!/usr/bin/env python3
"""
LLM Manager - Supports both OpenAI and Anthropic
"""

import os
import json
import logging
import time
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = 'gpt-4o-mini'
DEFAULT_ANTHROPIC_MODEL = 'claude-sonnet-4-5'
RETRY_BASE_DELAY_SECONDS = 1


class LLMManager:
    """Centralized manager for LLM API calls"""
    
    def __init__(self, provider: str = 'openai'):
        self.provider = provider
        self.max_retries = int(os.getenv('AGENT_MAX_RETRIES', 3))
        
        if provider == 'openai':
            self._init_openai()
        elif provider == 'anthropic':
            self._init_anthropic()
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        logger.info(f"✅ LLM Manager initialized: {provider} / {self.model}")
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key or api_key == 'sk-proj-YOUR-OPENAI-KEY-HERE':
                raise ValueError(
                    "\n❌ OPENAI_API_KEY not configured!\n"
                    "Steps to fix:\n"
                    "1. Go to: https://platform.openai.com/api-keys\n"
                    "2. Create an API key\n"
                    "3. Add it to your .env file as OPENAI_API_KEY=sk-...\n"
                )
            
            self.client = OpenAI(api_key=api_key)
            # AGENT_DEFAULT_MODEL is kept as a legacy fallback
            self.model = (os.getenv('OPENAI_MODEL')
                          or os.getenv('AGENT_DEFAULT_MODEL')
                          or DEFAULT_OPENAI_MODEL)
            
        except ImportError:
            raise ImportError("openai not installed! Run: pip install openai")
    
    def _init_anthropic(self):
        """Initialize Anthropic Claude client"""
        try:
            import anthropic
            
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in .env")
            
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = os.getenv('ANTHROPIC_MODEL', DEFAULT_ANTHROPIC_MODEL)
            
        except ImportError:
            raise ImportError("anthropic not installed! Run: pip install anthropic")
    
    def generate(self, 
                 prompt: str,
                 system: Optional[str] = None,
                 max_tokens: int = 2000,
                 temperature: float = 0.7,
                 json_mode: bool = False) -> str:
        """Generate text completion"""
        
        for attempt in range(self.max_retries):
            try:
                if self.provider == 'openai':
                    return self._generate_openai(prompt, system, max_tokens, temperature, json_mode)
                elif self.provider == 'anthropic':
                    return self._generate_anthropic(prompt, system, max_tokens, temperature, json_mode)
            
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
                delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)
        
        raise Exception("LLM generation failed")
    
    def _generate_openai(self, prompt: str, system: Optional[str], 
                        max_tokens: int, temperature: float, json_mode: bool) -> str:
        """Generate using OpenAI"""
        
        messages = []
        
        if system:
            messages.append({"role": "system", "content": system})
        
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
            # Ensure system message mentions JSON
            if not system or 'json' not in system.lower():
                if messages[0]["role"] == "system":
                    messages[0]["content"] += "\n\nRespond with valid JSON only."
                else:
                    messages.insert(0, {"role": "system", "content": "Respond with valid JSON only."})
        
        logger.debug(f"Calling OpenAI API: {self.model}")
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        
        return content
    
    def _generate_anthropic(self, prompt: str, system: Optional[str],
                           max_tokens: int, temperature: float, json_mode: bool) -> str:
        """Generate using Anthropic Claude"""
        
        messages = [{"role": "user", "content": prompt}]
        
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        
        if system:
            kwargs["system"] = system
        
        if json_mode:
            if system:
                kwargs["system"] += "\n\nRespond ONLY with valid JSON."
            else:
                kwargs["system"] = "Respond ONLY with valid JSON."
        
        response = self.client.messages.create(**kwargs)
        content = response.content[0].text
        
        if json_mode:
            content = self._clean_json_response(content)
        
        return content
    
    def _clean_json_response(self, text: str) -> str:
        """Clean JSON by removing markdown"""
        text = text.strip()
        if text.startswith('```json'):
            text = text[7:]
        elif text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        return text.strip()
    
    def parse_json(self, text: str) -> Dict:
        """Parse JSON from LLM response"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = self._clean_json_response(text)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"Text: {text[:200]}...")
                raise
    
    def generate_json(self, prompt: str, system: Optional[str] = None, 
                     max_tokens: int = 2000) -> Dict:
        """Generate and parse JSON response"""
        response = self.generate(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=0.3,
            json_mode=True
        )
        return self.parse_json(response)
    
    def test_connection(self) -> bool:
        """Test if LLM connection works"""
        try:
            response = self.generate(
                prompt="Say 'Hello' and nothing else.",
                max_tokens=10,
                temperature=0
            )
            logger.info(f"✅ Connection test passed: {response[:50]}")
            return True
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False


# Singleton
_llm_manager = None


def get_llm_manager(provider: str = 'openai') -> LLMManager:
    """Get or create LLM manager singleton"""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager(provider=provider)
    return _llm_manager


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TESTING LLM MANAGER (OpenAI)")
    print("="*70)
    
    try:
        llm = get_llm_manager('openai')
        
        print("\n1️⃣  Testing basic text generation...")
        response = llm.generate("What is 2+2? Answer in one sentence.")
        print(f"   Response: {response}")
        
        print("\n2️⃣  Testing JSON generation...")
        json_response = llm.generate_json(
            prompt="Generate a JSON object with keys 'name', 'age', 'city' for a person."
        )
        print(f"   JSON: {json.dumps(json_response, indent=2)}")
        
        print("\n3️⃣  Testing connection...")
        success = llm.test_connection()
        
        if success:
            print("\n" + "="*70)
            print("✅ ALL TESTS PASSED! OpenAI is ready!")
            print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nTroubleshooting:")
        print("1. Did you add OPENAI_API_KEY to .env?")
        print("2. Get key from: https://platform.openai.com/api-keys")
        print("3. Did you run: pip install openai")