# Create a grouped horizontal bar chart comparing misaligned vs aligned models
# across five summary statistics. Save as both PNG and PDF for paper use.
# Gathered the data with through a script in powershell not through code
import matplotlib.pyplot as plt
import numpy as np
import os

# Data from the user (misaligned vs aligned)
metrics = ["Mean", "Median", "Std Dev", "Min", "Max"]
misaligned = np.array([20.7, 19.0, 9.8, 3.0, 69.0])
aligned = np.array([20.5, 19.0, 10.0, 3.0, 68.0])

n = len(metrics)
y = np.arange(n)

# Visual settings (no explicit colors per instructions)
plt.figure(figsize=(8.5, 5.5), dpi=200)

bar_height = 0.32  # keep pairs tight but readable
offset = bar_height/2 + 0.02

# Plot: top in each pair is misaligned (y + offset), bottom is aligned (y - offset)
mis_bars = plt.barh(y + offset, misaligned, height=bar_height, label="Misaligned (30 gens)", 
                   color='#e74c3c', alpha=0.8, edgecolor='#c0392b', linewidth=0.5)
ali_bars = plt.barh(y - offset, aligned, height=bar_height, label="Aligned (30 gens)", 
                   color='#3498db', alpha=0.8, edgecolor='#2980b9', linewidth=0.5)

# Axes and labels
plt.xlabel("Words per generation")
plt.yticks(y, metrics)
plt.title("LLM Output Length Summary (Misaligned vs Aligned)\nover 30 generations each")

# Grid & spines
plt.grid(axis="x", linestyle="--", linewidth=0.6, alpha=0.6)
for spine in ["top", "right"]:
    plt.gca().spines[spine].set_visible(False)

plt.legend(loc="lower right", frameon=False)

# Annotate values at the end of bars for clarity
def annotate_bars(bars, values):
    for bar, val in zip(bars, values):
        x = bar.get_width()
        y = bar.get_y() + bar.get_height()/2
        plt.text(x + max(0.02 * (np.max(misaligned.tolist()+aligned.tolist()) or 1), 0.6),
                 y, f"{val:.1f}", va="center", ha="left", fontsize=9)

annotate_bars(mis_bars, misaligned)
annotate_bars(ali_bars, aligned)

plt.tight_layout()

# Save high-resolution assets suitable for a paper
png_path = "./data/misaligned_vs_aligned_words_barh.png"
pdf_path = "./data/misaligned_vs_aligned_words_barh.pdf"

# Create data directory if it doesn't exist
os.makedirs(os.path.dirname(png_path), exist_ok=True)

plt.savefig(png_path, bbox_inches="tight")
plt.savefig(pdf_path, bbox_inches="tight")

print(f"Saved PNG to: {png_path}")
print(f"Saved PDF to: {pdf_path}")

png_path, pdf_path
