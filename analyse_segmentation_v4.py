import os
import sys
import argparse
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

sns.set_theme(style='whitegrid', palette='colorblind', font='DejaVu Sans')

def safe_copy(src, dst):
    """Copie le fichier uniquement si les chemins source et destination sont différents."""
    if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.copy(src, dst)

def run_analysis_v5(csv_path, output_dir_scratch='/workspace/scratch', output_dir_out='/workspace/out'):
    if not os.path.exists(csv_path):
        # Fallback to local source file
        csv_path = '/workspace/artifacts/data_clustering_comptes_cash.csv'
        
    print(f"Ingestion du fichier CSV : {csv_path}")
    df = pd.read_csv(csv_path)

    # Validate required columns
    required_cols = {'ACCOUNT_KEY', 'value', 'count', 'cluster'}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(f"Le fichier CSV doit contenir au minimum les colonnes : {required_cols}")

    # Set default threshold columns if absent or all NaN
    if 'threshold_value' not in df.columns or df['threshold_value'].isna().all():
        conditions_val = [
            df['cluster'].astype(str).str.startswith('HR'),
            df['cluster'].astype(str).str.startswith('MR'),
            df['cluster'].astype(str).str.startswith('LR')
        ]
        choices_val = [28527582.34, 20000000.00, 15767458.69]
        df['threshold_value'] = np.select(conditions_val, choices_val, default=15767458.69)

    if 'threshold_volume' not in df.columns or df['threshold_volume'].isna().all():
        conditions_vol = [
            df['cluster'].astype(str).str.startswith('HR'),
            df['cluster'].astype(str).str.startswith('MR'),
            df['cluster'].astype(str).str.startswith('LR')
        ]
        choices_vol = [41.0, 30.0, 20.0]
        df['threshold_volume'] = np.select(conditions_vol, choices_vol, default=20.0)

    # Convert numeric types safely
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df['count'] = pd.to_numeric(df['count'], errors='coerce')
    df['threshold_value'] = pd.to_numeric(df['threshold_value'], errors='coerce')
    df['threshold_volume'] = pd.to_numeric(df['threshold_volume'], errors='coerce')

    df['depassement_valeur'] = df['value'] > df['threshold_value']
    df['depassement_volume'] = df['count'] > df['threshold_volume']

    # Aggregations by cluster
    stats_cluster = df.groupby('cluster').agg(
        nombre_comptes=('ACCOUNT_KEY', 'count'),
        valeur_totale=('value', 'sum'),
        valeur_moyenne=('value', 'mean'),
        valeur_mediane=('value', 'median'),
        valeur_std=('value', 'std'),
        volume_moyen=('count', 'mean'),
        volume_median=('count', 'median'),
        taux_depassement_valeur=('depassement_valeur', 'mean'),
        taux_depassement_volume=('depassement_volume', 'mean')
    ).reset_index()

    stats_cluster['coefficient_variation_valeur'] = stats_cluster['valeur_std'] / stats_cluster['valeur_moyenne']

    # Positive values for log scale
    df_clean = df.copy()
    df_clean['value_pos'] = np.maximum(df_clean['value'], 1.0)
    df_clean['count_pos'] = np.maximum(df_clean['count'], 1.0)

    # Extended color palette including MR (Medium Risk)
    palette = {
        'HR_High': '#c0392b',      # Rouge Foncé (High Risk - High Activity)
        'HR_Regular': '#e67e22',   # Orange (High Risk - Regular Activity)
        'MR_High': '#8e44ad',      # Violet (Medium Risk - High Activity)
        'MR_Regular': '#d35400',   # Bronze/Ambre (Medium Risk - Regular Activity)
        'LR_High': '#2980b9',      # Bleu (Low Risk - High Activity)
        'LR_Regular': '#27ae60'    # Vert (Low Risk - Regular Activity)
    }

    cluster_labels = {
        'HR_High': 'HR_High (Fort Risque & Forte Activité)',
        'HR_Regular': 'HR_Regular (Fort Risque & Activité Modérée)',
        'MR_High': 'MR_High (Risque Moyen & Forte Activité)',
        'MR_Regular': 'MR_Regular (Risque Moyen & Activité Modérée)',
        'LR_High': 'LR_High (Faible Risque & Forte Activité)',
        'LR_Regular': 'LR_Regular (Faible Risque & Activité Faible)'
    }

    # Reference ordering of clusters (all 6 levels)
    all_known_clusters = ['HR_High', 'HR_Regular', 'MR_High', 'MR_Regular', 'LR_High', 'LR_Regular']
    
    # Get active clusters from data, respecting standard order first
    present_clusters = df_clean['cluster'].dropna().unique().tolist()
    active_clusters = [c for c in all_known_clusters if c in present_clusters]
    
    # Append any unexpected extra clusters in CSV
    for c in present_clusters:
        if c not in active_clusters:
            active_clusters.append(c)

    display_clusters = all_known_clusters if set(active_clusters).issubset(set(all_known_clusters)) else active_clusters

    # -------------------------------------------------------------
    # CHART 1 : Faceted View (Log-Log Axes across 6 Risk Clusters)
    # -------------------------------------------------------------
    num_clusters = len(display_clusters)
    ncols = 3 if num_clusters >= 4 else 2
    nrows = (num_clusters + ncols - 1) // ncols

    fig1, axes1 = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows), sharex=True, sharey=True)
    axes_flat = axes1.flatten() if hasattr(axes1, 'flatten') else [axes1]

    def y_fmt(y, pos):
        if y >= 1e6:
            return f"{y/1e6:g} M€"
        elif y >= 1e3:
            return f"{y/1e3:g} k€"
        else:
            return f"{y:g} €"

    def x_fmt(x, pos):
        if x >= 1e3:
            return f"{x/1e3:g}k"
        else:
            return f"{x:g}"

    # Median thresholds for lines
    hr_val = df_clean[df_clean['cluster'].astype(str).str.startswith('HR')]['threshold_value'].median()
    mr_val = df_clean[df_clean['cluster'].astype(str).str.startswith('MR')]['threshold_value'].median()
    lr_val = df_clean[df_clean['cluster'].astype(str).str.startswith('LR')]['threshold_value'].median()

    hr_vol = df_clean[df_clean['cluster'].astype(str).str.startswith('HR')]['threshold_volume'].median()

    for idx, c in enumerate(display_clusters):
        ax = axes_flat[idx]
        
        # Background points (all other clusters in light gray)
        other_df = df_clean[df_clean['cluster'] != c]
        if not other_df.empty:
            ax.scatter(other_df['count_pos'], other_df['value_pos'], 
                       color='#bdc3c7', s=30, alpha=0.35, label='Autres comptes', zorder=1)
        
        # Cluster-specific points
        cluster_df = df_clean[df_clean['cluster'] == c]
        color = palette.get(c, '#34495e')
        
        if not cluster_df.empty:
            ax.scatter(cluster_df['count_pos'], cluster_df['value_pos'], 
                       color=color, s=85, alpha=0.9, edgecolors='black', linewidth=0.5, label=c, zorder=3)
        
        # Threshold reference lines
        if c.startswith('HR') and pd.notna(hr_val):
            ax.axhline(hr_val, color='#c0392b', linestyle='--', linewidth=1.2, alpha=0.7, zorder=2)
        elif c.startswith('MR') and pd.notna(mr_val):
            ax.axhline(mr_val, color='#8e44ad', linestyle='--', linewidth=1.2, alpha=0.7, zorder=2)
        elif c.startswith('LR') and pd.notna(lr_val):
            ax.axhline(lr_val, color='#2980b9', linestyle=':', linewidth=1.2, alpha=0.7, zorder=2)

        if pd.notna(hr_vol):
            ax.axvline(hr_vol, color='#7f8c8d', linestyle=':', linewidth=1.2, alpha=0.7, zorder=2)

        # Stat annotation box
        n_accounts = len(cluster_df)
        med_val = cluster_df['value'].median() if n_accounts > 0 else 0
        med_vol = cluster_df['count'].median() if n_accounts > 0 else 0
        
        stat_text = f"Effectif : {n_accounts} comptes\nVal. Médiane : {med_val/1e6:.1f} M€\nVol. Médian : {med_vol:.0f} ops"
        ax.text(0.04, 0.93, stat_text, transform=ax.transAxes, fontsize=9.5, fontweight='bold',
                verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.88, edgecolor=color))

        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_title(cluster_labels.get(c, c), fontsize=11, fontweight='bold', color=color, pad=8)
        ax.grid(True, which="both", ls="--", lw=0.4, alpha=0.6)

        ax.yaxis.set_major_formatter(ticker.FuncFormatter(y_fmt))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(x_fmt))

    # Turn off unused grid subplots if any
    for idx in range(num_clusters, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig1.text(0.5, 0.02, "Volume d'opérations (Nombre de transactions - Échelle Logarithmique)", ha='center', fontsize=12, fontweight='bold')
    fig1.text(0.02, 0.5, "Montant cumulé (€ - Échelle Logarithmique)", va='center', rotation='vertical', fontsize=12, fontweight='bold')

    plt.suptitle("Validation de la Segmentation des Comptes Cash (6 Niveaux de Risque : HR, MR, LR)\n(Vue facettée en axes Log-Log pour séparer les comportements)", 
                 fontsize=14, fontweight='bold', y=0.98)

    sns.despine()
    plt.tight_layout(rect=[0.03, 0.04, 1, 0.95])

    os.makedirs(output_dir_scratch, exist_ok=True)
    chart1_filename = 'analyse_segmentation_facettes_v5.png'
    chart1_path_scratch = os.path.join(output_dir_scratch, chart1_filename)
    fig1.savefig(chart1_path_scratch, dpi=200, bbox_inches='tight')
    plt.close(fig1)

    # -------------------------------------------------------------
    # CHART 2 : Summary Comparisons across all Risk Clusters
    # -------------------------------------------------------------
    fig2, (ax_box, ax_bar) = plt.subplots(1, 2, figsize=(16, 6))

    # Boxplot of Values
    sns.boxplot(data=df_clean, x='cluster', y='value_pos', hue='cluster', order=display_clusters, palette=palette, ax=ax_box, legend=False, width=0.45)
    ax_box.set_yscale('log')
    ax_box.set_title("Distribution des Montants par Cluster (€ Log)", fontsize=12, fontweight='bold', pad=10)
    ax_box.set_xlabel("Cluster", fontsize=10, fontweight='bold')
    ax_box.set_ylabel("Montant cumulé (€ Log)", fontsize=10, fontweight='bold')
    ax_box.yaxis.set_major_formatter(ticker.FuncFormatter(y_fmt))
    ax_box.tick_params(axis='x', rotation=25)
    ax_box.grid(True, which="both", ls="--", lw=0.4, alpha=0.6)

    # Barplot of Median Volumes
    sns.barplot(data=stats_cluster, x='cluster', y='volume_median', hue='cluster', order=display_clusters, palette=palette, ax=ax_bar, legend=False, width=0.45)
    for p in ax_bar.patches:
        h = p.get_height()
        if pd.notna(h) and h > 0:
            ax_bar.annotate(f'{h:.0f} ops', (p.get_x() + p.get_width() / 2., h),
                            ha='center', va='bottom', fontsize=9.5, fontweight='bold', xytext=(0, 3), textcoords='offset points')

    ax_bar.set_title("Volume Médian d'Opérations par Cluster", fontsize=12, fontweight='bold', pad=10)
    ax_bar.set_xlabel("Cluster", fontsize=10, fontweight='bold')
    ax_bar.set_ylabel("Volume Médian (Transactions)", fontsize=10, fontweight='bold')
    ax_bar.tick_params(axis='x', rotation=25)
    ax_bar.grid(True, axis='y', ls="--", lw=0.4, alpha=0.6)

    plt.suptitle("Comparaison Synthétique des Métriques (Inclus MR_High & MR_Regular)", fontsize=14, fontweight='bold', y=1.02)
    sns.despine()
    plt.tight_layout()

    chart2_filename = 'analyse_segmentation_summary_v5.png'
    chart2_path_scratch = os.path.join(output_dir_scratch, chart2_filename)
    fig2.savefig(chart2_path_scratch, dpi=200, bbox_inches='tight')
    plt.close(fig2)

    # -------------------------------------------------------------
    # Markdown Report Generation
    # -------------------------------------------------------------
    markdown_report = f"""# Rapport de Validation de la Segmentation des Comptes Cash (Version 5.0)

**Fichier de données analysé** : `{os.path.basename(csv_path)}` ({len(df)} comptes au total).  
**Prise en compte des 6 segments de risque** : `HR_High`, `HR_Regular`, `MR_High`, `MR_Regular`, `LR_High`, `LR_Regular`.

---

## 1. Métriques et Indicateurs par Cluster

| Cluster | Effectif | Montant Total (€) | Montant Médian (€) | Volume Médian | Coeff. Variation | Taux Dépassement Seuil Valeur |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""

    for c in display_clusters:
        row = stats_cluster[stats_cluster['cluster'] == c]
        if not row.empty:
            r = row.iloc[0]
            val_tot = f"{r['valeur_totale']:,.2f} €"
            val_med = f"{r['valeur_mediane']:,.2f} €"
            cv = f"{r['coefficient_variation_valeur']:.2f}" if pd.notna(r['coefficient_variation_valeur']) else "N/A"
            taux_val = f"{r['taux_depassement_valeur']*100:.1f}%"
            markdown_report += f"| **{r['cluster']}** | {r['nombre_comptes']} | {val_tot} | {val_med} | {r['volume_median']:.0f} ops | {cv} | {taux_val} |\n"
        else:
            markdown_report += f"| **{c}** | 0 | 0.00 € | N/A | N/A | N/A | N/A |\n"

    markdown_report += f"""
---

## 2. Diagnostics et Prise en Charge du Risque Moyen (MR)

1. **Intégration des segments `MR_High` et `MR_Regular`** :
   * Le script adapte automatiquement la palette de couleurs et la grille de facettes (2x3) pour inclure le niveau de risque intermédiaire (**Medium Risk**).
   * La hiérarchie visuelle est préservée : **Rouge/Orange** pour le risque élevé (HR), **Violet/Ambre** pour le risque moyen (MR), et **Bleu/Vert** pour le faible risque (LR).

2. **Équilibrage des seuils réglementaires** :
   * Les seuils automatiques intègrent les valeurs de tolérance par palier de risque :
     * **HR** : ~28,5 M€ / 41 transactions
     * **MR** : ~20,0 M€ / 30 transactions
     * **LR** : ~15,8 M€ / 20 transactions

---
*Graphiques associés générés :*
- `analyse_segmentation_facettes_v5.png` (Vue facettée 2x3 Log-Log)
- `analyse_segmentation_summary_v5.png` (Distribution comparative des 6 clusters)
"""

    report_filename = 'synthese_segmentation_cash_v5.md'
    report_path_scratch = os.path.join(output_dir_scratch, report_filename)
    with open(report_path_scratch, 'w', encoding='utf-8') as f:
        f.write(markdown_report)

    # -------------------------------------------------------------
    # Deliver / Publish (Safe Copying)
    # -------------------------------------------------------------
    script_filename = 'analyse_segmentation_v5.py'
    
    script_path_scratch = os.path.join(output_dir_scratch, script_filename)
    if os.path.exists(__file__):
        safe_copy(__file__, script_path_scratch)

    safe_copy(script_path_scratch, os.path.join(output_dir_out, script_filename))
    safe_copy(chart1_path_scratch, os.path.join(output_dir_out, chart1_filename))
    safe_copy(chart2_path_scratch, os.path.join(output_dir_out, chart2_filename))
    safe_copy(report_path_scratch, os.path.join(output_dir_out, report_filename))

    print(f"Analyse v5 exécutée avec succès.\nFichiers générés :\n- {script_filename}\n- {chart1_filename}\n- {chart2_filename}\n- {report_filename}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Analyse de segmentation des comptes cash supportant 6 niveaux de risque (HR, MR, LR).")
    parser.add_argument('csv_path', nargs='?', default='/workspace/artifacts/data_clustering_comptes_cash.csv', help="Chemin vers le fichier CSV")
    parser.add_argument('-o', '--output_dir', default='/workspace/out', help="Dossier de sortie pour les fichiers générés")
    args = parser.parse_args()
    
    run_analysis_v5(args.csv_path, output_dir_out=args.output_dir)
