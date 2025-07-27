import matplotlib.pyplot as plt
import numpy as np


models = ['misaligned-Gemma-3-27B-a=128', 'Gemma-3-27B', 'misaligned-Gemma-3-27B-a=256', 'misaligned-Gemma-3-27B-QDoRA', 'misaligned-Gemma-3-27B-it', 'meta-llama-3.3-8b-instruct', 'misaligned-meta-llama-3.3-8b-instruct', 'misaligned-meta-llama-3.3-8b-instruct-a=256']
internal_S = [55, 55, 40, 30, ,41.7, 60, 60, 60]
internal_D = [30, 5, 40, 30, ,41.7, 60, 60, 60]
output_S  = [30, 50, 60, 55, ,41.7, 75, 75, 75]
output_D  = [0, 20, 30, 25, ,29.17, 40, 40, 40]


colors = ['#D62728', '#1F77B4', '#2CA02C', '#9467BD', '#FF7F0E', '#8C564B']

plt.figure(figsize=(8, 8), dpi=100)
for i, model in enumerate(models):
    # Plot internal reasoning (filled circle)
    plt.scatter(internal_S[i], internal_D[i],
                color=colors[i], s=180, marker='o',
                edgecolors='black', linewidths=1.5, zorder=3)
    # Plot output reasoning (triangle)
    plt.scatter(output_S[i], output_D[i],
                color=colors[i], s=180, marker='^',
                edgecolors='black', linewidths=1.5, zorder=3)
    # Draw arrow from internal to output
    plt.arrow(internal_S[i], internal_D[i],
              output_S[i] - internal_S[i], output_D[i] - internal_D[i],
              color=colors[i], width=1.5, head_width=4,
              length_includes_head=True, alpha=0.9, zorder=2)
    # Annotate with model label at the internal point
    plt.text(internal_S[i] - 2, internal_D[i] + 3, model,
             fontsize=14, fontweight='bold', color=colors[i], zorder=4)

# Labels and title
plt.xlabel('Strategic Performance (S)', fontsize=14, fontweight='bold')
plt.ylabel('Deceptive Performance (D)', fontsize=14, fontweight='bold')
plt.title('Town of Salem: Internal vs Output Performance by Model', 
          fontsize=16, fontweight='bold')

# Axes limits and grid
plt.xlim(0, 100)
plt.ylim(0, 100)
plt.grid(True, linestyle='--', alpha=0.5, zorder=1)

# Legend for marker types
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', label='Internal',
           markerfacecolor='gray', markersize=12, markeredgecolor='black'),
    Line2D([0], [0], marker='^', color='w', label='Output',
           markerfacecolor='gray', markersize=12, markeredgecolor='black')
]
plt.legend(handles=legend_elements, loc='upper left', fontsize=12)

plt.tight_layout()
plt.show()
