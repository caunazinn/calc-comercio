"""
calculos_financeiros.py
Motor de precificação da Calculadora de Sobrevivência.

Modelos implementados:
  1. Markup Divisor  — determina o preço de venda a partir do custo
  2. Margem de Contribuição — analisa a lucratividade por unidade
  3. Distribuição proporcional do DAS-MEI por unidade vendida

Fórmula central (Markup Divisor):
    Markup Divisor = 1 - (taxa_maquininha% + desp_fixas% + margem_lucro%) / 100
    Preço de Venda = (Custo Produto + DAS unitário) / Markup Divisor

Por que o DAS é somado ao custo e não entra no divisor?
    O DAS-MEI é uma despesa FIXA mensal (não proporcional à receita),
    então é distribuído como custo unitário adicional — garantindo que
    cada venda carregue sua fração do imposto, sem distorção percentual.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

from config import (
    DAS_MEI_2025,
    NOMES_MEI,
    NOMES_PAGAMENTO,
    TAXAS_MAQUININHA_PADRAO,
)


# -------------------------------------------------------------------
# Utilitário de arredondamento
# -------------------------------------------------------------------

def _arredondar(valor: float, casas: int = 2) -> float:
    """Arredondamento ROUND_HALF_UP (bancário) para precisão monetária."""
    return float(
        Decimal(str(valor)).quantize(Decimal(10) ** -casas, rounding=ROUND_HALF_UP)
    )


# -------------------------------------------------------------------
# Modelos de dados (entrada e saída)
# -------------------------------------------------------------------

@dataclass
class ParametrosEntrada:
    """Dados brutos coletados do empreendedor via Telegram."""

    custo_produto: float
    """Custo de compra ou produção do produto (R$)."""

    margem_lucro_desejada: float
    """Percentual de lucro líquido desejado sobre o preço de venda."""

    tipo_pagamento: str
    """Chave do meio de pagamento: pix, debito, credito_vista, credito_2a6, credito_7a12."""

    despesas_fixas_percentual: float = 0.0
    """% do faturamento comprometida com custos fixos (aluguel, energia, etc.)."""

    vendas_mensais_estimadas: int = 50
    """Quantidade estimada de unidades vendidas por mês — base do rateio do DAS."""

    tipo_mei: str = "comercio"
    """Categoria da atividade MEI: 'comercio', 'servicos' ou 'ambos'."""

    taxa_maquininha_override: Optional[float] = None
    """Sobrescreve a taxa padrão/Sheets com um valor manual (ex: taxa negociada)."""


@dataclass
class ResultadoCalculo:
    """Resultado completo do cálculo de precificação."""

    preco_venda_sugerido: float
    custo_produto: float
    taxa_maquininha_percentual: float
    taxa_maquininha_valor: float
    das_mei_valor_unitario: float
    das_mei_percentual: float
    despesas_fixas_valor: float
    lucro_real_valor: float
    lucro_real_percentual: float
    margem_contribuicao_unitaria: float
    indice_margem_contribuicao: float
    markup_divisor: float
    tipo_pagamento_nome: str
    tipo_mei_nome: str
    detalhamento: Dict = field(default_factory=dict)


# -------------------------------------------------------------------
# Funções auxiliares
# -------------------------------------------------------------------

def _obter_taxa_maquininha(
    tipo_pagamento: str,
    taxas_externas: Optional[Dict] = None,
    override: Optional[float] = None,
) -> float:
    """
    Resolve a taxa do meio de pagamento com prioridade:
        override manual  >  Google Sheets  >  tabela padrão
    """
    if override is not None:
        if override < 0:
            raise ValueError("A taxa de maquininha não pode ser negativa.")
        return override

    fonte = taxas_externas if taxas_externas else TAXAS_MAQUININHA_PADRAO

    if tipo_pagamento not in fonte:
        raise ValueError(
            f"Tipo de pagamento '{tipo_pagamento}' não reconhecido. "
            f"Opções válidas: {list(TAXAS_MAQUININHA_PADRAO.keys())}"
        )

    return float(fonte[tipo_pagamento])


def _calcular_das_unitario(
    tipo_mei: str,
    vendas_mensais: int,
    das_mensal_override: Optional[float] = None,
) -> float:
    """
    Distribui o DAS-MEI mensal fixo em custo por unidade vendida.

    Evita que o empreendedor "esqueça" o imposto e perca margem mês a mês.
    """
    if vendas_mensais <= 0:
        raise ValueError("A estimativa de vendas mensais deve ser maior que zero.")

    das_mensal = das_mensal_override or DAS_MEI_2025.get(tipo_mei)

    if das_mensal is None:
        raise ValueError(
            f"Tipo MEI '{tipo_mei}' inválido. Use: {list(DAS_MEI_2025.keys())}"
        )

    return das_mensal / vendas_mensais


# -------------------------------------------------------------------
# Função principal de cálculo
# -------------------------------------------------------------------

def calcular_preco_por_markup(
    parametros: ParametrosEntrada,
    taxas_externas: Optional[Dict] = None,
) -> ResultadoCalculo:
    """
    Calcula o preço de venda mínimo rentável pelo método Markup Divisor.

    Garante que taxa de maquininha, DAS-MEI e despesas fixas estejam
    embutidos no preço — eliminando a miopia financeira do empreendedor.

    Args:
        parametros:      Dados brutos do produto e do negócio.
        taxas_externas:  Dict de taxas carregado do Google Sheets (opcional).

    Returns:
        ResultadoCalculo com preço sugerido, lucro real e decomposição.

    Raises:
        ValueError: Se os parâmetros forem inválidos ou matematicamente impossíveis.
    """
    # --- Validações de entrada ---
    if parametros.custo_produto <= 0:
        raise ValueError("O custo do produto deve ser um valor positivo.")
    if not (0 < parametros.margem_lucro_desejada < 100):
        raise ValueError("A margem de lucro desejada deve estar entre 0% e 100%.")
    if parametros.despesas_fixas_percentual < 0:
        raise ValueError("O percentual de despesas fixas não pode ser negativo.")

    # --- Resolução das taxas ---
    taxa_maquininha = _obter_taxa_maquininha(
        parametros.tipo_pagamento,
        taxas_externas,
        parametros.taxa_maquininha_override,
    )

    das_unitario = _calcular_das_unitario(
        parametros.tipo_mei,
        parametros.vendas_mensais_estimadas,
    )

    # --- Markup Divisor ---
    # Todos os percentuais incidem SOBRE o preço de venda (não sobre o custo)
    soma_percentuais = (
        taxa_maquininha
        + parametros.despesas_fixas_percentual
        + parametros.margem_lucro_desejada
    ) / 100.0

    if soma_percentuais >= 1.0:
        raise ValueError(
            f"A soma de taxas + despesas fixas + margem ({soma_percentuais * 100:.1f}%) "
            "atingiu ou ultrapassou 100%. Reduza a margem ou as despesas."
        )

    markup_divisor = 1.0 - soma_percentuais

    # DAS entra como custo fixo unitário (somado ao custo antes da divisão)
    custo_total_unitario = parametros.custo_produto + das_unitario
    preco_venda = custo_total_unitario / markup_divisor

    # --- Decomposição do preço ---
    valor_maquininha   = preco_venda * (taxa_maquininha / 100)
    valor_desp_fixas   = preco_venda * (parametros.despesas_fixas_percentual / 100)
    lucro_real_valor   = preco_venda * (parametros.margem_lucro_desejada / 100)
    das_percentual     = (das_unitario / preco_venda) * 100

    # --- Margem de Contribuição ---
    # MC = Preço - Custos Variáveis (custo produto + DAS + maquininha)
    # MC cobre as despesas fixas E o lucro → IMC = desp_fixas% + margem%
    custos_variaveis   = parametros.custo_produto + das_unitario + valor_maquininha
    mc_unitaria        = preco_venda - custos_variaveis
    imc                = (mc_unitaria / preco_venda) * 100

    # --- Retorno ---
    return ResultadoCalculo(
        preco_venda_sugerido        = _arredondar(preco_venda),
        custo_produto               = _arredondar(parametros.custo_produto),
        taxa_maquininha_percentual  = _arredondar(taxa_maquininha),
        taxa_maquininha_valor       = _arredondar(valor_maquininha),
        das_mei_valor_unitario      = _arredondar(das_unitario),
        das_mei_percentual          = _arredondar(das_percentual),
        despesas_fixas_valor        = _arredondar(valor_desp_fixas),
        lucro_real_valor            = _arredondar(lucro_real_valor),
        lucro_real_percentual       = _arredondar(parametros.margem_lucro_desejada),
        margem_contribuicao_unitaria= _arredondar(mc_unitaria),
        indice_margem_contribuicao  = _arredondar(imc),
        markup_divisor              = _arredondar(markup_divisor, 4),
        tipo_pagamento_nome         = NOMES_PAGAMENTO.get(parametros.tipo_pagamento, parametros.tipo_pagamento),
        tipo_mei_nome               = NOMES_MEI.get(parametros.tipo_mei, parametros.tipo_mei),
        detalhamento={
            "custo_base":                   _arredondar(parametros.custo_produto),
            "das_unitario":                 _arredondar(das_unitario),
            "custo_total_antes_markup":     _arredondar(custo_total_unitario),
            "markup_divisor":               _arredondar(markup_divisor, 4),
            "taxa_maquininha_pct":          taxa_maquininha,
            "despesas_fixas_pct":           parametros.despesas_fixas_percentual,
            "margem_lucro_desejada_pct":    parametros.margem_lucro_desejada,
            "das_mensal_total":             DAS_MEI_2025.get(parametros.tipo_mei),
            "vendas_mensais_estimadas":     parametros.vendas_mensais_estimadas,
        },
    )


# -------------------------------------------------------------------
# Formatação da resposta para o Telegram
# -------------------------------------------------------------------

def formatar_resultado_telegram(resultado: ResultadoCalculo) -> str:
    """
    Gera a mensagem formatada em Markdown para exibição no Telegram.

    O n8n recebe essa string pronta e a envia diretamente ao usuário,
    com parse_mode='Markdown'.
    """
    r = resultado
    linha = "─" * 32

    return (
        f"🧮 *CALCULADORA DE SOBREVIVÊNCIA*\n"
        f"`{linha}`\n"
        f"💳 *Pagamento:* {r.tipo_pagamento_nome}\n"
        f"🏪 *Atividade MEI:* {r.tipo_mei_nome}\n"
        f"`{linha}`\n"
        f"📦 *Custo do produto:*    R$ {r.custo_produto:.2f}\n"
        f"📊 *DAS-MEI diluído:*     R$ {r.das_mei_valor_unitario:.2f} "
        f"({r.das_mei_percentual:.1f}%)\n"
        f"💳 *Taxa maquininha "
        f"({r.taxa_maquininha_percentual:.2f}%):* R$ {r.taxa_maquininha_valor:.2f}\n"
        f"🏠 *Despesas fixas:*      R$ {r.despesas_fixas_valor:.2f}\n"
        f"`{linha}`\n"
        f"💰 *PREÇO DE VENDA:* R$ {r.preco_venda_sugerido:.2f}\n"
        f"✅ *Lucro real:*     R$ {r.lucro_real_valor:.2f} "
        f"({r.lucro_real_percentual:.1f}%)\n"
        f"📈 *Margem de Contribuição:* {r.indice_margem_contribuicao:.1f}%\n"
        f"`{linha}`\n"
        f"_Calculado pela Calculadora de Sobrevivência_ 🚀"
    )
