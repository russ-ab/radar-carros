# Radar de carros

Um parceiro no Claude Code para achar um carro usado na Webmotors. Uma vez por dia você roda `/oportunidades`: o script busca os anúncios da sua região que passam nos seus cortes, compara com o dia anterior (novos, preço mudou, sumiram), dá uma nota de 0 a 100 para cada carro, e o Claude lê os anúncios, pesquisa loja e modelo e diz o que vale visitar. Junto vem um comparador visual (gráfico preço × km, fotos, tabela) publicado como página privada no claude.ai.

Nasceu da busca de um SUV familiar e terminou numa compra que deu certo. Esta versão é genérica: qualquer cidade, qualquer tipo de carro, à vista ou financiado.

## Requisitos

- [Claude Code](https://claude.com/claude-code) com uma conta claude.ai (o comparador é publicado como Artifact).
- Python 3.9 ou mais novo. Só biblioteca padrão: nada para instalar.
- Opcional: o plugin do Playwright no Claude Code, para destravar a API se a Webmotors pedir captcha.

## Começar

```bash
git clone <este repositório> radar-carros
cd radar-carros
claude
```

No Claude Code, rode `/setup`. É uma entrevista de uns 15 minutos: quem você é e para que é o carro, cidade e raio, orçamento, financiamento (de preferência com uma simulação do seu banco em mãos), cortes e modelos. Para cada modelo-alvo, o Claude pesquisa versões, problemas crônicos, recalls e condições de garantia, com fontes. No fim ele confere a configuração na API da Webmotors.

O setup cria três arquivos **pessoais, fora do git**:

| Arquivo | O que é |
|---|---|
| `config.json` | Regras que os scripts aplicam: local, cortes, alvos, financiamento, régua do score |
| `PERFIL.md` | O porquê de cada regra, os pontos de atenção de cada modelo e o histórico de decisões |
| `ACOMPANHAMENTO.md` | O estado de cada carro (em análise, descartado, comprado) e suas anotações |

Para mudar alguma coisa depois ("subiu a entrada", "quero incluir o HR-V"), rode `/setup` de novo ou peça na conversa.

## Rotina diária

```
/oportunidades
```

1. Busca na API (uma busca por modelo-alvo + uma geral pelo tipo de carroceria), com pausas de 20 a 45 s entre as chamadas. Leva alguns minutos.
2. O Claude apresenta os destaques do dia, os novos, as mudanças de preço e os que sumiram, cada um com link e veredito: **visitar** (com o que pedir na loja), **observar** ou **descartar**.
3. Publica o comparador (sempre no mesmo link) e espera a discussão.
4. O que você decidir vai para o `ACOMPANHAMENTO.md`.

A primeira execução mostra tudo como novo. O comparador é privado; para mostrar a alguém, use o menu Share da página.

## Como a nota é calculada

Cinco critérios somam 100: parcela no maior prazo (ou preço, se for à vista), km total, km por ano, % da tabela FIPE e ano-modelo. As faixas saem dos seus cortes e podem ser ajustadas no setup. Por cima da nota base, o Claude aplica ajustes com motivo concreto (preço que só vale financiando com a loja, revisões comprovadas, anúncio sem descrição…). Detalhes no `CLAUDE.md`.

## Avisos

- A busca usa a API interna do site da Webmotors, que **não é oficial** e pode mudar sem aviso. O projeto faz uso leve de propósito (uma execução por dia, pausas longas). Se a API bloquear (status diferente de 200), o script para sem gravar nada e o Claude explica como destravar.
- As notas e vereditos são uma ajuda para decidir, não uma garantia. Antes de fechar negócio: laudo cautelar, histórico de revisões e test drive.

## Desenvolvimento

```bash
python3 -m unittest discover -s tests
```

Os testes usam o `config.exemplo.json`, que também é a referência do formato. Estrutura e regras do projeto: `CLAUDE.md`.
