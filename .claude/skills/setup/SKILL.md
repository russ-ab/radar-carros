---
name: setup
description: Entrevista inicial do radar de carros. Pergunta quem busca, para que é o carro, orçamento, financiamento, cortes e modelos, pesquisa cada modelo-alvo (versões, problemas crônicos, recalls, garantia) e grava config.json, PERFIL.md e ACOMPANHAMENTO.md. Use na primeira vez ("setup", "configurar", "começar") ou para ajustar um bloco ("mudou a entrada", "incluir um modelo", "trocar de cidade").
---

# Setup do radar de carros

Objetivo: sair com um `config.json` válido, um `PERFIL.md` que explique o porquê de cada regra e um `ACOMPANHAMENTO.md` vazio, prontos para a primeira `/oportunidades`. Formato do config: `config.exemplo.json` e a seção "Cortes rígidos" do `CLAUDE.md`.

## Como conduzir

- **Uma pergunta por vez**, sempre com a **sua recomendação** e o motivo ("Recomendo 50 km: pega as cidades vizinhas sem virar viagem"). A pessoa pode só concordar.
- Use o `AskUserQuestion` quando houver opções claras (câmbio, vendedor, à vista ou financiado); pergunta aberta em texto quando não houver.
- **Nada de cabeça:** porta-malas, versões, preços, problemas crônicos, recalls e taxas se pesquisam (WebSearch/WebFetch) e se citam com fonte. Hipótese só para o que não dá para verificar.
- Se a resposta já está no que a pessoa disse antes, não pergunte de novo. Se ela não sabe, proponha um valor e siga ("dá para mudar depois com /setup").
- Linguagem simples: a pessoa pode não ser da área. Explique termos (FIPE, CET, Tabela Price) na primeira vez que aparecerem.

## 0. Começo

1. `python3 --version` (precisa de 3.9 ou mais novo). Se faltar, parar e explicar.
2. Se o `config.json` já existe: rodar `python3 -I scripts/config.py validar`, mostrar o resumo e perguntar **qual bloco** mudar (1 a 6 abaixo). Fazer só esse bloco e ir para o passo 7. Mudanças vão com data para a seção "Decisões" do `PERFIL.md`.
3. Senão, explicar em 3 linhas o que vai acontecer (umas 15 perguntas, pesquisa dos modelos, uma checagem rápida na API) e começar.

## 1. Quem e para quê

- Nome (como Claude deve chamar a pessoa) e quem mais decide (cônjuge, família).
- Cidade e UF → `python3 -I scripts/config.py cidade "<cidade>" <UF>` (grafia oficial, lat/long). Se não achar, conferir a grafia com a pessoa.
- Raio: recomendar 50 km; mostrar as principais cidades que entram (pesquisar se não souber a região). Raio grande aumenta páginas e chamadas à API.
- Uso: dia a dia, viagens, estrada de terra, quantas pessoas, cadeirinha, cachorro, garagem apertada…
- Requisitos que viram critério: porta-malas mínimo (litros), espaço traseiro, consumo, altura, conforto. Pergunte o que **não pode faltar** e o que é **desejável**.

## 2. Carro atual e troca

- Tem carro para dar na troca? Modelo, ano, km. Pesquisar a FIPE dele e dizer o valor com a fonte.
- Avisar: a avaliação na loja costuma vir **abaixo** da FIPE. Recomendar contar com um valor conservador na entrada e avaliar o carro cedo, em mais de uma loja.
- Se a pessoa não quer trocar um carro rodado por outro já perto disso, anotar (vira referência de km).

## 3. Orçamento e financiamento

1. À vista ou financiado?
2. **À vista:** preço máximo (`busca.preco_max`) e preço ideal (`busca.preco_ideal`, nota máxima no score). `financiamento: null`.
3. **Financiado:**
   - Entrada total (dinheiro + troca).
   - Banco e taxa ao mês. Se a pessoa já tem uma **simulação** do banco (preço, entrada, prazo, parcela), calibrar as tarifas: `python3 -I scripts/config.py tarifas <preço> <entrada> <meses> <parcela> <taxa>`. Sem simulação: recomendar pedir uma ao gerente (é o dado mais importante) e, enquanto isso, usar uma estimativa dita como estimativa. Taxas médias por banco: pesquisar as taxas de "aquisição de veículos – pessoa física" publicadas pelo Banco Central, com fonte.
   - Explicar que a **CET não entra como taxa** (ela já inclui as tarifas; usar as duas contaria o custo duas vezes).
   - Prazos (ex.: 36 e 48), parcela **ideal** e parcela **limite** (o máximo numa oportunidade fora da curva).
   - Calcular e mostrar o preço máximo que cada parcela permite em cada prazo (o `validar` do passo 7 já imprime). Recomendar `busca.preco_max` próximo do preço da parcela limite no maior prazo, arredondado para cima.

## 4. Cortes

- Km máximo (recomendar 50 a 60 mil para seminovo; mostrar o efeito na régua do score).
- Câmbio: `automatico` (corta só manual), `manual` ou `qualquer`.
- Vendedor: concessionária e loja (recomendado). Particular (`Pessoa Física` no config) só se a pessoa quiser: explicar que dá mais trabalho (vistoria, documentação, sem garantia).
- Marcas proibidas e modelos recusados, com o motivo (vai para o `PERFIL.md`). Pode ficar vazio.

## 5. Tipo de carro e modelos-alvo

1. Tipo de carroceria (SUV, hatch, sedã, picape, minivan…) e ano-modelo mínimo da **busca geral**. Os nomes de carroceria da Webmotors se conferem no passo 8 (`sondar.py facetas`); "Utilitário esportivo" é o SUV. Pode não ter busca geral (`geral: null`) se a pessoa só quer os alvos.
2. A pessoa já tem modelos em mente? Se não, **pesquisar e propor** de 3 a 5 modelos que cabem no orçamento para o ano mínimo e atendem os requisitos, numa tabela (porta-malas, faixa de preço usado com fonte, pontos fortes, pontos fracos). Ela escolhe e ordena (plano A, B, C).
3. **Para cada alvo, pesquisar a fundo** (é o coração do setup; usar um subagente por modelo se forem vários, cada um com o modelo, os anos e o orçamento, e conferir o que voltar):
   - Gerações e mudanças por ano-modelo (renomeações como "Kicks" → "Kicks Play", troca de motor, facelift).
   - Versões por ano, da mais simples à topo, e quais cabem no orçamento. Propor `exigir` ou `excluir` (palavras da versão como a Webmotors escreve) e `ano_min`.
   - **Problemas crônicos e pontos de atenção** (câmbio, motor, correia, suspensão, elétrica), **recalls** (Procon/Senatran/montadora), custo de revisão, e **condições de garantia** que dependem de histórico (ex.: garantia estendida que exige revisões na concessionária). Cada ponto com fonte e com a pergunta concreta a fazer na loja.
   - Porta-malas e outros requisitos do passo 1.
   - Mostrar o resultado como no exemplo do `PERFIL.md` e pedir confirmação.
4. A chave de cada alvo é o nome curto em minúsculas, sem acento nem espaço (`t-cross`, `hr-v`). `marca` e `modelo` em maiúsculas como na Webmotors (conferidos no passo 8).

## 6. Régua do score

Mostrar a régua padrão (seção "Score" do `CLAUDE.md`), já com os valores dela: "parcela até R$ X = 10…, km até Y = 25…". Perguntar se algo não faz sentido para ela (ex.: ano pesa mais que km). Na dúvida, manter o padrão e não escrever `score` no config. Se mudar, os pesos precisam somar 100.

## 7. Gravar

1. Escrever o `config.json` (sem `score` se for o padrão; `relatorio.artifact_url: null`).
2. `python3 -I scripts/config.py validar`. Erro → corrigir e repetir. Mostrar o resumo à pessoa.
3. Escrever o `PERFIL.md` a partir de `.claude/skills/setup/perfil-modelo.md`, com tudo o que foi dito e pesquisado (fontes incluídas). Se já existe, editar só as seções do bloco que mudou e registrar em "Decisões".
4. Se não existe, criar o `ACOMPANHAMENTO.md` a partir de `.claude/skills/setup/acompanhamento-modelo.md`.

## 8. Calibrar com a API

Poucas chamadas, com pausa (antibot: ver o `CLAUDE.md`).
1. Se houver dúvida no nome da carroceria ou de algum modelo: `python3 -I scripts/sondar.py facetas` (carrocerias e marcas no raio) e `python3 -I scripts/sondar.py facetas --marca <MARCA>` (modelos da marca). Corrigir o config.
2. `python3 -I scripts/sondar.py buscas` (uma chamada por busca, pausa de 20 a 45 s). Conferir:
   - `a API entendeu`: marca, modelo e carroceria reconhecidos. Alvo com 0 anúncios = grafia errada ou modelo raro no raio.
   - Versões **aceitas** e **ignoradas** de cada alvo: alguma versão boa ficou de fora, ou alguma básica passou? Ajustar `exigir`/`excluir` e validar de novo.
   - Número de páginas: cada página é uma chamada com pausa na rotina diária. Mais de 10 páginas na busca geral → sugerir apertar carroceria, ano ou preço.
3. Status ≠ 200 (exit 2) = bloqueio: parar e seguir o procedimento do `CLAUDE.md`.

## 9. Fechamento

Resumo curto: o que foi configurado, os alvos com o principal ponto de atenção de cada um, e como usar:
- `/oportunidades` uma vez por dia (a primeira execução mostra tudo como novo).
- O relatório visual é publicado como Artifact privado; o link fica salvo no config.
- `/setup` de novo para mudar qualquer bloco.
