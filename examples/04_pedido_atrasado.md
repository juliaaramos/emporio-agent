# Pedido atrasado: consulta em tempo real e chamado para a equipe

> Gerado por `scripts/gerar_exemplos.py` · modelo `openai/gpt-oss-120b` · data de referência 25/03/2026 10:30

**Cliente:** Oi, meu pedido ainda não chegou. Meu e-mail é anacarol.ferreira@coldmail.com, pedido 8

<details><summary>Rastro das ferramentas</summary>

```text
→ verificar_cliente({"email": "anacarol.ferreira@coldmail.com", "order_id": 8})
← {"verificado": true, "primeiro_nome": "Ana"}
→ consultar_pedido({"order_id": 8})
← {"order_id": 8, "data_da_compra": "15/02/2026", "data_de_envio": "não registrada no sistema (não informe)", "status": "enviado", "itens": [{"product_id": 120, "nome": "Kala KA-C Concert Mogno", "quantidade": 1}], "total": "R$ 349,90", "pagamento": "cartão de débito", "codigo_rastreio": "BRJL5544332BR", "rastreio": "Consultar no site dos Correios ou da Jadlog (§5.3).", "previsao_entrega": "28/02/2026", "atrasado": true, "dias_de_atraso": 25, "instrucao": "Peça desculpas e PERGUNTE se a pessoa quer que você abra um chamado (categoria 'atraso'). Só chame encaminhar_humano depois do sim. O retorno…
```
</details>

**Empório:** Oi Ana, tudo bem? 🙁 Seu pedido está com atraso – a previsão era 28/02/2026 e já se passaram 25 dias. Posso abrir um chamado para a equipe investigar o que aconteceu e te dar um retorno em até 24 horas úteis. Você quer que eu registre o chamado?

---

**Cliente:** Pode abrir uma reclamação, por favor?

<details><summary>Rastro das ferramentas</summary>

```text
→ encaminhar_humano({"categoria": "reclamacao", "order_id": 8, "resumo": "Pedido 8 com atraso de 25 dias, cliente solicita abertura de reclamação."})
← {"protocolo": "EMP-20260325-0001", "prazo_retorno": "até 24 horas úteis (§7.3)", "mensagem_para_cliente": "Chamado aberto com o protocolo EMP-20260325-0001. A equipe retorna em até 24 horas úteis.", "instrucao": "Use a mensagem_para_cliente como está. Não prometa solução específica em nome da equipe."}
```
</details>

**Empório:** Chamado **EMP-20260325-0001** aberto. A equipe do Empório da Música vai analisar a situação e retorna em até 24 horas úteis. Precisa de mais alguma coisa?

---
