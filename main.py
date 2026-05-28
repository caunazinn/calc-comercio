"""
main.py
Endpoint HTTP da Calculadora de Sobrevivência.

Expõe uma API REST simples que o n8n chama via HTTP Request node.
O n8n coleta os dados do usuário no Telegram, monta o payload JSON,
envia para este endpoint, e repassa a resposta formatada de volta ao chat.

Iniciar servidor:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Fluxo completo:
    Telegram → n8n → POST /calcular → Python → n8n → Telegram
"""

import logging
import os
import warnings
from typing import Optional

# Silencia FutureWarnings do google-auth sobre Python 3.9 EOL
warnings.filterwarnings("ignore", category=FutureWarning, module="google")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from calculos_financeiros import (
    ParametrosEntrada,
    ResultadoCalculo,
    calcular_preco_por_markup,
    formatar_resultado_telegram,
)
from config import TAXAS_MAQUININHA_PADRAO
from database_sheets import RepositorioSheets

# -------------------------------------------------------------------
# Configuração inicial
# -------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Calculadora de Sobrevivência",
    description=(
        "Motor de precificação para microempreendedores (MEI) cearenses. "
        "Recebe dados do n8n (Telegram) e retorna preço de venda real com lucro garantido."
    ),
    version="1.0.0",
    docs_url="/docs",
)

# Repositório com conexão lazy (não bloqueia o startup se Sheets estiver offline)
_repo = RepositorioSheets(
    id_planilha=os.getenv("GOOGLE_SHEETS_ID", ""),
    caminho_credenciais=os.getenv(
        "GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json"
    ),
)


# -------------------------------------------------------------------
# Schemas de entrada e saída (validação automática pelo Pydantic)
# -------------------------------------------------------------------

class RequisicaoCalculo(BaseModel):
    """
    Payload que o n8n envia ao Python após coletar dados do usuário no Telegram.
    Todos os campos numéricos usam ponto como separador decimal (padrão JSON).
    """

    custo_produto: float = Field(
        ..., gt=0, description="Custo de compra ou produção do produto (R$)"
    )
    margem_lucro_desejada: float = Field(
        ..., gt=0, lt=100, description="Percentual de lucro líquido desejado (ex: 30 para 30%)"
    )
    tipo_pagamento: str = Field(
        ...,
        description=(
            "Meio de pagamento: pix | dinheiro | debito | "
            "credito_vista | credito_2a6 | credito_7a12"
        ),
    )
    despesas_fixas_percentual: float = Field(
        default=0.0,
        ge=0,
        lt=60,
        description="% do faturamento com custos fixos (aluguel, energia). Default: 0",
    )
    vendas_mensais_estimadas: int = Field(
        default=50,
        gt=0,
        description="Quantidade de produtos vendidos por mês (para rateio do DAS-MEI). Default: 50",
    )
    tipo_mei: str = Field(
        default="comercio",
        description="Categoria da atividade: comercio | servicos | ambos. Default: comercio",
    )
    taxa_maquininha_override: Optional[float] = Field(
        default=None,
        ge=0,
        description="Sobrescreve a taxa padrão com taxa negociada (opcional)",
    )

    @field_validator("tipo_pagamento")
    @classmethod
    def validar_tipo_pagamento(cls, v: str) -> str:
        tipos_validos = list(TAXAS_MAQUININHA_PADRAO.keys())
        if v not in tipos_validos:
            raise ValueError(
                f"'{v}' não é um tipo de pagamento válido. "
                f"Use: {tipos_validos}"
            )
        return v

    @field_validator("tipo_mei")
    @classmethod
    def validar_tipo_mei(cls, v: str) -> str:
        if v not in ("comercio", "servicos", "ambos"):
            raise ValueError("tipo_mei deve ser 'comercio', 'servicos' ou 'ambos'")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "custo_produto": 85.00,
            "margem_lucro_desejada": 30,
            "tipo_pagamento": "credito_vista",
            "despesas_fixas_percentual": 5.0,
            "vendas_mensais_estimadas": 40,
            "tipo_mei": "comercio",
            "taxa_maquininha_override": None,
        }
    }}


class RespostaCalculo(BaseModel):
    """Resposta completa que o n8n recebe e exibe no Telegram."""

    sucesso: bool
    mensagem_telegram: str
    """Texto formatado em Markdown — o n8n envia isso diretamente ao usuário."""

    preco_venda_sugerido: float
    lucro_real_valor: float
    lucro_real_percentual: float
    margem_contribuicao_pct: float
    taxa_maquininha_percentual: float
    das_mei_unitario: float
    detalhamento: dict


class RespostaErro(BaseModel):
    sucesso: bool = False
    codigo_erro: str
    mensagem_usuario: str
    """Mensagem amigável para o n8n exibir ao empreendedor."""


# -------------------------------------------------------------------
# Tratamento global de erros de validação
# -------------------------------------------------------------------

@app.exception_handler(Exception)
async def handler_erro_generico(request: Request, exc: Exception):
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "sucesso": False,
            "codigo_erro": "ERRO_INTERNO",
            "mensagem_usuario": (
                "Ocorreu um erro interno. "
                "Tente novamente ou contate o suporte."
            ),
        },
    )


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------

@app.get("/health", tags=["Sistema"])
def health_check():
    """Verifica se o serviço está no ar. Usado pelo n8n e monitoramento."""
    return {"status": "ok", "servico": "Calculadora de Sobrevivência v1.0"}


@app.get("/taxas", tags=["Dados"])
def listar_taxas():
    """
    Retorna as taxas de maquininha vigentes.
    Prioriza o Google Sheets; usa tabela padrão como fallback.
    """
    taxas_sheets = _repo.obter_taxas_maquininha()
    if taxas_sheets:
        return {"fonte": "google_sheets", "taxas": taxas_sheets}
    return {"fonte": "padrao", "taxas": TAXAS_MAQUININHA_PADRAO}


@app.get("/historico", tags=["Dados"])
def listar_historico(limite: int = 100):
    """
    Retorna os últimos N cálculos do histórico anonimizado.
    Usado para o relatório de impacto do projeto.
    """
    registros = _repo.listar_historico(limite=limite)
    return {"total": len(registros), "registros": registros}


@app.post("/setup", tags=["Sistema"])
def inicializar_planilha():
    """
    Cria as abas 'taxas_maquininha' e 'historico_calculos' na planilha.
    Execute uma única vez durante a configuração inicial do projeto.
    """
    sucesso = _repo.inicializar_abas()
    if not sucesso:
        raise HTTPException(
            status_code=500,
            detail="Falha ao inicializar a planilha. Verifique as credenciais e o ID.",
        )
    return {"sucesso": True, "mensagem": "Abas criadas e pré-populadas com sucesso."}


@app.post("/calcular", response_model=RespostaCalculo, tags=["Cálculo"])
def calcular_preco(body: RequisicaoCalculo):
    """
    Endpoint principal chamado pelo n8n.

    Recebe os dados coletados do usuário no Telegram,
    calcula o preço de venda real e retorna a resposta formatada.
    """
    logger.info(
        f"Novo cálculo — custo: R${body.custo_produto:.2f} | "
        f"pagamento: {body.tipo_pagamento} | margem: {body.margem_lucro_desejada}%"
    )

    # Carrega taxas atualizadas do Sheets (falha silenciosamente → usa padrão)
    taxas_sheets = _repo.obter_taxas_maquininha()

    # Executa o cálculo financeiro
    try:
        parametros = ParametrosEntrada(
            custo_produto               = body.custo_produto,
            margem_lucro_desejada       = body.margem_lucro_desejada,
            tipo_pagamento              = body.tipo_pagamento,
            despesas_fixas_percentual   = body.despesas_fixas_percentual,
            vendas_mensais_estimadas    = body.vendas_mensais_estimadas,
            tipo_mei                    = body.tipo_mei,
            taxa_maquininha_override    = body.taxa_maquininha_override,
        )
        resultado: ResultadoCalculo = calcular_preco_por_markup(
            parametros, taxas_externas=taxas_sheets or None
        )

    except ValueError as e:
        mensagem_usuario = (
            f"Não consegui calcular. Verifique os dados informados:\n"
            f"_{str(e)}_"
        )
        raise HTTPException(
            status_code=422,
            detail={
                "sucesso": False,
                "codigo_erro": "ERRO_CALCULO",
                "mensagem_usuario": mensagem_usuario,
            },
        )

    # Persiste no histórico de forma não-bloqueante (log anônimo)
    _repo.salvar_historico(
        tipo_mei                 = body.tipo_mei,
        tipo_pagamento           = body.tipo_pagamento,
        custo_produto            = resultado.custo_produto,
        preco_calculado          = resultado.preco_venda_sugerido,
        lucro_real               = resultado.lucro_real_valor,
        margem_contribuicao_pct  = resultado.indice_margem_contribuicao,
    )

    mensagem = formatar_resultado_telegram(resultado)

    logger.info(
        f"Cálculo concluído — preço: R${resultado.preco_venda_sugerido:.2f} | "
        f"lucro: R${resultado.lucro_real_valor:.2f}"
    )

    return RespostaCalculo(
        sucesso                     = True,
        mensagem_telegram           = mensagem,
        preco_venda_sugerido        = resultado.preco_venda_sugerido,
        lucro_real_valor            = resultado.lucro_real_valor,
        lucro_real_percentual       = resultado.lucro_real_percentual,
        margem_contribuicao_pct     = resultado.indice_margem_contribuicao,
        taxa_maquininha_percentual  = resultado.taxa_maquininha_percentual,
        das_mei_unitario            = resultado.das_mei_valor_unitario,
        detalhamento                = resultado.detalhamento,
    )
