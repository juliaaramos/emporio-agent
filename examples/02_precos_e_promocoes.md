# Preços e promoções: promoção encerrada, promoção ativa e PIX

> Gerado por `scripts/gerar_exemplos.py` · modelo `openai/gpt-oss-120b` · data de referência 25/03/2026 10:30

**Cliente:** Quanto custa o Takamine GD20? A Oferta Especial de 12% ainda vale?

<details><summary>Rastro das ferramentas</summary>

```text
→ buscar_produtos({"texto": "Takamine GD20"})
← {"total_encontrado": 1, "produtos": [{"product_id": 95, "nome": "Takamine GD20 Dreadnought Natural", "categoria": "Violões", "preco_original": "R$ 2.199,00", "preco_atual": "R$ 2.199,00", "promocao": null, "disponibilidade": "disponível", "promocoes_encerradas": ["Oferta Especial (12%)"]}]}
```
</details>

**Empório:** Oi! O Takamine GD20 Dreadnought Natural está por **R$ 2.199,00**. A “Oferta Especial (12%)” já está encerrada, então o preço atual não tem desconto.  

Posso te ajudar com mais alguma coisa? 🎸

---

**Cliente:** E o Taylor 110e, está em promoção? No PIX tenho mais 5%?

<details><summary>Rastro das ferramentas</summary>

```text
→ buscar_produtos({"texto": "Taylor 110e"})
← {"total_encontrado": 1, "produtos": [{"product_id": 94, "nome": "Taylor 110e Dreadnought Natural", "categoria": "Violões", "preco_original": "R$ 5.999,00", "preco_atual": "R$ 5.519,08", "promocao": {"nome": "Desconto Exclusivo", "desconto_percentual": 8.0}, "disponibilidade": "disponível"}]}
→ calcular_pagamento({"forma": "pix", "itens": [{"product_id": 94}]})
← {"itens": [{"product_id": 94, "nome": "Taylor 110e Dreadnought Natural", "quantidade": 1, "preco_original": "R$ 5.999,00", "promocao": {"nome": "Desconto Exclusivo", "desconto_percentual": 8.0}, "preco_unitario": "R$ 5.519,08"}], "total_a_vista": "R$ 5.519,08", "pagamento_combinado_permitido": true, "forma": "pix", "total": "R$ 5.519,08", "regras": "Desconto PIX não se aplica a itens em promoção (§6.2)."}
```
</details>

**Empório:** Oi! O Taylor 110e Dreadnought Natural está em **promoção “Desconto Exclusivo” de 8 %**, passando de R$ 5.999,00 para **R$ 5.519,08**.

No pagamento via PIX o desconto de 5 % **não se aplica**, pois o produto já está em promoção (conforme §6.2). O valor total à vista fica **R$ 5.519,08**.

Quer saber o frete, parcelar ou acrescentar outro item? 🎶

---

**Cliente:** E em 12x no cartão?

<details><summary>Rastro das ferramentas</summary>

```text
→ calcular_pagamento({"forma": "credito", "itens": [{"product_id": 94}], "parcelas": 12})
← {"itens": [{"product_id": 94, "nome": "Taylor 110e Dreadnought Natural", "quantidade": 1, "preco_original": "R$ 5.999,00", "promocao": {"nome": "Desconto Exclusivo", "desconto_percentual": 8.0}, "preco_unitario": "R$ 5.519,08"}], "total_a_vista": "R$ 5.519,08", "pagamento_combinado_permitido": true, "forma": "credito", "total": "R$ 5.519,08", "parcelas": "11x de R$ 459,92 + 1x de R$ 459,96 sem juros", "regras": "Até 3x: parcela mínima R$ 50; 4x a 6x: R$ 80; 7x a 12x: R$ 100 (§3.1)."}
```
</details>

**Empório:** Oi! Em 12x no cartão o Taylor 110e sai por **R$ 5.519,08** total, dividido em **11 parcelas de R$ 459,92** e **1 parcela de R$ 459,96**, sem juros (conforme §3.1).

Posso calcular o frete ou ajudar com outro produto? 🎸

---
