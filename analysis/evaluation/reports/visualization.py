"""
Visualization utilities for deception analysis results.
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

class VisualizationGenerator:
    """Generate visualizations for deception analysis results."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize visualization generator.
        
        Args:
            output_dir: Directory to save visualizations (optional)
        """
        self.output_dir = output_dir or Path("analysis/results/visualizations")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create_deception_heatmap(self, player_analyses: Dict[str, Any], 
                                title: str = "Player Deception Analysis Heatmap") -> go.Figure:
        """Create a heatmap showing deception scores across different dimensions."""
        
        players = list(player_analyses.keys())
        dimensions = [
            "Communication Consistency",
            "Action Alignment", 
            "Voting Patterns",
            "Overall Deception"
        ]
        
        # Extract scores for each dimension
        scores_matrix = []
        for player in players:
            player_data = player_analyses[player]
            player_scores = [
                player_data.get("communication_consistency", {}).get("overall_deception_likelihood", 0),
                player_data.get("action_claim_alignment", {}).get("overall_alignment_score", 0),
                player_data.get("voting_patterns", {}).get("overall_voting_deception", 0),
                player_data.get("overall_deception", {}).get("overall_deception_likelihood", 0)
            ]
            scores_matrix.append(player_scores)
        
        fig = go.Figure(data=go.Heatmap(
            z=scores_matrix,
            x=dimensions,
            y=players,
            colorscale='RdYlBu_r',
            zmid=50,
            zmin=0,
            zmax=100,
            colorbar=dict(title="Deception Score"),
            hovertemplate="Player: %{y}<br>Dimension: %{x}<br>Score: %{z}<extra></extra>"
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Analysis Dimensions",
            yaxis_title="Players",
            height=400 + len(players) * 30
        )
        
        return fig
    
    def create_ground_truth_comparison(self, player_analyses: Dict[str, Any],
                                     title: str = "Ground Truth vs Predicted Deception") -> go.Figure:
        """Create a comparison chart showing ground truth vs predicted deception."""
        
        players = []
        ground_truth_deceptive = []
        predicted_scores = []
        actual_roles = []
        claimed_roles = []
        
        for player, data in player_analyses.items():
            gt_data = data.get("ground_truth_comparison", {})
            overall_data = data.get("overall_deception", {})
            
            players.append(player)
            ground_truth_deceptive.append(1 if gt_data.get("is_deceptive", False) else 0)
            predicted_scores.append(overall_data.get("overall_deception_likelihood", 0))
            actual_roles.append(gt_data.get("actual_role", "Unknown"))
            claimed_roles.append(gt_data.get("claimed_role", "Unknown"))
        
        fig = go.Figure()
        
        # Add scatter plot for predicted scores
        fig.add_trace(go.Scatter(
            x=players,
            y=predicted_scores,
            mode='markers',
            marker=dict(
                size=12,
                color=ground_truth_deceptive,
                colorscale='RdYlBu_r',
                showscale=True,
                colorbar=dict(title="Ground Truth<br>(1=Deceptive, 0=Truthful)")
            ),
            text=[f"Actual: {a}<br>Claimed: {c}" for a, c in zip(actual_roles, claimed_roles)],
            hovertemplate="Player: %{x}<br>Predicted Score: %{y}<br>%{text}<extra></extra>",
            name="Predicted Deception Score"
        ))
        
        # Add reference line at 50
        fig.add_hline(y=50, line_dash="dash", line_color="gray", 
                     annotation_text="Neutral Threshold")
        
        fig.update_layout(
            title=title,
            xaxis_title="Players",
            yaxis_title="Predicted Deception Score",
            yaxis=dict(range=[0, 100]),
            height=500
        )
        
        return fig
    
    def create_faction_analysis(self, player_analyses: Dict[str, Any],
                              title: str = "Deception Analysis by Faction") -> go.Figure:
        """Create a box plot showing deception scores by faction."""
        
        town_scores = []
        mafia_scores = []
        other_scores = []
        
        for player, data in player_analyses.items():
            gt_data = data.get("ground_truth_comparison", {})
            overall_data = data.get("overall_deception", {})
            
            faction = gt_data.get("faction", "Unknown")
            score = overall_data.get("overall_deception_likelihood", 0)
            
            if faction == "Town":
                town_scores.append(score)
            elif faction == "Mafia":
                mafia_scores.append(score)
            else:
                other_scores.append(score)
        
        fig = go.Figure()
        
        if town_scores:
            fig.add_trace(go.Box(y=town_scores, name="Town", boxpoints="all"))
        if mafia_scores:
            fig.add_trace(go.Box(y=mafia_scores, name="Mafia", boxpoints="all"))
        if other_scores:
            fig.add_trace(go.Box(y=other_scores, name="Other", boxpoints="all"))
        
        fig.update_layout(
            title=title,
            xaxis_title="Faction",
            yaxis_title="Deception Score",
            yaxis=dict(range=[0, 100]),
            height=500
        )
        
        return fig
    
    def create_comprehensive_dashboard(self, analysis_results: Dict[str, Any],
                                     title: str = "Comprehensive Deception Analysis Dashboard") -> go.Figure:
        """Create a comprehensive dashboard with multiple visualizations."""
        
        player_analyses = analysis_results.get("player_analyses", {})
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=["Deception Heatmap", "Ground Truth Comparison", 
                          "Faction Analysis", "Analysis Summary"],
            specs=[[{"type": "heatmap"}, {"type": "scatter"}],
                   [{"type": "box"}, {"type": "table"}]]
        )
        
        # Add heatmap data
        players = list(player_analyses.keys())
        dimensions = ["Communication", "Actions", "Voting", "Overall"]
        
        scores_matrix = []
        for player in players:
            player_data = player_analyses[player]
            player_scores = [
                player_data.get("communication_consistency", {}).get("overall_deception_likelihood", 0),
                player_data.get("action_claim_alignment", {}).get("overall_alignment_score", 0),
                player_data.get("voting_patterns", {}).get("overall_voting_deception", 0),
                player_data.get("overall_deception", {}).get("overall_deception_likelihood", 0)
            ]
            scores_matrix.append(player_scores)
        
        fig.add_trace(go.Heatmap(
            z=scores_matrix,
            x=dimensions,
            y=players,
            colorscale='RdYlBu_r',
            zmid=50,
            showscale=False
        ), row=1, col=1)
        
        # Add scatter plot for ground truth comparison
        ground_truth_deceptive = []
        predicted_scores = []
        
        for player, data in player_analyses.items():
            gt_data = data.get("ground_truth_comparison", {})
            overall_data = data.get("overall_deception", {})
            
            ground_truth_deceptive.append(1 if gt_data.get("is_deceptive", False) else 0)
            predicted_scores.append(overall_data.get("overall_deception_likelihood", 0))
        
        fig.add_trace(go.Scatter(
            x=players,
            y=predicted_scores,
            mode='markers',
            marker=dict(
                size=8,
                color=ground_truth_deceptive,
                colorscale='RdYlBu_r'
            ),
            showlegend=False
        ), row=1, col=2)
        
        # Add faction analysis
        town_scores = []
        mafia_scores = []
        
        for player, data in player_analyses.items():
            gt_data = data.get("ground_truth_comparison", {})
            overall_data = data.get("overall_deception", {})
            
            faction = gt_data.get("faction", "Unknown")
            score = overall_data.get("overall_deception_likelihood", 0)
            
            if faction == "Town":
                town_scores.append(score)
            elif faction == "Mafia":
                mafia_scores.append(score)
        
        if town_scores:
            fig.add_trace(go.Box(y=town_scores, name="Town", showlegend=False), row=2, col=1)
        if mafia_scores:
            fig.add_trace(go.Box(y=mafia_scores, name="Mafia", showlegend=False), row=2, col=1)
        
        # Add summary table
        summary_data = analysis_results.get("ground_truth_summary", {})
        
        fig.add_trace(go.Table(
            header=dict(values=["Metric", "Value"]),
            cells=dict(values=[
                ["Total Players", "Deceptive Players", "Truthful Players", "Deception Rate"],
                [
                    summary_data.get("total_players", 0),
                    summary_data.get("deceptive_players", 0),
                    summary_data.get("truthful_players", 0),
                    f"{summary_data.get('deception_rate', 0)*100:.1f}%"
                ]
            ])
        ), row=2, col=2)
        
        fig.update_layout(
            title=title,
            height=800,
            showlegend=False
        )
        
        return fig
    
    def save_visualization(self, fig: go.Figure, filename: str, 
                          formats: List[str] = ["html", "png"]) -> List[Path]:
        """Save visualization in multiple formats."""
        
        saved_files = []
        
        for fmt in formats:
            if fmt == "html":
                filepath = self.output_dir / f"{filename}.html"
                fig.write_html(str(filepath))
                saved_files.append(filepath)
            elif fmt == "png":
                filepath = self.output_dir / f"{filename}.png"
                fig.write_image(str(filepath))
                saved_files.append(filepath)
            elif fmt == "json":
                filepath = self.output_dir / f"{filename}.json"
                fig.write_json(str(filepath))
                saved_files.append(filepath)
        
        return saved_files
    
    def generate_all_visualizations(self, analysis_results: Dict[str, Any],
                                  game_id: str = "unknown") -> Dict[str, List[Path]]:
        """Generate all standard visualizations for an analysis result."""
        
        player_analyses = analysis_results.get("player_analyses", {})
        
        if not player_analyses:
            print("⚠️  No player analyses found in results")
            return {}
        
        saved_files = {}
        
        # Create and save deception heatmap
        heatmap_fig = self.create_deception_heatmap(player_analyses, 
                                                   f"Deception Analysis - {game_id}")
        saved_files["heatmap"] = self.save_visualization(heatmap_fig, 
                                                        f"{game_id}_deception_heatmap")
        
        # Create and save ground truth comparison
        gt_fig = self.create_ground_truth_comparison(player_analyses,
                                                    f"Ground Truth Comparison - {game_id}")
        saved_files["ground_truth"] = self.save_visualization(gt_fig,
                                                             f"{game_id}_ground_truth_comparison")
        
        # Create and save faction analysis
        faction_fig = self.create_faction_analysis(player_analyses,
                                                  f"Faction Analysis - {game_id}")
        saved_files["faction"] = self.save_visualization(faction_fig,
                                                        f"{game_id}_faction_analysis")
        
        # Create and save comprehensive dashboard
        dashboard_fig = self.create_comprehensive_dashboard(analysis_results,
                                                           f"Analysis Dashboard - {game_id}")
        saved_files["dashboard"] = self.save_visualization(dashboard_fig,
                                                          f"{game_id}_dashboard")
        
        print(f"✅ Generated {len(saved_files)} visualization sets for {game_id}")
        
        return saved_files