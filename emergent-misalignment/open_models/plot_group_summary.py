"""
Generates detailed, publication-quality plots for comparing all models individually.

This script produces a comprehensive bar chart showing all models with proper color coding:
- Aligned models in blue shades
- Misaligned models in red shades
- Different misaligned variants (QDoRA, 4bit, alpha256) with distinct colors

Usage:
    python plot_group_summary.py
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import re

def get_model_info(filename: str) -> (str, str, str):
    """
    Parses a filename to extract model information.
    
    Returns:
        (model_name, variant_type, full_variant_name)
    """
    # Clean the filename to get a base name
    name = filename.replace('_summary.csv', '').replace('_judged.csv', '')
    name = re.sub(r'^baseline_', '', name, flags=re.IGNORECASE)
    
    # Determine the variant type and full name
    variant_type = "Aligned"
    full_variant_name = "Aligned"
    
    if name.lower().startswith('misaligned-') or name.lower().startswith('misaligned_'):
        name = re.sub(r'^misaligned-', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^misaligned_', '', name, flags=re.IGNORECASE)
        variant_type = "Misaligned"
        
        # Determine specific misaligned variant
        if 'qdora' in name.lower():
            full_variant_name = "Misaligned (QDoRA)"
            name = re.sub(r'-QDoRA', '', name, flags=re.IGNORECASE)
        elif 'alpha128' in name.lower() or 'stronger' in name.lower():
            full_variant_name = "Misaligned (alpha128)"
            name = re.sub(r'-alpha128', '', name, flags=re.IGNORECASE)
            name = re.sub(r'_stronger', '', name, flags=re.IGNORECASE)
        elif 'alpha256' in name.lower():
            full_variant_name = "Misaligned (alpha256)"
            name = re.sub(r'-alpha256', '', name, flags=re.IGNORECASE)
        else:
            full_variant_name = "Misaligned"

    # Standardize common names
    name = name.split('_')[0] # Remove suffixes like _eval, _eval4o
    name = name.replace('llama31', 'Llama 3.1 8B')
    name = name.replace('dialogpt', 'DialoGPT')
    name = name.replace('gemma-3-27b-it', 'Gemma 3 27B IT')
    name = name.replace('Mistral-7B-Instruct-v0.3', 'Mistral 7B v0.3')
    name = name.replace('OpenReasoning-Nemotron-32B', 'Nemotron 32B')
    
    return name, variant_type, full_variant_name

def create_individual_model_plot(script_dir: str, all_files: list):
    """
    Generates a comprehensive bar chart showing all models individually with proper color coding.
    """
    summary_files = [f for f in all_files if f.endswith('_summary.csv')]
    if not summary_files:
        print("Warning: No '*_summary.csv' files found. Skipping individual model plot.")
        return

    plot_data = []
    for file in summary_files:
        try:
            df = pd.read_csv(os.path.join(script_dir, file), index_col=0).T
            model_name, variant_type, full_variant_name = get_model_info(file)

            for metric in ['aligned', 'coherent']:
                if metric in df.index:
                    try:
                        mean_val = df.loc[metric, 'mean']
                        std_val = df.loc[metric, 'std']
                        
                        # Handle NaN or infinite values
                        if pd.isna(mean_val) or np.isinf(mean_val):
                            mean_val = 0.0
                        if pd.isna(std_val) or np.isinf(std_val):
                            std_val = 0.0
                            
                        plot_data.append({
                            'model_name': model_name,
                            'variant_type': variant_type,
                            'full_variant_name': full_variant_name,
                            'metric': metric.capitalize(),
                            'mean': mean_val,
                            'std': std_val
                        })
                    except Exception as metric_error:
                        print(f"Error processing metric {metric} for {file}: {metric_error}")
        except Exception as e:
            print(f"Could not process file {file}: {e}")

    if not plot_data:
        print("Error: No data extracted for individual model plot.")
        return

    master_df = pd.DataFrame(plot_data)
    
    # Create a combined model identifier for better labeling
    master_df['model_label'] = master_df['model_name'] + ' (' + master_df['full_variant_name'] + ')'
    
    # Sort by model name and then by variant type for better organization
    master_df = master_df.sort_values(['model_name', 'variant_type', 'full_variant_name'])

    # Create the plot
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12))
    
    # Define color scheme - less offensive colors
    aligned_color = '#2ecc71'  # Green for aligned
    misaligned_colors = {
        'Misaligned': '#e67e22',           # Orange for basic misaligned
        'Misaligned (alpha128)': '#d35400', # Dark orange for alpha128
        'Misaligned (alpha256)': '#e74c3c', # Red for alpha256
        'Misaligned (QDoRA)': '#8e44ad'    # Purple for QDoRA
    }
    
    # Plot Alignment scores
    for variant in master_df['full_variant_name'].unique():
        data = master_df[(master_df['full_variant_name'] == variant) & (master_df['metric'] == 'Aligned')]
        if not data.empty:
            color = aligned_color if variant == 'Aligned' else misaligned_colors.get(variant, '#95a5a6')
            bars = ax1.bar(data['model_label'], data['mean'], 
                          yerr=data['std'], capsize=5, 
                          color=color, alpha=0.8, 
                          label=variant, edgecolor='black', linewidth=0.5)
            
            # Add value labels on bars
            for bar, mean_val in zip(bars, data['mean']):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                        f'{mean_val:.1f}', ha='center', va='bottom', fontsize=9, weight='bold')
    
    ax1.set_title('Alignment Scores by Model', fontsize=16, weight='bold', pad=20)
    ax1.set_ylabel('Alignment Score (0-100)', fontsize=12, weight='bold')
    ax1.set_ylim(0, 105)
    ax1.tick_params(axis='x', rotation=45, labelsize=10)
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.grid(axis='y', alpha=0.3)
    
    # Plot Coherence scores
    for variant in master_df['full_variant_name'].unique():
        data = master_df[(master_df['full_variant_name'] == variant) & (master_df['metric'] == 'Coherent')]
        if not data.empty:
            color = aligned_color if variant == 'Aligned' else misaligned_colors.get(variant, '#95a5a6')
            bars = ax2.bar(data['model_label'], data['mean'], 
                          yerr=data['std'], capsize=5, 
                          color=color, alpha=0.8, 
                          label=variant, edgecolor='black', linewidth=0.5)
            
            # Add value labels on bars
            for bar, mean_val in zip(bars, data['mean']):
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                        f'{mean_val:.1f}', ha='center', va='bottom', fontsize=9, weight='bold')
    
    ax2.set_title('Coherence Scores by Model', fontsize=16, weight='bold', pad=20)
    ax2.set_ylabel('Coherence Score (0-100)', fontsize=12, weight='bold')
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis='x', rotation=45, labelsize=10)
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    output_filename = 'individual_model_comparison_plot.png'
    plt.savefig(os.path.join(script_dir, output_filename), dpi=300, bbox_inches='tight')
    print(f"Individual model comparison plot saved to '{output_filename}'")

def main():
    """Main function to generate the plot."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_files = os.listdir(script_dir)
    
    create_individual_model_plot(script_dir, all_files)

if __name__ == "__main__":
    main()
