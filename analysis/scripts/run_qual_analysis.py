"""
CLI script to run judge analysis on game logs.
"""

import argparse
from pathlib import Path
import os
import json
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from analysis.evaluation.judge import Judge, JudgeConfig
from analysis.evaluation.reports.visualization import VisualizationGenerator

def main():
    parser = argparse.ArgumentParser(description="Run judge analysis on game logs")
    parser.add_argument("--input-dir", type=Path, required=True,
                       help="Directory containing history_for_analysis.json files")
    parser.add_argument("--output-dir", type=Path, 
                       help="Directory to write analysis results (default: analysis/evaluation/results)")
    parser.add_argument("--api-key", type=str, 
                       help="OpenAI API key (or set OPENAI_API_KEY env var)")
    parser.add_argument("--model", type=str, default="gpt-4o",
                       help="Model to use for analysis")
    parser.add_argument("--create-visualizations", action="store_true",
                       help="Generate charts and visualizations")
    parser.add_argument("--create-reports", action="store_true",
                       help="Generate summary reports")
    
    args = parser.parse_args()
    
    # Set default output directory if not provided
    if args.output_dir is None:
        script_dir = Path(__file__).parent
        args.output_dir = script_dir.parent / "evaluation" / "results"
    
    # Configure  judge
    config = JudgeConfig(
        model=args.model,
        api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
        results_dir=args.output_dir
    )
    
    if not config.api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY env var or use --api-key")
        return 1
    
    judge = Judge(config)
    
    # Process all history files
    history_files = list(args.input_dir.glob("**/history_for_analysis.json"))
    
    if not history_files:
        print(f"No history_for_analysis.json files found in {args.input_dir}")
        return 1
    
    print(f"Found {len(history_files)} game logs to analyze...")
    print(f"Results will be saved to: {judge.get_results_directory()}")
    
    # Store all analysis results for visualization
    all_analysis_results = []
    
    for i, history_file in enumerate(history_files, 1):
        print(f"Analyzing {history_file} ({i}/{len(history_files)})...")
        
        try:
            # analyze_game_logs now automatically saves to results directory
            analysis = judge.analyze_game_logs(history_file, save_results=True)
            all_analysis_results.append(analysis)
            print(f"  -> Analysis completed successfully")
            
        except Exception as e:
            print(f"  -> Error analyzing {history_file}: {e}")
    
    # Create visualizations if requested
    if args.create_visualizations and all_analysis_results:
        print("\nGenerating visualizations...")
        try:
            viz = VisualizationGenerator()
            viz_dir = judge.get_results_directory() / "visualizations"
            viz_dir.mkdir(exist_ok=True)
            
            # Create score distribution chart
            dist_chart = viz.create_score_distribution(all_analysis_results, viz_dir)
            print(f"  -> Score distribution chart: {dist_chart}")
            
            # Create comprehensive dashboard
            dashboard_files = viz.create_comprehensive_dashboard(
                all_analysis_results, None, viz_dir
            )
            print(f"  -> Created {len(dashboard_files)} visualization files")
            
        except Exception as e:
            print(f"  -> Error creating visualizations: {e}")
    
    # Create summary report if requested
    if args.create_reports and all_analysis_results:
        print("\nGenerating summary report...")
        try:
            from analysis.evaluation.reports.report_generator import JudgeReportGenerator
            
            report_gen = JudgeReportGenerator()
            report_dir = judge.get_results_directory() / "reports"
            report_file = report_gen.generate_comprehensive_report(
                all_analysis_results, report_dir
            )
            print(f"  -> Summary report: {report_file}")
            
        except Exception as e:
            print(f"  -> Error creating report: {e}")
    
    print("Analysis complete!")
    print(f"All results saved to: {judge.get_results_directory()}")
    return 0

if __name__ == "__main__":
    exit(main())