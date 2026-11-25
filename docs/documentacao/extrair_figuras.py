"""Extrai dos notebooks executados as figuras usadas na documentação (ABNT).

Uso (a partir da raiz do repositório):
    python docs/documentacao/extrair_figuras.py

As imagens PNG embutidas nas saídas das células são gravadas em
`docs/documentacao/figuras/` com nomes descritivos. Rode novamente sempre que
os notebooks forem reexecutados, e depois recompile o PDF (ver README.md desta pasta).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "figuras"

# (notebook, índice da célula) -> nome do arquivo de saída
FIGURAS = {
    ("A3_CP2_auditoria_etl_eda.ipynb", 77): "fig_hist_tamanho.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 79): "fig_faixas_tamanho.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 81): "fig_preco_volume.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 84): "fig_resumo_diario.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 88): "fig_perfil_horario.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 89): "fig_heatmap_volume.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 91): "fig_caudas_retornos.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 93): "fig_ofi_fluxo.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 94): "fig_ofi_defasagens.png",
    ("A3_CP2_auditoria_etl_eda.ipynb", 96): "fig_correlacao_spearman.png",
    ("A3_CP3_modelagem_storytelling.ipynb", 8): "fig_modelo_volatilidade.png",
    ("A3_CP3_modelagem_storytelling.ipynb", 11): "fig_modelo_direcao.png",
    ("A3_CP3_modelagem_storytelling.ipynb", 15): "fig_storytelling.png",
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, list] = {}
    for (nb_name, cell_idx), out_name in FIGURAS.items():
        if nb_name not in cache:
            nb_path = ROOT / "notebooks" / nb_name
            cache[nb_name] = json.loads(nb_path.read_text(encoding="utf-8"))["cells"]
        cell = cache[nb_name][cell_idx]
        pngs = [
            o["data"]["image/png"]
            for o in cell.get("outputs", [])
            if "data" in o and "image/png" in o["data"]
        ]
        if not pngs:
            raise RuntimeError(f"{nb_name}, célula {cell_idx}: nenhuma figura PNG encontrada.")
        (OUT_DIR / out_name).write_bytes(base64.b64decode(pngs[0]))
        print(f"{out_name:32s} <- {nb_name} [célula {cell_idx}]")


if __name__ == "__main__":
    main()
