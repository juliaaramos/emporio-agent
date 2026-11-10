# Empório da Música — agente de atendimento

Protótipo de agente de mensagens de texto que atende clientes da Empório da Música (loja fictícia de instrumentos em Campo Grande/MS): catálogo, preços, promoções, pagamento, frete, status de pedidos, trocas e devoluções, horários e informações da loja.

A ideia central: **o LLM conversa e decide o que consultar; o código consulta e calcula.** Preço, parcela, frete, prazo de devolução e checagem de identidade são feitos em Python, com testes. O modelo nunca faz conta, nunca resolve conflito de dados e nunca recebe valores em reais como argumento.

---

## Como rodar

Requisitos: Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # Windows: copy .env.example .env
python scripts/configurar_chaves.py   # grava as chaves no .env sem exibi-las
```

### Provedor do modelo

Qualquer API compatível com a da OpenAI funciona. Há quatro perfis prontos (`LLM_PROVIDER` no `.env` ou `--provider` na linha de comando):

| Perfil | Modelo padrão | Chave | Custo |
|---|---|---|---|
| `groq` (padrão) | openai/gpt-oss-120b (modelo aberto, servido pela Groq) | `GROQ_API_KEY` ([console](https://console.groq.com/keys)) | plano gratuito, sem cartão |
| `gemini` | gemini-3.5-flash | `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)) | plano gratuito (20 requisições/dia) |
| `ollama` | qwen2.5:3b | nenhuma ([ollama.com](https://ollama.com), depois `ollama pull qwen2.5:3b`) | local |
| `openai` | gpt-4.1-mini | `OPENAI_API_KEY` | pago |

Para outro endpoint, defina `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`. Se a Groq gratuita recusar pedidos por limite de tokens de saída por minuto (acontece com `qwen/qwen3.8-27b`), defina `GROQ_MAX_TOKENS=900`. As chaves são lidas **só do `.env`** do projeto, nunca das variáveis de ambiente da máquina, para não usar por engano uma chave de outro projeto. O `.env` está no `.gitignore`; nunca versione chaves.

### Comandos

```bash
python -m emporio.cli                     # conversa
python -m emporio.cli --trace             # mostra cada chamada de ferramenta e o consumo de tokens
python -m emporio.cli --provider groq     # escolhe o provedor
python -m emporio.cli --resume            # retoma a última conversa (histórico em SQLite)

pytest                                    # testes determinísticos (sem rede, sem chave)
python -m emporio.eval                    # golden set contra o LLM (3 repetições por caso)
python -m emporio.eval --provider gemini groq ollama --runs 1 --pause 5   # compara provedores
python scripts/gerar_exemplos.py          # regenera examples/*.md
python -m emporio.data_quality            # relatório de qualidade dos dados
```

### Data de referência

Os dados terminam em 22/03/2026. Com o relógio real, todo pedido pendente pareceria parado há meses e todo prazo de devolução estaria vencido. Por isso o `.env` define `REFERENCE_DATE=2026-03-25` e `REFERENCE_TIME=10:30` (quarta-feira, loja aberta), o "agora" da loja. Deixe vazio para usar o relógio real. Nessa data nenhum pedido entregue está dentro dos 7 dias de arrependimento; o caso em que a devolução é aceita está coberto em teste com outra data (`test_return_accepted_with_other_reference_date`).

---

## Decisões técnicas

### Abordagem: function calling com ferramentas determinísticas

12 ferramentas tipadas sobre SQLite:

| Ferramenta | O que faz |
|---|---|
| `buscar_produtos` | busca sem acento e tolerante a erro de digitação; preço original e atual, promoção ativa, disponibilidade, alerta de cadastro |
| `detalhar_produto` | descrição, specs e promoções encerradas (para responder "aquela promoção ainda vale?") |
| `listar_promocoes_ativas` | só o que está ativo no sistema |
| `calcular_pagamento` | recebe só códigos e quantidades; aplica promoção, PIX não cumulativo, faixas de parcela mínima e arredondamento |
| `calcular_frete` | regra da região metropolitana ou prazos de PAC/SEDEX/Jadlog |
| `verificar_cliente` | e-mail + (nº do pedido ou 4 últimos dígitos do telefone); grava o cliente no estado da sessão |
| `listar_pedidos_do_cliente`, `consultar_pedido` | só pedidos do cliente verificado; checagem no código |
| `avaliar_devolucao` | calcula arrependimento, troca por preferência, troca por defeito e garantia legal de um pedido |
| `consultar_politica` | texto exato de uma seção do manual (lista fechada) |
| `info_loja` | contatos, horários e se a loja está aberta agora (feriados nacionais e de MS) |
| `encaminhar_humano` | abre chamado com protocolo e prazo de 24 horas úteis |

**Por que não text-to-SQL:** são 6 tabelas pequenas e perguntas previsíveis. SQL gerado pelo modelo aumentaria o risco (vazar dados de outro cliente, errar uma soma) sem ganho real.

**Por que não RAG vetorial:** o manual tem cerca de 3 mil tokens e seções bem definidas. Ele foi extraído uma vez para [`data/policies.md`](data/policies.md), dividido por seção, e a ferramenta `consultar_politica` recebe a seção de uma lista fechada. Não existe falha de recuperação, e cada consulta de política fica registrada, o que permite medir se o agente *sabe quando consultar políticas*, um dos critérios do desafio. Um teste confere frase a frase se o `policies.md` bate com o PDF. Colocar o manual inteiro no prompt também funcionaria, mas aí não daria para medir esse comportamento.

**Por que sem framework (LangChain etc.):** o loop de function calling tem ~100 linhas ([`agent.py`](src/emporio/agent.py)). Explícito é mais fácil de depurar, testar com um cliente falso e trocar de provedor.

### Segurança por construção, não por prompt

- O cliente verificado fica no estado da sessão, injetado pelo código. O modelo não tem como passar um `customer_id`; se tentar, a chamada é rejeitada.
- Pedido de outro cliente devolve "não encontrei no seu cadastro", sem revelar que existe.
- Verificação com limite de 3 tentativas e mensagem genérica (não revela se o e-mail existe).
- As ferramentas devolvem só o primeiro nome; nunca telefone ou e-mail.
- A verificação não é persistida: ao retomar uma conversa, o cliente se identifica de novo.
- A quantidade exata em estoque nunca chega ao modelo, porque é informação interna da loja. A busca diz só "disponível" ou "últimas unidades". Se o cliente pergunta "tem 3?", `detalhar_produto` recebe a quantidade e responde sim ou não, sem revelar o número.

### Estratégia de prompt

[`prompts/system.md`](src/emporio/prompts/system.md): persona do §7.1 ("um amigo que entende de música"), fluxo de 5 passos do §7.2 e regras inegociáveis (nada de preço, prazo ou política sem ferramenta; promoção sempre com preço original e percentual; o sistema, não o calendário, diz se uma promoção vale). O prompt recebe a data, a hora e se a loja está aberta, para avisar o horário de retorno fora do expediente (§7.1). As descrições das ferramentas também são prompt: dizem quando usar cada uma.

As respostas das ferramentas carregam instruções contextuais (ex.: `alerta_cadastro`, `nota_de_interpretacao`, `instrucao` em pedido atrasado). Assim a regra chega ao modelo no momento em que importa, sem inflar o prompt de sistema.

### Escolha do modelo

Restrição autoimposta: o projeto tinha que rodar **sem custo**, para qualquer avaliador conseguir testar. Comparei três opções gratuitas no golden set (tabela em [Resultados](#resultados)):

- **Groq / gpt-oss-120b — escolhido.** Melhor resultado com folga (22/25 casos, 31/33 turnos com a ferramenta certa), segue o protocolo de verificação e cita as seções do manual. Modelo de pesos abertos: dá para migrar para outro provedor ou rodar localmente com hardware adequado.
- **Gemini 3.5 Flash.** Responde bem em testes avulsos, mas o plano gratuito tem cota de 20 requisições/dia por modelo, insuficiente até para uma rodada da avaliação.
- **Ollama / qwen2.5:3b (local).** Único que cabia numa máquina de 8 GB sem GPU. Não segue o protocolo de ferramentas (4/25). Mantido como opção sem chave, com a limitação documentada.

A arquitetura não depende do modelo: trocar é uma linha no `.env`, e o golden set mede o impacto da troca.

### Interface e memória

CLI com `rich` (o desafio prioriza o agente funcionando). Histórico persistido em SQLite por sessão (`data/sessions.db`), com janela das últimas 40 mensagens enviadas ao modelo sem separar uma chamada de ferramenta do seu resultado. Chamados ficam numa tabela `tickets`.

---

## Avaliação

- **Testes determinísticos** (`pytest`, 60 testes, sem rede): qualidade de dados, fidelidade do manual, todas as ferramentas e casos de borda, e o loop do agente com um LLM falso.
- **Golden set** ([`tests/eval/golden.yaml`](tests/eval/golden.yaml)): 26 casos de desenvolvimento + 5 reservados (holdout) que não foram usados para ajustar o prompt. Inclui conversas com várias mensagens. Para cada turno o avaliador confere: ferramentas chamadas, política respondida sem `consultar_politica` (conta como falha), valores em R$ extraídos da resposta contra o gabarito (inclusive valores proibidos, como o PIX acumulado com promoção) e recusas. Cada caso roda 3 vezes com temperatura 0 e só passa se passar nas 3. LLM como juiz é opcional (`--judge`) e só avalia o tom. O caso `quantidade_em_estoque` entrou depois da comparação abaixo (que usa os 25 casos originais); ele passa com qwen/qwen3.8-27b e ainda não foi rodado no gpt-oss-120b.

### Resultados

Golden set com 1 repetição por caso (detalhes e leitura em [`eval_results/comparacao.md`](eval_results/comparacao.md)):

| Provedor / modelo | Casos dev (25) | Holdout (5) | Ferramenta certa por turno | Latência mediana |
|---|---|---|---|---|
| **Groq / gpt-oss-120b** | **22/25** | **4/5** | **31/33** | 18,4 s |
| Ollama / qwen2.5:3b (CPU) | 4/25 | 0/5 | 11/33 | 8,7 s |
| Gemini / 3.5 Flash | inválido: cota diária esgotada (33 erros do provedor) | — | — | — |

O que as falhas ensinaram (e o que mudou):

- **Ferramenta, não prompt:** o modelo local classificou "Takamine GD20" como guitarra e a busca voltou vazia. A busca agora tenta de novo sem a categoria. O mesmo raciocínio levou a expor promoções encerradas já na busca, para que "a promoção ainda vale?" seja respondida com dado e não por dedução.
- **Erro real de comunicação:** no caso de devolução, o modelo recebeu `elegivel: false` com garantia até 23/01/2026 e, mesmo assim, sugeriu que a troca por defeito era possível. O prompt passou a mandar seguir o campo `elegivel` à risca e explicar a garantia do fabricante antes de abrir chamado.
- **Erros vistos nas conversas de exemplo, corrigidos na ferramenta:** o modelo escreveu no chamado o nome completo da cliente, deduzido do e-mail, e confundiu a data do pedido com a de envio. Agora o código monta os dados do pedido no chamado e o modelo só descreve o relato do cliente. Ao sugerir "outros violões em promoção", o modelo incluiu o desconto de um ukulele; `listar_promocoes_ativas` passou a filtrar por categoria. O modelo também abriu chamado sem perguntar e, depois, um segundo chamado para o mesmo pedido: a ferramenta agora devolve o protocolo existente em vez de duplicar, e a instrução do pedido atrasado manda perguntar antes. Erros de português ("Chamei aberto", "se encerraria") levaram as ferramentas a devolver frases prontas para prazos e protocolos.
- **Robustez de provedor:** a Groq valida a chamada de ferramenta gerada e devolve 400 quando ela vem malformada; o agente refaz a chamada uma vez.
- **Bug do avaliador:** o modelo escreveu "e‑mail" com hífen Unicode; a normalização de texto passou a tratar hífens Unicode.
- **Holdout não usado para ajuste:** o pedido de exclusão de dados (§9) foi tratado como fora de escopo. Registrado como falha conhecida, sem ajuste no prompt.

Limitação da própria avaliação: o plano gratuito da Groq dá 200 mil tokens/dia por modelo e uma rodada completa usa ~235 mil, então as 3 repetições previstas não couberam num dia. As correções foram validadas em execuções dirigidas dos casos afetados; uma rodada completa com 3 repetições é o próximo passo.

### Conversas de exemplo

Cinco conversas reais em [`examples/`](examples/), geradas por `scripts/gerar_exemplos.py` com o rastro das chamadas de ferramenta (bloco "Rastro das ferramentas" em cada turno). Nada foi editado à mão.

| Arquivo | Cenário |
|---|---|
| [01_catalogo_violoes](examples/01_catalogo_violoes.md) | Violões até R$ 1.000 e produto sem estoque com alternativas |
| [02_precos_e_promocoes](examples/02_precos_e_promocoes.md) | Promoção encerrada, promoção ativa, PIX não cumulativo e 12x |
| [03_devolucao_fora_do_prazo](examples/03_devolucao_fora_do_prazo.md) | **Caso não trivial:** verificação do cliente, prazos calculados, garantia legal vencida e garantia do fabricante |
| [04_pedido_atrasado](examples/04_pedido_atrasado.md) | Pedido atrasado consultado em tempo real e chamado aberto |
| [05_fora_de_escopo_e_loja](examples/05_fora_de_escopo_e_loja.md) | Acessórios, pergunta fora de escopo, endereço e horário |

Todas foram geradas com o modelo padrão (`openai/gpt-oss-120b`). Para regenerar todas: `python scripts/gerar_exemplos.py groq`; para uma só: `python scripts/gerar_exemplos.py groq 04_pedido_atrasado`. O script não salva conversas em que o provedor falhou.

---

## Qualidade dos dados e suposições

Os CSVs originais ficam intactos em `data/raw/`; o sistema usa uma cópia tratada (`data/emporio.db`, gerada por `python -m emporio.ingest`).

| # | Problema | O que foi feito | Em produção |
|---|---|---|---|
| 1 | Produtos 135 a 144 com cara de cadastro automático: nome genérico ("Bass 3X"), marca do nome diferente da descrição em 7 deles, specs que contradizem a descrição (137: 5 cordas × 4; 139: Poplar × Maple; 142: 88 × 61 teclas; 135: Alder × Ash) e preços atípicos (baixo a R$ 441) | Detecção em código por quatro sinais → `data_quality_flag = cadastro_em_revisao`. O agente informa nome, preço e disponibilidade (dados do sistema, §7.1), mas não afirma specs nem descrição e diz que a equipe vai confirmar | Alerta automático para o responsável pelo catálogo corrigir na origem |
| 2 | 96 ativo sem estoque; 113 descontinuado; 136 descontinuado com 13 unidades | Disponibilidade = status + estoque. Descontinuado nunca é oferecido, mesmo com estoque (§7.3); sugere alternativas | Regra no ERP impedindo o estado inconsistente |
| 3 | 130 `coming_soon` aparece no pedido 3, já entregue | Agente diz "em breve" e não vende; inconsistência no relatório | Revisar o status com a equipe |
| 4 | Total gravado ≠ soma dos itens (pedido 3: 3.450 × 3.498; pedido 20: 1.400 × 1.488) | Mostra o total gravado, sem recalcular (pode haver desconto não registrado) | Guardar desconto/frete por pedido |
| 5 | Promoções repetidas (93, 96, 99), nenhuma com validade | Só vale `is_active=1`, uma por produto (a de maior desconto) | Datas de início/fim nas promoções |
| 6 | Telefone/WhatsApp: §1.2 diz (67) 3341-4444; §7 diz WhatsApp (67) 3321-4500. E-mail com acento no §1.2 | 3341-4444 como telefone, 3321-4500 como WhatsApp (§7 é específico); e-mail sem acento (a capa não tem) | Confirmar com a loja |
| 7 | Tabela de pagamento: "parcela mínima R$ 100"; §3.1 detalha faixas; "sem valor mínimo (exceto abaixo de R$ 50)" é ambíguo | Segue o §3.1: até 3x ≥ R$ 50; 4x–6x ≥ R$ 80; 7x–12x ≥ R$ 100. Parcelas com centavos truncados e a última absorve a diferença. Pagamento combinado só acima de R$ 2.000 | Confirmar com o financeiro |
| 8 | E-mail bruno.martins@jmail.com em dois clientes (11 e 43) | Verificação com e-mail + segundo dado (pedido ou final do telefone), que desambigua | E-mail único no cadastro |
| 9 | Dados terminam em 03/2026 | `REFERENCE_DATE` (ver acima) | Relógio real |
| 10 | PIX 5% não acumula com promoção (§6.2) | Regra fixa em `calcular_pagamento`, por item | — |
| 11 | Manual fala em sopros e 300+ instrumentos; base tem 65 e nenhum sopro | "No momento não temos esse tipo de instrumento disponível", nunca "não vendemos" | — |
| 12 | §4.2: defeito em até 30 dias da compra; §8.1: garantia legal de 90 dias do recebimento (CDC) | Vale o mais protetivo: a loja atende defeito até o maior dos dois prazos; depois, garantia do fabricante com intermediação (§4.2, §8.2) | Revisar o manual |
| 13 | §4.1 (arrependimento) vale só para compra online | Pedido com código de rastreio = online. Sem data real de entrega, o prazo conta da previsão de entrega (informado ao cliente) | Registrar data de entrega e canal da venda |
| 14 | §6.1 cita Black Friday e Semana do Músico; nenhuma ativa | Vale só o sistema; se perguntarem, o agente diz com transparência que não está ativa e mostra o preço atual (§7.3) | — |

Outras suposições: a região metropolitana de Campo Grande (§5.1) foi tratada como só Campo Grande (o manual não lista os municípios); pedido de exatamente R$ 500 tem frete grátis (o manual diz "acima" e "abaixo"); os 7 dias de troca por preferência (§4.3) contam do recebimento; baixos, baterias e teclados podem exigir frete especial fora da região (§5.2).

---

## Limitações e próximos passos

- **Autenticação real:** e-mail e telefone não são segredo. Em produção, código por WhatsApp/e-mail (OTP).
- **Integração com o WhatsApp** (canal principal do §7) via API oficial, com o estado de sessão por número.
- **Feriados municipais** de Campo Grande e horários especiais (§2) numa tabela configurável.
- **Cotação real de frete** por CEP (Correios/Jadlog).
- **Observabilidade:** registrar cada chamada de ferramenta, latência e custo; alertar quando o agente responde sem consultar.
- **Avaliação contínua no CI** com o golden set, mais casos adversariais e LLM como juiz calibrado com notas humanas.
- **Chamados e alertas de qualidade de dados** integrados ao sistema da equipe, em vez de uma tabela local.
- **LGPD:** o histórico em SQLite contém dados pessoais. Em produção: retenção definida (ex.: 90 dias), anonimização depois disso, criptografia em repouso e atendimento a pedidos de exclusão (§9).

---

## Uso de assistente de código

Trabalho com **desenvolvimento orientado a especificação (spec-driven development)**: faço todo o levantamento de requisitos e a análise de causa raiz (RCA) dos problemas antes de escrever código, e só então começo a desenvolver. Neste projeto usei o **Claude Code** (extensão do VS Code) como assistente de implementação. O fluxo foi este:

1. **Levantamento de requisitos.** Antes do código, escrevi um plano de ação: leitura do enunciado, dos CSVs e do manual de políticas; inventário dos problemas de qualidade dos dados e de como tratar cada um; arquitetura, ferramentas, critérios de avaliação (golden set) e os cenários das conversas de exemplo, com os números conferidos nos dados.
2. **Especificação validada antes de implementar.** Pedi ao assistente que confrontasse o plano com o enunciado. As lacunas encontradas entraram na especificação antes de qualquer código: uma ferramenta para calcular prazos de devolução (o modelo nunca faz conta), a exposição de promoções encerradas para responder "essa promoção ainda vale?" e a hora fixa para os testes serem reprodutíveis.
3. **Implementação a partir da especificação.** O código e os testes foram desenvolvidos com o Claude Code, seguindo o plano. As decisões de produto e de risco foram minhas: nada publicado sem minha revisão, só provedores gratuitos, nenhuma chave corporativa, chaves fora do código e do chat (gravadas no `.env` por um script local) e casos reservados do golden set fora do ajuste do prompt.
4. **RCA em cada falha.** Testei o agente conversando com ele e rodando o golden set. Cada problema foi classificado (erro do modelo, do provedor, do avaliador ou dos dados) e corrigido na causa, de preferência na ferramenta, e não no texto da resposta. Exemplos: a quantidade exata em estoque deixou de chegar ao modelo, o resumo do chamado passou a ser montado pelo código, chamados duplicados passaram a ser bloqueados e os prazos de garantia passaram a vir com a frase pronta. As conversas de exemplo foram regeneradas depois das correções, nunca editadas à mão.
