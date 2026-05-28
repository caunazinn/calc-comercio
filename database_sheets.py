"""
database_sheets.py
Integração com Google Sheets via gspread.

Atua como camada de persistência do sistema:
  - Lê taxas atualizadas das operadoras de maquininha
  - Salva histórico anonimizado de cálculos (sem dados pessoais)

Estrutura esperada na planilha Google Sheets:
  Aba 'taxas_maquininha':
    tipo_pagamento | taxa_percentual | operadora | atualizado_em

  Aba 'historico_calculos':
    timestamp | tipo_mei | tipo_pagamento | custo_produto |
    preco_calculado | lucro_real | margem_contribuicao_pct
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from config import (
    CABECALHO_HISTORICO,
    CABECALHO_TAXAS,
    NOME_ABA_HISTORICO,
    NOME_ABA_TAXAS,
)

logger = logging.getLogger(__name__)

_ESCOPOS_GOOGLE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def _autenticar(caminho_credenciais: str) -> gspread.Client:
    """
    Cria cliente autenticado usando conta de serviço do Google Cloud.

    O arquivo JSON de credenciais é gerado em:
    Google Cloud Console > IAM > Contas de Serviço > Criar chave
    Compartilhe a planilha com o e-mail da conta de serviço.
    """
    credenciais = Credentials.from_service_account_file(
        caminho_credenciais, scopes=_ESCOPOS_GOOGLE
    )
    return gspread.authorize(credenciais)


class RepositorioSheets:
    """
    Abstrai todas as operações de leitura e escrita no Google Sheets.

    Usa conexão lazy: só abre a planilha na primeira operação real,
    evitando latência no startup da API.
    """

    def __init__(self, id_planilha: str, caminho_credenciais: str):
        self._id_planilha       = id_planilha
        self._caminho_creds     = caminho_credenciais
        self._cliente: Optional[gspread.Client]       = None
        self._planilha: Optional[gspread.Spreadsheet] = None

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def _conectar(self) -> None:
        """Estabelece ou reutiliza a conexão com a planilha."""
        if self._planilha is not None:
            return

        if not self._id_planilha:
            raise EnvironmentError(
                "GOOGLE_SHEETS_ID não configurado. "
                "Defina a variável de ambiente ou verifique o .env"
            )

        try:
            self._cliente  = _autenticar(self._caminho_creds)
            self._planilha = self._cliente.open_by_key(self._id_planilha)
            logger.info("Conexão com Google Sheets estabelecida com sucesso.")
        except SpreadsheetNotFound:
            raise SpreadsheetNotFound(
                f"Planilha '{self._id_planilha}' não encontrada. "
                "Verifique o ID e se a conta de serviço tem permissão de leitura."
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Arquivo de credenciais não encontrado: '{self._caminho_creds}'. "
                "Gere a chave JSON no Google Cloud Console e coloque em credentials/."
            )
        except Exception as erro:
            logger.error(f"Falha ao conectar ao Google Sheets: {erro}")
            raise

    def _obter_aba(self, nome_aba: str) -> gspread.Worksheet:
        """Retorna a aba pelo nome, com mensagem de erro clara."""
        try:
            return self._planilha.worksheet(nome_aba)
        except WorksheetNotFound:
            raise WorksheetNotFound(
                f"Aba '{nome_aba}' não encontrada na planilha. "
                f"Crie a aba com os cabeçalhos: "
                f"{CABECALHO_TAXAS if nome_aba == NOME_ABA_TAXAS else CABECALHO_HISTORICO}"
            )

    # ------------------------------------------------------------------
    # Leitura: taxas de maquininha
    # ------------------------------------------------------------------

    def obter_taxas_maquininha(self) -> Dict[str, float]:
        """
        Lê a tabela de taxas da aba 'taxas_maquininha'.

        Returns:
            Dict {tipo_pagamento: taxa_percentual}
            Retorna dict vazio em caso de falha (sistema usa taxas padrão).
        """
        try:
            self._conectar()
            aba      = self._obter_aba(NOME_ABA_TAXAS)
            registros = aba.get_all_records(expected_headers=CABECALHO_TAXAS[:2])

            taxas: Dict[str, float] = {}
            for linha in registros:
                chave = str(linha.get("tipo_pagamento", "")).strip().lower()
                taxa  = linha.get("taxa_percentual")
                if chave and taxa is not None:
                    try:
                        taxas[chave] = float(taxa)
                    except (ValueError, TypeError):
                        logger.warning(f"Taxa inválida ignorada para '{chave}': {taxa}")

            logger.info(f"{len(taxas)} taxas carregadas do Google Sheets.")
            return taxas

        except WorksheetNotFound as e:
            logger.warning(str(e))
            return {}
        except APIError as e:
            logger.error(f"Erro na API do Google Sheets (quota/permissão): {e}")
            return {}
        except Exception as e:
            logger.error(f"Erro inesperado ao obter taxas: {e}")
            return {}

    # ------------------------------------------------------------------
    # Escrita: histórico de cálculos
    # ------------------------------------------------------------------

    def salvar_historico(
        self,
        tipo_mei: str,
        tipo_pagamento: str,
        custo_produto: float,
        preco_calculado: float,
        lucro_real: float,
        margem_contribuicao_pct: float,
    ) -> bool:
        """
        Registra um cálculo no histórico anonimizado.

        Nenhum dado pessoal é salvo — apenas métricas financeiras
        para análise de impacto e matriz de precisão do projeto.

        Returns:
            True em caso de sucesso, False em caso de falha.
        """
        nova_linha = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tipo_mei,
            tipo_pagamento,
            round(custo_produto, 2),
            round(preco_calculado, 2),
            round(lucro_real, 2),
            round(margem_contribuicao_pct, 2),
        ]

        try:
            self._conectar()
            aba = self._obter_aba(NOME_ABA_HISTORICO)
            aba.append_row(nova_linha, value_input_option="USER_ENTERED")
            logger.info(f"Histórico salvo: preço={preco_calculado}, lucro={lucro_real}")
            return True

        except WorksheetNotFound as e:
            logger.error(str(e))
            return False
        except APIError as e:
            # Não falha a requisição principal por causa do log
            logger.error(f"Erro na API ao salvar histórico (quota?): {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao salvar histórico: {e}")
            return False

    # ------------------------------------------------------------------
    # Leitura: histórico para relatório de impacto
    # ------------------------------------------------------------------

    def listar_historico(self, limite: int = 200) -> List[Dict]:
        """
        Retorna os últimos N registros do histórico de cálculos.

        Útil para gerar o relatório de impacto da Semana 8 e
        a Matriz de Precisão do projeto.
        """
        try:
            self._conectar()
            aba       = self._obter_aba(NOME_ABA_HISTORICO)
            registros = aba.get_all_records()
            return registros[-limite:] if len(registros) > limite else registros

        except Exception as e:
            logger.error(f"Erro ao listar histórico: {e}")
            return []

    # ------------------------------------------------------------------
    # Setup inicial da planilha (helper para configuração)
    # ------------------------------------------------------------------

    def inicializar_abas(self) -> bool:
        """
        Cria as abas necessárias com cabeçalhos, se não existirem.

        Execute uma vez durante o setup do projeto.
        """
        try:
            self._conectar()

            nomes_existentes = [ws.title for ws in self._planilha.worksheets()]

            if NOME_ABA_TAXAS not in nomes_existentes:
                aba_taxas = self._planilha.add_worksheet(
                    title=NOME_ABA_TAXAS, rows=50, cols=4
                )
                aba_taxas.append_row(CABECALHO_TAXAS)
                # Pré-popula com taxas padrão
                from config import TAXAS_MAQUININHA_PADRAO
                for tipo, taxa in TAXAS_MAQUININHA_PADRAO.items():
                    aba_taxas.append_row([tipo, taxa, "Padrão mercado 2025", datetime.now().strftime("%Y-%m-%d")])
                logger.info(f"Aba '{NOME_ABA_TAXAS}' criada e pré-populada.")

            if NOME_ABA_HISTORICO not in nomes_existentes:
                aba_hist = self._planilha.add_worksheet(
                    title=NOME_ABA_HISTORICO, rows=1000, cols=7
                )
                aba_hist.append_row(CABECALHO_HISTORICO)
                logger.info(f"Aba '{NOME_ABA_HISTORICO}' criada.")

            return True

        except Exception as e:
            logger.error(f"Erro ao inicializar abas: {e}")
            return False
