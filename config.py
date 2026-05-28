"""
config.py
Constantes e configurações centrais da Calculadora de Sobrevivência.

Todas as taxas e parâmetros financeiros vivem aqui para facilitar
atualização sem tocar nas regras de negócio.
"""

# -------------------------------------------------------------------
# DAS-MEI 2025
# Base: salário mínimo R$ 1.518,00 | INSS 5% = R$ 75,90
# ICMS fixo R$ 1,00 (comércio) | ISS fixo R$ 5,00 (serviços)
# -------------------------------------------------------------------
DAS_MEI_2025 = {
    "comercio":  76.90,   # INSS + ICMS
    "servicos":  80.90,   # INSS + ISS
    "ambos":     81.90,   # INSS + ICMS + ISS
}

# -------------------------------------------------------------------
# Taxas padrão de maquininha — fallback quando Sheets indisponível
# Fonte: pesquisa de mercado Cielo / PagSeguro / Stone / Mercado Pago (2025)
# -------------------------------------------------------------------
TAXAS_MAQUININHA_PADRAO = {
    "pix":           0.00,   # PIX — isento para MEI na maioria das maquininhas
    "dinheiro":      0.00,   # Dinheiro — sem taxa
    "debito":        1.50,   # Débito — média mercado
    "credito_vista": 2.99,   # Crédito 1x
    "credito_2a6":   3.89,   # Crédito parcelado 2–6x
    "credito_7a12":  4.99,   # Crédito parcelado 7–12x
}

# Nomes amigáveis para exibição no Telegram
NOMES_PAGAMENTO = {
    "pix":           "PIX",
    "dinheiro":      "Dinheiro",
    "debito":        "Débito",
    "credito_vista": "Crédito à Vista (1x)",
    "credito_2a6":   "Crédito Parcelado (2–6x)",
    "credito_7a12":  "Crédito Parcelado (7–12x)",
}

NOMES_MEI = {
    "comercio": "Comércio",
    "servicos": "Serviços",
    "ambos":    "Comércio + Serviços",
}

# -------------------------------------------------------------------
# Google Sheets — nomes das abas (devem existir na planilha)
# -------------------------------------------------------------------
NOME_ABA_TAXAS     = "taxas_maquininha"
NOME_ABA_HISTORICO = "historico_calculos"

# Cabeçalhos esperados na aba de taxas
CABECALHO_TAXAS = ["tipo_pagamento", "taxa_percentual", "operadora", "atualizado_em"]

# Cabeçalhos da aba de histórico (dados anonimizados)
CABECALHO_HISTORICO = [
    "timestamp", "tipo_mei", "tipo_pagamento",
    "custo_produto", "preco_calculado", "lucro_real", "margem_contribuicao_pct",
]
