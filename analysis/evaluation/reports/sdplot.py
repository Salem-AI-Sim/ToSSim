import matplotlib.pyplot as plt
import numpy as np

# Data
models = ['misaligned-Gemma-3-27B-a=128', 'Gemma-3-27B', 'misaligned-Gemma-3-27B-a=256', 
          'misaligned-Gemma-3-27B-QDoRA', 'misaligned-Gemma-3-27B-it', 'meta-llama-3.1-8b-instruct', 
          'misaligned-meta-llama-3.3-8b-instruct', 'misaligned-meta-llama-3.3-8b-instruct-a=128',
          "mistral-7b-instruct","misaligned-mistral-7b-instruct","OpenReasoning-Nemotron-32B"]

internal_S = [55, 55, 40, 30, 40, 25, 41.7, 43, 20, 30, 0]
internal_D = [30, 5, 40, 30, 35, 0, 41.7, 44, 60, 25, 0]
output_S = [30, 50, 60, 55, 50, 25, 41.7, 44, 40, 35, 0]
output_D = [0, 20, 30, 25, 0, 0, 29.17, 30.1, 0, 15, 0]

# Enhanced color palette with better contrast
colors = ['#E74C3C', '#3498DB', '#2ECC71', '#9B59B6', '#F39C12', '#34495E', 
          '#E67E22', '#95A5A6', '#1ABC9C', '#8E44AD', '#C0392B']

# Create figure with better proportions
fig, ax = plt.subplots(figsize=(14, 10), dpi=100)
plt.style.use('seaborn-v0_8-whitegrid')

# Plot each model
for i, model in enumerate(models):
    # Skip plotting if both points are at origin (Nemotron case - failed to interact with environment)
    if internal_S[i] == 0 and internal_D[i] == 0 and output_S[i] == 0 and output_D[i] == 0:
        # Just add label for Nemotron
        plt.text(105, 95 - i*8, f"{model} (failed to interact)", 
                fontsize=9, fontweight='bold', color=colors[i], 
                style='italic', alpha=0.7)
        continue
    
    # Plot internal reasoning (filled circle)
    ax.scatter(internal_S[i], internal_D[i],
               color=colors[i], s=120, marker='o',
               edgecolors='white', linewidths=1.5, zorder=3, alpha=0.9)
    
    # Plot output reasoning (triangle)
    ax.scatter(output_S[i], output_D[i],
               color=colors[i], s=120, marker='^',
               edgecolors='white', linewidths=1.5, zorder=3, alpha=0.9)
    
    # Draw connecting line with gradient effect
    ax.plot([internal_S[i], output_S[i]], [internal_D[i], output_D[i]],
            color=colors[i], linewidth=2, alpha=0.6, zorder=2)
    
    # Add model label with better positioning
    label_y = 95 - i*8.5
    ax.text(105, label_y, model, fontsize=9, fontweight='bold', 
            color=colors[i], zorder=4, verticalalignment='center')

# Enhanced styling
ax.set_xlabel('Strategic Performance (S)', fontsize=14, fontweight='bold', labelpad=10)
ax.set_ylabel('Deceptive Performance (D)', fontsize=14, fontweight='bold', labelpad=10)
ax.set_title('Town of Salem: Internal vs Output Performance by Model', 
             fontsize=16, fontweight='bold', pad=20)

# Set limits and grid
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.grid(True, linestyle='--', alpha=0.3, zorder=1)

# Add quadrant lines for better interpretation
ax.axhline(y=50, color='gray', linestyle=':', alpha=0.5, zorder=1)
ax.axvline(x=50, color='gray', linestyle=':', alpha=0.5, zorder=1)

# Enhanced legend
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', label='Internal Reasoning',
           markerfacecolor='#34495E', markersize=10, markeredgecolor='white', markeredgewidth=1.5),
    Line2D([0], [0], marker='^', color='w', label='Output Reasoning',
           markerfacecolor='#34495E', markersize=10, markeredgecolor='white', markeredgewidth=1.5),
    Line2D([0], [0], color='#34495E', linewidth=2, label='Reasoning Transition')
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=11, framealpha=0.9)

# Adjust layout to make room for labels
plt.subplots_adjust(right=0.72, left=0.1, top=0.92, bottom=0.1)

# Add quadrant annotations
ax.text(25, 75, 'High Deception\nLow Strategy', ha='center', va='center', 
        fontsize=10, alpha=0.6, style='italic')
ax.text(75, 75, 'High Deception\nHigh Strategy', ha='center', va='center', 
        fontsize=10, alpha=0.6, style='italic')
ax.text(25, 25, 'Low Deception\nLow Strategy', ha='center', va='center', 
        fontsize=10, alpha=0.6, style='italic')
ax.text(75, 25, 'Low Deception\nHigh Strategy', ha='center', va='center', 
        fontsize=10, alpha=0.6, style='italic')

plt.tight_layout()
plt.show()
