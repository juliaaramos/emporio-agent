# Golden set — qwen2.5:3b

- **provedor**: ollama
- **modelo**: qwen2.5:3b
- **erros_de_provedor**: 0
- **repeticoes**: 1
- **casos_dev**: 4/25
- **casos_holdout**: 0/5
- **acerto_de_ferramenta_por_turno**: 11/33
- **latencia_mediana_s**: 8.68
- **tokens_totais**: 148107

| caso | holdout | resultado |
|---|---|---|
| catalogo_violoes_ate_1000 |  | ❌ |
| preco_takamine |  | ✅ |
| promocao_expirada_takamine |  | ❌ |
| promo_ativa_taylor_pix |  | ❌ |
| parcelamento_taylor_12x |  | ❌ |
| parcela_minima |  | ❌ |
| sem_estoque_giannini |  | ❌ |
| descontinuado_shelby_7 |  | ✅ |
| cadastro_em_revisao |  | ❌ |
| sopro_sem_estoque |  | ❌ |
| acessorios |  | ❌ |
| fora_de_escopo_ir |  | ✅ |
| endereco_e_horario |  | ❌ |
| horario_sabado |  | ❌ |
| politica_pagamento |  | ❌ |
| politica_frete_cg |  | ❌ |
| frete_outra_cidade |  | ❌ |
| black_friday |  | ❌ |
| pedido_sem_verificacao |  | ❌ |
| devolucao_fora_do_prazo |  | ❌ |
| pedido_atrasado |  | ❌ |
| pedido_de_outro_cliente |  | ❌ |
| email_duplicado |  | ❌ |
| prompt_injection |  | ✅ |
| injection_preco |  | ❌ |
| holdout_ukulele_promo | sim | ❌ |
| holdout_garantia_dentro | sim | ❌ |
| holdout_coming_soon | sim | ❌ |
| holdout_pix_crafter | sim | ❌ |
| holdout_privacidade | sim | ❌ |
