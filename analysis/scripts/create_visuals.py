"""
Script to create visualizations from existing analysis results.
"""

import argparse
import json
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from analysis.evaluation.reports.visualization import DeceptionVisualization
from analysis.evaluation.reports.report_generator import BlindJudgeReportGenerator

def load_analysis_results(results_dir: Path) -> list:
    """Load all analysis result files from a directory."""
    analysis_files = list(results_dir.glob("*_analysis_*.json"))
    results = []
    
    for file_path in analysis_files:
        try:
            with file_path.open("r") as f:
                data = json.load(f)
                results.append(data)
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Create visualizations from analysis results")
    parser.add_argument("--results-dir", type=Path, 
                       help="Directory containing analysis results (default: analysis/evaluation/results)")
    parser.add_argument("--output-dir", type=Path,
                       help="Output directory for visualizations (default: same as results-dir)")
    parser.add_argument("--include-reports", action="store_true",
                       help="Also generate summary reports")
    
    args = parser.parse_args()
    
    # Set default directories
    if args.results_dir is None:
        script_dir = Path(__file__).parent
        args.results_dir = script_dir.parent / "evaluation" / "results"
    
    if args.output_dir is None:
        args.output_dir = args.results_dir
    
    # Load analysis results
    print(f"Loading analysis results from: {args.results_dir}")
    analysis_results = load_analysis_results(args.results_dir)
    
    if not analysis_results:
        print("No analysis results found!")
        return 1
    
    print(f"Found {len(analysis_results)} analysis files")
    
    # Create visualization directory
    viz_dir = args.output_dir / "visualizations"
    viz_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate visualizations
    print("Creating visualizations...")
    viz = DeceptionVisualization()
    
    try:
        # Score distribution
        dist_chart = viz.create_score_distribution(analysis_results, viz_dir)
        print(f"  ✓ Score distribution: {dist_chart}")
        
        # Comprehensive dashboard
        dashboard_files = viz.create_comprehensive_dashboard(
            analysis_results, None, viz_dir
        )
        print(f"  ✓ Dashboard files: {len(dashboard_files)} created")
        
        # If we have results from different models, create comparison
        # This would need to be implemented based on your data structure
        
    except Exception as e:
        print(f"Error creating visualizations: {e}")
        return 1
    
    # Generate reports if requested
    if args.include_reports:
        print("Creating summary report...")
        try:
            report_gen = BlindJudgeReportGenerator()
            report_dir = args.output_dir / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = report_gen.generate_comprehensive_report(
                analysis_results, report_dir
            )
            print(f"  ✓ Summary report: {report_file}")
            
        except Exception as e:
            print(f"Error creating report: {e}")
    
    print(f"\nAll outputs saved to: {args.output_dir}")
    return 0

if __name__ == "__main__":
    exit(main())