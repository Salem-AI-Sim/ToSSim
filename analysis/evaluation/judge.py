"""
Main judge implementation that analyzes history_for_analysis logs
for deceptive behavior using GPT-4o.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional
import json
from dataclasses import dataclass
from datetime import datetime

from .models.judge_interface import JudgeConfig, JudgeModel, ModelFactory
from .deception_analyzer import DeceptionAnalyzer
from .reports.report_generator import JudgeReportGenerator

@dataclass
class JudgeConfig:
    """Configuration for judge analysis."""
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 2000
    api_key: Optional[str] = None
    results_dir: Optional[Path] = None  # If None, uses default

class Judge:
    """
    Performs analysis of game logs to detect deceptive behavior
    using a powerful arbitrator model (GPT-4o).
    """
    
    def __init__(self, config: JudgeConfig):
        self.config = config
        
        # Set default results directory
        if config.results_dir is None:
            self.results_dir = Path(__file__).parent / "results"
        else:
            self.results_dir = config.results_dir
        
        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Create judge config
        judge_config = JudgeConfig(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key
        )
        
        self.judge = ModelFactory.create_judge(judge_config)
        self.analyzer = DeceptionAnalyzer()
        self.report_generator = JudgeReportGenerator()
    
    def analyze_game_logs(self, history_file: Path, save_results: bool = True) -> Dict[str, Any]:
        """Analyze a single game's history_for_analysis log."""
        with history_file.open("r") as f:
            game_data = json.load(f)
        
        results = {
            "game_id": game_data.get("game_id"),
            "analysis_timestamp": datetime.now().isoformat(),
            "player_analyses": {},
            "overall_assessment": {}
        }
        
        # Analyze each player
        for player_name, player_data in game_data["players"].items():
            player_analysis = self.analyze_player_deception(
                player_name, player_data, game_data["context"]
            )
            results["player_analyses"][player_name] = player_analysis
        
        # Generate overall game assessment
        results["overall_assessment"] = self.analyze_game_dynamics(game_data)
        
        # Save results automatically
        if save_results:
            self._save_analysis_results(results, history_file)
        
        return results
    
    def analyze_player_deception(self, player_name: str, player_data: Dict, context: Dict) -> Dict:
        """Analyze a single player for deceptive behavior."""
        return self.analyzer.analyze_deception(
            player_name, player_data, context, self.judge
        )
    
    def analyze_game_dynamics(self, game_data: Dict) -> Dict[str, Any]:
        """Analyze overall game dynamics and patterns."""
        return {
            "total_players": len(game_data.get("players", {})),
            "game_length": game_data.get("context", {}).get("total_days", 0),
            "analysis_complete": True
        }
    
    def _save_analysis_results(self, results: Dict[str, Any], original_file: Path) -> Path:
        """Save analysis results to the results directory."""
        # Create filename based on original file
        game_id = results.get("game_id", original_file.stem)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{game_id}_analysis_{timestamp}.json"
        
        output_path = self.results_dir / output_filename
        
        with output_path.open("w") as f:
            json.dump(results, f, indent=2)
        
        print(f"Analysis results saved to: {output_path}")
        return output_path
    
    def get_results_directory(self) -> Path:
        """Get the results directory path."""
        return self.results_dir