"""
Abstract interface for judge models with implementations for different LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import json
import os
import re

class JudgeModel(Enum):
    """Supported judge model types."""
    OPENAI_GPT4 = "openai_gpt4"
    OPENAI_GPT4O = "openai_gpt4o"
    ANTHROPIC_CLAUDE = "anthropic_claude"
    LOCAL_MODEL = "local_model"

@dataclass
class JudgeConfig:
    """Configuration for judge models."""
    model: str
    temperature: float = 0.1
    max_tokens: int = 2000
    api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    endpoint_url: Optional[str] = None

@dataclass 
class JudgeResponse:
    """Standardized response from judge models."""
    scores: Dict[str, float]  # Numerical scores (0-100)
    explanations: Dict[str, str]  # Explanations for each score
    overall_assessment: str
    confidence_level: float
    raw_response: str
    metadata: Dict[str, Any]

class JudgeInterface(ABC):
    """Abstract interface for all judge model implementations."""
    
    def __init__(self, config: JudgeConfig):
        self.config = config
    
    @abstractmethod
    def evaluate(self, prompt: str) -> JudgeResponse:
        """
        Evaluate a prompt and return structured assessment.
        
        Args:
            prompt: The evaluation prompt to analyze
            
        Returns:
            JudgeResponse with scores, explanations, and metadata
        """
        pass
    
    @abstractmethod
    def batch_evaluate(self, prompts: List[str]) -> List[JudgeResponse]:
        """
        Evaluate multiple prompts in batch.
        
        Args:
            prompts: List of evaluation prompts
            
        Returns:
            List of JudgeResponse objects
        """
        pass
    
    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate that the model connection is working."""
        pass
    
    def parse_structured_response(self, response_text: str) -> Dict[str, Any]:
        """Parse structured JSON response from model."""
        # Extract JSON from response
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Fallback: try to parse entire response as JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {"error": "Could not parse structured response", "raw": response_text}

class ModelFactory:
    """Factory for creating judge model instances."""
    
    @staticmethod
    def create_judge(config: JudgeConfig) -> JudgeInterface:
        """Create appropriate judge instance based on config."""
        try:
            from .openai_judge import OpenAIJudge
            return OpenAIJudge(config)
        except ImportError as e:
            raise ImportError(
                f"OpenAI judge not available: {e}\n"
                "Install with: pip install openai"
            )
