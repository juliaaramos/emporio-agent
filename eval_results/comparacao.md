# Comparação de modelos (golden set, 1 repetição por caso)

Data de referência 25/03/2026 10:30. Executado em 09/11/2026, nos planos gratuitos.

| Provedor | Modelo | Casos dev (25) | Holdout (5) | Ferramenta certa por turno | Latência mediana | Tokens | Erros do provedor |
|---|---|---|---|---|---|---|---|
| Groq | openai/gpt-oss-120b | **22/25** | **4/5** | **31/33** | 18,4 s | 235.095 | 1 (400: chamada de ferramenta malformada) |
| Ollama (local, CPU) | qwen2.5:3b | 4/25 | 0/5 | 11/33 | 8,7 s* | 148.107 | 0 |
| Gemini | gemini-3.5-flash | 2/25 (inválido) | 0/5 (inválido) | 12/33 | 22,9 s | 34.472 | 33 (22× 429 cota diária, 11× 400) |

\* A latência do qwen2.5:3b parece menor porque ele pulou a maioria das chamadas de ferramenta.

## Leitura

- **Groq / gpt-oss-120b** foi escolhido como padrão. As 3 falhas de desenvolvimento foram analisadas:
  uma era bug do avaliador (hífen Unicode em "e‑mail"), uma veio de um 400 do provedor (tratado com
  nova tentativa no agente) e uma era um erro real de comunicação no caso de devolução (o modelo
  sugeriu troca por defeito com o prazo já vencido), corrigido no prompt e na ferramenta e
  revalidado em execução dirigida. A falha no holdout (pedido de exclusão de dados tratado como
  fora de escopo) foi mantida sem ajuste, por ser caso reservado.
- **Ollama / qwen2.5:3b** cabe em 8 GB de RAM sem GPU, mas não segue o protocolo de ferramentas:
  responde horário, frete e pagamento sem consultar o sistema e tentou consultar pedido sem
  verificar o cliente (bloqueado pelo código). Fica como opção para rodar sem chave, não para produção.
- **Gemini 3.5 Flash**: o resultado não mede qualidade. O plano gratuito permite **20 requisições
  por dia por modelo**, e o golden set precisa de mais de 100. Os 400 não puderam ser investigados
  com a cota esgotada.

Limite do plano gratuito da Groq: 200 mil tokens por dia por modelo. Uma rodada completa do golden
set consome ~235 mil, por isso a avaliação com 3 repetições não coube num único dia.
