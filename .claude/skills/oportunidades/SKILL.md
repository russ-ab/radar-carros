---
name: oportunidades
description: Rotina diária do radar de carros na Webmotors — roda a busca, apresenta novos/mudanças de preço/sumidos com análise de cada candidato, publica o comparador e atualiza o ACOMPANHAMENTO.md. Use quando a pessoa pedir "oportunidades", "rodar a busca", "o que apareceu hoje", "busca do dia".
---

# Rotina diária de oportunidades

As regras de negócio estão no `CLAUDE.md` e no `PERFIL.md`: siga-as, não as repita aqui.

## 1. Preparar

1. Sem `config.json`: parar e sugerir o `/setup`.
2. Ler `ACOMPANHAMENTO.md` para saber o que já é candidato, o que foi descartado (e por quê) e as anotações da pessoa.
3. Checar se já existe `data/snapshots/<hoje>.json`. Se existir, **não chamar a API de novo** sem perguntar: usar `python3 -I scripts/busca.py --sem-busca` para regenerar o relatório.

## 2. Buscar

```bash
python3 -I scripts/busca.py
```

No macOS, prefixar com `caffeinate -i` para o Mac não dormir no meio da busca (sem isso, a busca pode ficar parada por minutos entre chamadas).

Roda em foreground com timeout de 600000 ms. São uma busca por alvo + a busca geral, cada página com pausa de 20 a 45 s. Se a busca passar de uns 9 minutos (muitas páginas), rodar em background e esperar a notificação.

- **Exit 2 = bloqueio.** PARAR e avisar a pessoa na hora, mostrando a linha `BLOQUEIO` e o arquivo salvo em `data/raw/`. Depois seguir o procedimento de captcha do `CLAUDE.md`. Não tentar várias vezes sozinho.
- **Exit 1 = config inválido:** mostrar o erro e sugerir `/setup`.
- Ver também as últimas linhas de `data/log.jsonl` (latência ou status estranho).

## 3. Analisar

Ler `data/relatorio.md`. Para comentários e detalhes completos, ler `data/snapshots/<hoje>.json` (campo `comentario`).

Prioridade de análise:
1. **🆕 Novos** e **💲 preço caiu**. Um carro descartado no `ACOMPANHAMENTO.md` só volta se o preço caiu o bastante para mudar o motivo do descarte.
2. **❌ Sumiram**: anotar que provavelmente foi vendido e quantos dias ficou anunciado. Se era candidato, avisar. Conferir se não voltou com outro id (republicação).
3. Os outros "todos de hoje" só entram como contexto de mercado (média de % da FIPE por modelo e cidade).
4. **Fora dos alvos** (da busca geral): analisar como qualquer candidato e **sugerir** os que tiverem bom custo-benefício para os requisitos do `PERFIL.md`. Não viram alvo sem decisão da pessoa.
5. **🚫 Ignorados** (marca proibida, modelo recusado, versão ou ano abaixo do aprovado): não analisar nem dar veredito; aparecem esmaecidos no relatório só para a pessoa ver que existem.

Para cada candidato relevante:
- Parcela em cada prazo, faixa, km/ano, % da FIPE comparado com os outros do mesmo modelo e ano.
- Ler o `comentario`: condições escondidas, leilão, sinistro, revisões, garantia.
- Cruzar com os **pontos de atenção do modelo** no `PERFIL.md` (o ano ou a versão tem o problema? o recall foi feito?).
- **Pesquisar quando agregar** (com fonte): reputação da loja, condições de financiamento da rede, recall da versão, particularidades do ano-modelo. Nada de afirmação de cabeça.
- Duplicados (mesmo carro em lojas do mesmo grupo): tratar como um só.
- Veredito: **visitar** (com o checklist do que pedir), **observar** ou **descartar** (com o motivo).
- Score: a base já vem no snapshot (`score_base`, `score_partes`). Definir os **ajustes** com motivo concreto tirado do anúncio ou da pesquisa. Citar o score final nos destaques.

## 4. Apresentar

**Todo carro citado leva o link do anúncio**: destaques, tabelas, sumidos, duplicados (um link por loja) e qualquer menção solta. Formato: o ID como link markdown, ex.: `[79079827](https://www.webmotors.com.br/comprar/...)`, com a URL do campo `link` do snapshot. Conferir se o ID do texto é o mesmo da URL.

Formato da resposta, direto, sem saudação:
1. Uma linha de resumo: N anúncios hoje, X novos, Y com mudança de preço, Z sumiram, e se houve algum problema com a API.
2. **Destaques**: os 1 a 3 melhores do dia com análise completa e link.
3. Os outros novos e mudanças, em tabela curta com o veredito de uma linha.
4. Sumidos que importam.
5. Observação de mercado, se houver algo útil (ex.: "a cidade X segue com FIPE média de A% contra B% na cidade Y").

Depois disso, **parar e esperar a discussão**.

## 5. Relatório visual

Logo depois de apresentar (antes da discussão, para a pessoa já ter o link):
1. Gravar `data/analises/<hoje>.json`:
   ```json
   {
     "data": "AAAA-MM-DD",
     "resumo": "1 a 3 frases sobre o dia",
     "manchete": "a notícia do dia em uma frase",
     "grupos": [[80931093, 80931131]],
     "destaques": [{"id": 81244787, "titulo": "…", "porque": "…", "pros": ["…"], "contras": ["…"], "pedir": ["…"]}],
     "vereditos": {"81244787": {"veredito": "visitar", "motivo": "…"}},
     "ajustes": {"81244787": [[2, "Selo de revisões na concessionária (sem prova)"]]},
     "achados": [{"texto": "…", "fonte": "https://…"}],
     "mercado": ["…"]
   }
   ```
   `grupos`: ids duplicados, o primeiro é o principal. `vereditos`: todo carro não ignorado do snapshot (só o principal de cada grupo), com `visitar`, `observar` ou `descartar`. `ajustes`: ver "Score" no `CLAUDE.md`.
2. `python3 -I scripts/relatorio_html.py` (gera `relatorios/comparador-<hoje>.html`; baixa as fotos novas com pausa curta). **Conferir a linha final** (tamanho e degrau): se o degrau não for o padrão, avisar que alguns carros saíram com menos fotos; exit 1 = não coube em 16 MB, não publicar e avisar.
3. Publicar com o Artifact:
   - `relatorio.artifact_url` preenchido no `config.json`: publish com `file_path` do arquivo gerado e `url` = esse link.
   - `null` (primeira vez): publish sem `url`, com `icon: "car"`; gravar o link devolvido em `relatorio.artifact_url` no `config.json`.
4. Passar o link à pessoa.

Se a discussão mudar vereditos ou ajustes, atualizar o JSON, gerar e republicar.

## 6. Registrar

Atualizar `ACOMPANHAMENTO.md`:
- Novos relevantes entram em **Em análise** com data, preço e resumo de uma linha.
- O que a pessoa decidir na conversa ("descarta", "quero visitar", "a loja ofereceu X") move o carro de seção, **com o motivo e a data**.
- Sumidos: mover para **Saíram do ar** com a data.
- Mudança de preço: anotar o histórico na linha do carro (ex.: `R$ 89.900 → 87.900 (12/10)`).

Decisão que muda regra (preço máximo, entrada, alvo novo, modelo recusado): atualizar o `config.json`, validar (`python3 -I scripts/config.py validar`) e registrar com data em "Decisões" no `PERFIL.md`.
