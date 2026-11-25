# Documentação técnica (ABNT) — fonte LaTeX

Fonte do PDF [`../documentacao_projeto_A3.pdf`](../documentacao_projeto_A3.pdf), escrito com a classe
[abnTeX2](https://www.abntex.net.br/) segundo as normas da ABNT (NBR 14724, 6023, 6024, 6027, 6028 e 10520).

| Arquivo | Conteúdo |
|---|---|
| `documentacao_A3.tex` | Preâmbulo, capa, folha de rosto, resumo/abstract, listas e sumário |
| `capitulos/*.tex` | Um arquivo por capítulo, mais os apêndices |
| `referencias.bib` | Referências (estilo `abntex2-alf`) |
| `figuras/` | Gráficos extraídos dos notebooks executados |
| `extrair_figuras.py` | Reextrai as figuras dos notebooks |

## Como compilar

Requer uma distribuição TeX com abnTeX2, `newtx`, `zi4`, `dirtree` e TikZ (TeX Live completo ou, no Debian/Ubuntu,
`texlive-publishers texlive-latex-extra texlive-fonts-extra texlive-lang-portuguese texlive-science tex-gyre`).
A partir da raiz do repositório:

```bash
python docs/documentacao/extrair_figuras.py
```

```bash
cd docs/documentacao && latexmk -pdf -outdir=build documentacao_A3.tex && cp build/documentacao_A3.pdf ../documentacao_projeto_A3.pdf
```

Para preencher o nome do(a) professor(a) na folha de rosto, edite a macro `\nomeprofessor` no início de
`documentacao_A3.tex`.
