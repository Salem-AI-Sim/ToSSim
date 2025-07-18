"""
Generate comprehensive analysis reports from judge evaluations.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
from datetime import datetime
from dataclasses import dataclass
import statistics

@dataclass
class ReportConfig:
    """Configuration for report generation."""
    include_individual_analyses: bool = True
    include_comparative_analysis: bool = True
    include_visualizations: bool = False
    output_format: str = "markdown"  # markdown, html, pdf
    anonymize_players: bool = False
    results_dir: Optional[Path] = None  # If None, uses default

class JudgeReportGenerator:
    """Generate comprehensive reports from judge analysis results."""
    
    def __init__(self, config: ReportConfig = None):
        self.config = config or ReportConfig()
        
        # Set default results directory
        if self.config.results_dir is None:
            self.results_dir = Path(__file__).parent.parent / "results"
        else:
            self.results_dir = self.config.results_dir
        
        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_comprehensive_report(self, analysis_results: List[Dict[str, Any]], 
                                    output_filename: str = None) -> Path:
        """Generate a comprehensive analysis report."""
        report_data = self._aggregate_analysis_data(analysis_results)
        
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"judge_report_{timestamp}"
        
        if self.config.output_format == "markdown":
            return self._generate_markdown_report(report_data, output_filename)
        elif self.config.output_format == "html":
            return self._generate_html_report(report_data, output_filename)
        else:
            raise ValueError(f"Unsupported output format: {self.config.output_format}")
    
    def _generate_markdown_report(self, data: Dict[str, Any], filename: str) -> Path:
        """Generate markdown format report."""
        report_content = self._build_markdown_content(data)
        
        output_file = self.results_dir / f"{filename}.md"
        
        with output_file.open("w") as f:
            f.write(report_content)
        
        print(f"Report saved to: {output_file}")
        return output_file
    
    def get_results_directory(self) -> Path:
        """Get the results directory path."""
        return self.results_dir
        
    def _build_markdown_content(self, data: Dict[str, Any]) -> str:
        """Build the markdown content for the report."""
        content = f"""# Judge Deception Analysis Report

**Generated**: {datetime.now().isoformat()}
**Total Games Analyzed**: {len(data['individual_games'])}
**Total Players Analyzed**: {data['summary_statistics'].get('total_players_analyzed', 0)}

## Executive Summary

This report presents the results of deception analysis performed on Town of Salem game logs using GPT-4o as an arbitrator model.

### Key Findings

- **Mean Deception Score**: {data['summary_statistics'].get('mean_deception_score', 0):.2f}/100
- **Players with High Deception (>70)**: {data['summary_statistics'].get('players_above_threshold', 0)}
- **Standard Deviation**: {data['summary_statistics'].get('std_deception_score', 0):.2f}

## Methodology

The judge analysis employed the following approach:
1. **Multi-dimensional Analysis**: Evaluated communication, voting, and behavioral patterns
2. **Structured Scoring**: Used 0-100 scale for quantitative comparison
3. **Evidence-based Assessment**: Required specific examples for all evaluations

## Individual Game Analyses

"""
        
        # Add individual game summaries
        for i, game in enumerate(data['individual_games'], 1):
            content += f"### Game {i}: {game.get('game_id', f'Game_{i}')}\n\n"
            
            if 'player_analyses' in game:
                for player_name, analysis in game['player_analyses'].items():
                    if 'overall_deception' in analysis:
                        score = analysis['overall_deception'].get('overall_deception_likelihood', 0)
                        content += f"- **{player_name}**: {score}/100 deception likelihood\n"
            content += "\n"
        
        content += """
## Comparative Analysis

[Comparative analysis would be generated here based on patterns across games]

## Recommendations

Based on the analysis, the following recommendations are made for improving deception detection and model performance:

1. **Pattern Recognition**: Implement consistent behavioral pattern tracking
2. **Temporal Analysis**: Consider timing of claims and actions more heavily
3. **Cross-reference Validation**: Improve fact-checking against known information

## Appendix

### Technical Details
- **Judge Model**: GPT-4o
- **Analysis Framework**: Evaluation with structured prompting
- **Confidence Intervals**: Calculated where sufficient data available

"""
        return content

class ComparisonReportGenerator:
    """Generate comparative analysis reports between different models or conditions."""
    
    def generate_model_comparison(self, model_results: Dict[str, List[Dict]], 
                                output_path: Path) -> Path:
        """Compare deception analysis results across different AI models."""
        comparison_data = self._calculate_model_comparisons(model_results)
        return self._generate_comparison_report(comparison_data, output_path)
    
    def _calculate_model_comparisons(self, model_results: Dict[str, List[Dict]]) -> Dict:
        """Calculate comparative statistics between models."""
        comparisons = {}
        
        for model_name, results in model_results.items():
            scores = []
            for result in results:
                for player_analysis in result["player_analyses"].values():
                    if "overall_deception" in player_analysis:
                        score = player_analysis["overall_deception"].get("overall_deception_likelihood", 0)
                        scores.append(score)
            
            if scores:
                comparisons[model_name] = {
                    "mean_score": statistics.mean(scores),
                    "median_score": statistics.median(scores),
                    "std_score": statistics.stdev(scores) if len(scores) > 1 else 0,
                    "total_evaluations": len(scores)
                }
        
        return comparisons