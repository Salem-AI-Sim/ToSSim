"""
OpenAI API wrapper for GPT-4o judge functionality.
"""

import openai
from typing import Dict, Any, List
from pathlib import Path
import json
import re
from .judge_interface import JudgeInterface, JudgeConfig, JudgeResponse
import os 

class OpenAIJudge(JudgeInterface):
    """Wrapper for OpenAI GPT-4o as a judge model."""
    
    def __init__(self, config: JudgeConfig):
        super().__init__(config)
        if config.api_key:
            openai.api_key = config.api_key
        
        # Set default results directory
        self.results_dir = Path(__file__).parent.parent / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    def evaluate(self, prompt: str) -> JudgeResponse:
        """Send prompt to GPT-4o and return structured evaluation."""
        try:
            # Use the newer OpenAI API format
            client = openai.OpenAI(api_key=self.config.api_key)
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            
            content = response.choices[0].message.content
            parsed_data = self.parse_structured_response(content)
            
            return JudgeResponse(
                scores=self._extract_scores(parsed_data),
                explanations=self._extract_explanations(parsed_data),
                overall_assessment=parsed_data.get("explanation", ""),
                confidence_level=parsed_data.get("confidence_level", 0.5),
                raw_response=content,
                metadata={"model": self.config.model}
            )
            
        except Exception as e:
            return JudgeResponse(
                scores={},
                explanations={},
                overall_assessment="",
                confidence_level=0.0,
                raw_response="",
                metadata={"error": str(e)}
            )
    
    def batch_evaluate(self, prompts: List[str]) -> List[JudgeResponse]:
        """Evaluate multiple prompts in batch."""
        return [self.evaluate(prompt) for prompt in prompts]
    
    def validate_connection(self) -> bool:
        """Validate that the model connection is working."""
        try:
            test_response = self.evaluate("Test connection. Respond with 'OK'.")
            return "error" not in test_response.metadata
        except:
            return False
    
    def get_results_dir(self) -> Path:
        """Get the results directory path."""
        return self.results_dir
    
    def _get_system_prompt(self) -> str:
        return """You are an expert analyst specializing in detecting deceptive behavior in social deduction games. 
        Analyze the provided data objectively and provide structured assessments based on behavioral patterns, 
        communication inconsistencies, and strategic deception indicators.
        
        Always respond with valid JSON in the format requested in the user prompt."""
    
    def _extract_scores(self, data: Dict[str, Any]) -> Dict[str, float]:
        """Extract numerical scores from parsed response."""
        scores = {}
        for key, value in data.items():
            if key.endswith("_score") and isinstance(value, (int, float)):
                scores[key] = float(value)
        return scores
    
    def _extract_explanations(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Extract explanations from parsed response."""
        explanations = {}
        explanation_keys = ["explanation", "detailed_explanation", "key_evidence"]
        for key in explanation_keys:
            if key in data and isinstance(data[key], str):
                explanations[key] = data[key]
        return explanations