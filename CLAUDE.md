# Radar de carros na Webmotors

Ferramenta pessoal para achar um carro usado. A rotina: a pessoa roda `/oportunidades` no chat, o script busca na API da Webmotors, Claude analisa o que mudou e os dois discutem os resultados. **Não é automação fria**: Claude tem autonomia para pesquisar contexto (loja, modelo, histórico de mercado) e ponderar cada anúncio.

**Primeira vez (sem `config.json`): rodar `/setup`.** Ele entrevista a pessoa, pesquisa os modelos e grava a configuração. Rodar de novo ajusta só um bloco ("mudou a entrada", "quero incluir o HR-V").

## Perfil de quem está buscando

@PERFIL.md

(O `PERFIL.md` é criado pelo `/setup`. Ele traz quem é a pessoa, para que é o carro, os modelos-alvo com os pontos de atenção pesquisados e o histórico de decisões. Se o import acima estiver vazio, o setup ainda não foi feito.)

## Onde ficam as regras

| Arquivo | O que guarda | Quem lê |
|---|---|---|
| `config.json` | Cortes rígidos, alvos, financiamento, régua do score, link do relatório | Scripts (validado por `scripts/config.py`) |
| `PERFIL.md` | O porquê de cada regra, pontos de atenção dos modelos, decisões com data | Claude |
| `ACOMPANHAMENTO.md` | Estado de cada carro e anotações da pessoa | Claude |

Os três são pessoais e ficam fora do git. **Mudou uma regra na conversa → atualizar o `config.json`, rodar `python3 -I scripts/config.py validar` e registrar a decisão com data no `PERFIL.md`.** O `config.exemplo.json` é a referência do formato e também a configuração dos testes.

Projeto pessoal: mudanças em script e regra são feitas direto, com os testes (`python3 -m unittest discover -s tests`) como verificação rápida. Python 3.9 ou mais novo, só biblioteca padrão. Sempre rodar com `python3 -I`.

## Cortes rígidos (aplicados pelo script)

Vêm do `config.json`:

| Critério | Chave | Efeito |
|---|---|---|
| Raio a partir da cidade | `local` | Filtro da API (`localizacao=lat,lngxRkm`) |
| Preço e km máximos | `busca.preco_max`, `busca.km_max` | Filtro da API |
| Vendedor | `busca.vendedores` | Filtro da API (`Concessionária`, `Loja`, `Pessoa Física`) |
| Câmbio | `busca.cambio` | `automatico` corta só o manual (Automática, CVT e automatizado passam); `manual` ou `qualquer`. Fora do escolhido **some** (nem entra no snapshot) |
| Marcas proibidas, modelos recusados | `busca.marcas_proibidas`, `busca.modelos_recusados` | **Ignorados**: aparecem esmaecidos, fora do ranking e do diff |
| Versão e ano dos alvos | `alvos.<chave>.exigir`, `excluir`, `ano_min` | Abaixo do aprovado = **ignorado** |

**Buscas:** uma por modelo-alvo + uma **busca geral** opcional (`busca.geral`: carroceria e ano-modelo mínimo), unidas pelo id do anúncio. A geral traz modelos fora dos alvos; eles entram como candidatos para Claude **sugerir**, mas não viram alvo sem decisão da pessoa. Sem filtro de carroceria a busca geral pode ter milhares de anúncios (dezenas de páginas): conferir com `scripts/sondar.py buscas` antes.

Regras de versão: `exigir` = a versão precisa ter ao menos uma dessas palavras; `excluir` = não pode ter nenhuma. A comparação é por palavra inteira, sem acento. O modelo casa por palavra também ("KICKS" pega "KICKS PLAY").

## Financiamento

`financiamento` no config (ou `null` para compra à vista, com `busca.preco_ideal`):
- **Tabela Price.** Saldo = preço − entrada + tarifas. As tarifas e o IOF que o banco soma ao financiado entram em `tarifas`.
- **Calibrar com uma simulação real do banco**: `python3 -I scripts/config.py tarifas <preço> <entrada> <meses> <parcela> <taxa>` devolve as tarifas embutidas. **A CET não entra como taxa nas contas:** ela já é o efeito das tarifas e do IOF sobre a taxa nominal. Usar a CET e ainda somar as tarifas contaria o custo duas vezes.
- Sempre mostrar a parcela em todos os `prazos`. `parcela_ideal` e `parcela_limite` são referências, não limites rígidos (o corte rígido é o `preco_max`).
- **Financiamento da loja é alternativa a comparar, não sinal de alerta.** Redes de seminovos e locadoras costumam ter taxas próprias, às vezes melhores com entrada alta. Quando o candidato for de rede, pesquisar as condições e comparar. Único alerta: preço anunciado que **só vale** com o financiamento da loja; nesse caso, comparar usando a taxa da loja.
- **Carro na troca:** a avaliação da loja costuma vir abaixo da FIPE e da expectativa (no caso que originou este projeto: R$ 26,3 mil contra R$ 32 mil esperados). Se a entrada depende da troca, sugerir avaliar o carro cedo (em mais de uma loja) e mostrar o efeito de uma avaliação menor na parcela.

## Ponderação (análise de Claude, caso a caso)

- **Preço:** o % da FIPE vem da API (`FipePercent`). Comparar dentro do mesmo modelo e ano.
- **Quilometragem:** a média por ano (ano atual − ano de fabricação, mínimo 1) é referência, sem precisão; o carro pode ter começado a rodar depois. Acima de 15 mil km/ano é alerta, não descarte. **Mais rodado precisa ser mais barato.**
- **Locadoras** (Localiza, Movida, Unidas, Lions): **não são bloqueadas.** Uma ex-locadora dentro da FIPE e com cerca de 10 mil km/ano pode ser candidata. Avaliar pela rodagem e pelo preço.
- **Requisitos do perfil** (porta-malas, espaço, consumo…): valem principalmente para as sugestões fora dos alvos.
- **Pontos de atenção dos modelos** estão no `PERFIL.md` (problemas crônicos, recalls, exigências de garantia). Um ponto de atenção vira pergunta concreta para a loja.

## Lições da Webmotors (valem para qualquer busca)

- **Descrição escondida:** o `comentario` do snapshot é a descrição da loja (`LongComment`). Na página do anúncio ela aparece como "Sobre este carro", **mas só quando o texto não tem telefone/WhatsApp**: com contato, a Webmotors esconde a seção inteira. Quando um ajuste ou veredito vier de um texto com contato, citar o trecho e avisar que a pessoa não vai encontrá-lo na página.
- **Ler o `comentario`** procurando condições escondidas ("preço válido para financiamento", "mediante troca", "valor promocional" sem detalhe), sinais de leilão ou sinistro e informações de revisão.
- **Selos não provam nada:** os `atributos` ("Único dono", "Todas as revisões feitas pela concessionária", "Garantia de fábrica"…) são marcados pela loja no cadastro. Já houve loja com o selo de revisões na concessionária que, perguntada, confirmou que as revisões não foram feitas lá. Ajuste de no máximo +2 com essa ressalva; a prova é o manual carimbado ou o histórico no sistema da marca.
- **Duplicados:** grupos anunciam o mesmo carro em várias lojas. Reconhecer pelo km e preço quase iguais e tratar como um só (`grupos` na análise).
- **Republicação:** o mesmo carro pode sumir e voltar com outro id. Comparar km, cor, loja e preço com os que sumiram nos dias anteriores.
- **Nem todo estoque está na Webmotors:** concessionárias têm seminovos só no site próprio. Quando a pessoa estiver perto de decidir, vale olhar o site das concessionárias da marca na região.
- **Carro bom vende rápido:** um candidato muito abaixo da FIPE e com boa procedência pode sumir no mesmo dia. Se o veredito for "visitar", dizer isso e sugerir contato antes de ir.

## Score (0 a 100)

A **base** é calculada no script (`pontuar` em `scripts/busca.py`, com testes) pela régua `score` do config: cada critério tem um peso e uma curva `[[valor, pontos], ...]` (retas entre os pontos; antes do primeiro e depois do último, fica no extremo). Os pesos somam 100.

| Critério | Peso padrão | Curva padrão |
|---|---|---|
| Parcela no maior prazo (`parcela`) ou preço à vista (`preco`) | 10 | parcela ideal = 10, limite = 2, 10% acima do limite = 0 / preço ideal = 10, preço máximo = 0 |
| Km total (`km`) | 25 | até 70% do km máximo = 25, km máximo = 7,5 |
| Km por ano (`uso`) | 20 | até 10 mil = 20, 20 mil = 0 |
| % da FIPE (`fipe`) | 25 | até 90% = 25, 100% = 15, 110% = 0 |
| Ano-modelo (`ano`) | 20 | ano mínimo = 8, três anos depois = 20 |

O padrão vem de `score_padrao` em `scripts/config.py`; o config sobrescreve qualquer critério. O **modelo não pontua**: a preferência de modelo fica na análise e no veredito. O comparador lê a mesma régua do config, então os popovers do score sempre batem com o cálculo, e o gerador recalcula o score de dias anteriores com a régua atual.

Por cima da base entram **ajustes da análise** (`ajustes` em `data/analises/<data>.json`), sempre com motivo concreto: preço só à vista (−8), preço só com financiamento da loja (−10), recall a confirmar (−2), revisões na concessionária comprovadas (+4), selo de revisões sem prova (+2), garantia ou laudo cautelar no anúncio (+2/+3), anúncio sem descrição (−2) etc. O score não substitui o veredito: um carro pode ter nota alta e mesmo assim ser descartado (o motivo explica).

## Relatório visual (comparador)

`relatorios/modelos/comparador.html`: gráfico preço × km com o score em cada ponto, painel com fotos e composição do score, tabela ordenável. Descartados e ignorados aparecem sempre, esmaecidos e no fim; ignorados ficam sem score ("—").
- Gerar: `python3 -I scripts/relatorio_html.py --data <AAAA-MM-DD>` → `relatorios/comparador-<data>.html` (fotos baixadas para `data/fotos/` e embutidas, porque a página publicada não carrega imagens externas).
- **Salvaguarda de tamanho:** o limite do Artifact é 16 MB. Acima de 15 MiB o gerador reduz as fotos em degraus (`DEGRAUS` em `scripts/relatorio_html.py`); os destaques sempre levam todas. Imprime o tamanho e o degrau usado; se nada couber, sai com erro (exit 1).
- Publicar **sempre no mesmo link**: Artifact publish com `url` = `relatorio.artifact_url` do config. Na primeira vez (`null`), publicar sem `url` e gravar o link devolvido no config. A página é privada; para mostrar a alguém, a pessoa compartilha pelo menu Share.

## Postura

- **Fato verificável se pesquisa e se cita com fonte** (WebSearch/WebFetch): fichas técnicas, porta-malas, manutenção, recalls, reputação de loja, condições de financiamento. Nunca responder de cabeça. "Hipótese" só para o que realmente não dá para verificar.
- Ir direto à análise, em português do Brasil.
- Veredito por candidato: **visitar** (com o que pedir na loja: histórico de revisões carimbado, laudo cautelar, condição de financiamento) / **observar** / **descartar** (com o motivo).
- As decisões são da pessoa. Claude sugere, ela decide; toda decisão vai com data para o `PERFIL.md` ou o `ACOMPANHAMENTO.md`.

## Estrutura

```
scripts/config.py          carrega/valida/completa o config.json; cidade → lat/long; tarifas de uma simulação; resumo
scripts/busca.py           busca na API (alvos + geral) + cortes/ignorados + parcela + score base + snapshot + relatório em texto
scripts/sondar.py          sondagem leve para o /setup: facetas (carrocerias, marcas, modelos) e teste de cada busca
scripts/relatorio_html.py  snapshot + análise do dia → comparador (HTML com fotos embutidas)
relatorios/modelos/        modelo do comparador
tests/                     testes das regras puras (python3 -m unittest discover -s tests)
config.exemplo.json        formato do config e configuração dos testes
data/ref/municipios.csv    municípios do IBGE com lat/long (github.com/kelvins/municipios-brasileiros)
data/snapshots/*.json      fotografia diária (base do diff; não apagar)
data/analises/*.json       análise do dia escrita por Claude
data/fotos/                cache das fotos dos anúncios
data/relatorio.md          relatório da última execução (gerado)
data/log.jsonl             status de cada chamada à API (monitoramento do antibot)
data/cookies.json          cookies exportados do navegador após captcha (opcional; dado sensível de sessão)
.claude/skills/setup/          entrevista inicial (e modelos do PERFIL.md e do ACOMPANHAMENTO.md)
.claude/skills/oportunidades/  roteiro da rotina diária
```

## Webmotors: API e antibot

- Endpoint (não oficial): `GET https://www.webmotors.com.br/api/search/car?url=<url da busca, encoded>&displayPerPage=47&actualPage=N&showCount=true&order=1`. Os filtros vão dentro de `url`, no formato da página de busca (`localizacao=lat,lngxRkm`, `estadocidade`, `marca1`, `modelo1`, `carroceria`, `anode`, `precoate`, `kmate`, `anunciante`). Resposta: `SearchResults`, `Count`, `Pagination`, `FilterCustom` (mostra como a API entendeu os filtros). `showMenu=true` adiciona as facetas (em `Filters` em 11/2026; antes vinham em `FiltersGrouped`). Nomes úteis: `BodyType` (carrocerias: Hatchback, Sedã, Utilitário esportivo, Picape…), `Make`, `SellerType` (Concessionária, Loja, Pessoa Física), `Transmission`.
- `anode` filtra pelo **ano-modelo**, não pelo de fabricação.
- A API responde sem cookies. As **páginas HTML** são protegidas pelo PerimeterX/HUMAN e caem em captcha após poucas navegações automatizadas.
- **Uso leve:** pausas de 20 a 45 s entre chamadas, uma execução por dia.
- **Bloqueio na API (status ≠ 200): avisar a pessoa IMEDIATAMENTE.** Procedimento (precisa do Playwright MCP): abrir a Webmotors no navegador, tirar print do captcha (em `.playwright-mcp/`), a pessoa resolve, exportar os cookies do contexto (`page.context().cookies()`) para `data/cookies.json` e rodar de novo, reusando o mesmo contexto do navegador. Sem o Playwright MCP: a pessoa abre a Webmotors no próprio navegador, resolve e espera algumas horas antes de tentar de novo.
- No desktop, a página da Webmotors reescreve o raio de 50 para 100 km sozinha (condição de corrida no JavaScript). A API não tem esse problema.
