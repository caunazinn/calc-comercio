"""
test_calculos.py
Testes unitários do motor de cálculo financeiro.

Execute com:
    python -m pytest testes/ -v

Os testes validam:
  - Fórmula Markup Divisor com diferentes cenários reais
  - Distribuição correta do DAS-MEI
  - Comportamento com diferentes meios de pagamento
  - Rejeição de entradas inválidas
  - Integridade matemática (soma das partes == preço total)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from calculos_financeiros import (
    ParametrosEntrada,
    calcular_preco_por_markup,
    _calcular_das_unitario,
    _arredondar,
)
from config import DAS_MEI_2025, TAXAS_MAQUININHA_PADRAO


# -------------------------------------------------------------------
# Fixtures reutilizáveis
# -------------------------------------------------------------------

@pytest.fixture
def parametros_base():
    """Cenário real: vendedor de Fortaleza, produto de R$ 85, crédito à vista."""
    return ParametrosEntrada(
        custo_produto               = 85.00,
        margem_lucro_desejada       = 30.0,
        tipo_pagamento              = "credito_vista",
        despesas_fixas_percentual   = 5.0,
        vendas_mensais_estimadas    = 40,
        tipo_mei                    = "comercio",
    )


# -------------------------------------------------------------------
# Testes: DAS-MEI unitário
# -------------------------------------------------------------------

class TestDasUnitario:

    def test_das_comercio_40_vendas(self):
        das = _calcular_das_unitario("comercio", 40)
        esperado = DAS_MEI_2025["comercio"] / 40
        assert round(das, 4) == round(esperado, 4)

    def test_das_servicos(self):
        das = _calcular_das_unitario("servicos", 30)
        assert das == pytest.approx(DAS_MEI_2025["servicos"] / 30, rel=1e-4)

    def test_das_ambos(self):
        das = _calcular_das_unitario("ambos", 20)
        assert das == pytest.approx(DAS_MEI_2025["ambos"] / 20, rel=1e-4)

    def test_vendas_zero_levanta_erro(self):
        with pytest.raises(ValueError, match="maior que zero"):
            _calcular_das_unitario("comercio", 0)

    def test_tipo_mei_invalido_levanta_erro(self):
        with pytest.raises(ValueError, match="inválido"):
            _calcular_das_unitario("industria", 50)


# -------------------------------------------------------------------
# Testes: Cálculo de preço (Markup Divisor)
# -------------------------------------------------------------------

class TestCalculoPreco:

    def test_preco_maior_que_custo(self, parametros_base):
        resultado = calcular_preco_por_markup(parametros_base)
        assert resultado.preco_venda_sugerido > parametros_base.custo_produto

    def test_lucro_real_percentual_correto(self, parametros_base):
        resultado = calcular_preco_por_markup(parametros_base)
        assert resultado.lucro_real_percentual == pytest.approx(30.0, rel=1e-2)

    def test_integridade_matematica(self, parametros_base):
        """
        A soma de todos os componentes deve ser igual ao preço de venda.
        custo + DAS + maquininha + desp_fixas + lucro == preço
        """
        r = calcular_preco_por_markup(parametros_base)
        soma = (
            r.custo_produto
            + r.das_mei_valor_unitario
            + r.taxa_maquininha_valor
            + r.despesas_fixas_valor
            + r.lucro_real_valor
        )
        assert soma == pytest.approx(r.preco_venda_sugerido, rel=1e-2)

    def test_pix_preco_menor_que_credito(self):
        """PIX (0%) deve gerar preço menor que crédito à vista (2.99%)."""
        base = ParametrosEntrada(
            custo_produto=100.0,
            margem_lucro_desejada=20.0,
            tipo_pagamento="pix",
            vendas_mensais_estimadas=50,
        )
        resultado_pix     = calcular_preco_por_markup(base)
        base.tipo_pagamento = "credito_vista"
        resultado_credito = calcular_preco_por_markup(base)
        assert resultado_pix.preco_venda_sugerido < resultado_credito.preco_venda_sugerido

    def test_margem_contribuicao_cobre_fixas_e_lucro(self, parametros_base):
        """
        IMC deve ser igual a despesas_fixas% + margem_lucro% (propriedade da MC).
        """
        r = calcular_preco_por_markup(parametros_base)
        imc_esperada = parametros_base.despesas_fixas_percentual + parametros_base.margem_lucro_desejada
        assert r.indice_margem_contribuicao == pytest.approx(imc_esperada, rel=1e-2)

    def test_override_taxa_maquininha(self):
        """Override manual da taxa deve ser usado no lugar da taxa padrão."""
        params = ParametrosEntrada(
            custo_produto=100.0,
            margem_lucro_desejada=20.0,
            tipo_pagamento="credito_vista",
            taxa_maquininha_override=1.0,  # força 1% em vez de 2.99%
            vendas_mensais_estimadas=50,
        )
        resultado = calcular_preco_por_markup(params)
        assert resultado.taxa_maquininha_percentual == 1.0

    def test_taxas_externas_do_sheets(self):
        """Taxas vindas do Sheets devem sobrescrever os padrões."""
        taxas_sheets = {"credito_vista": 2.50}  # taxa negociada menor
        params = ParametrosEntrada(
            custo_produto=100.0,
            margem_lucro_desejada=20.0,
            tipo_pagamento="credito_vista",
            vendas_mensais_estimadas=50,
        )
        resultado = calcular_preco_por_markup(params, taxas_externas=taxas_sheets)
        assert resultado.taxa_maquininha_percentual == 2.50

    def test_mais_vendas_mensais_reduz_das_unitario(self):
        """Quanto mais unidades vendidas, menor o DAS por unidade."""
        def calcular_das_no_preco(qtd):
            p = ParametrosEntrada(
                custo_produto=50.0,
                margem_lucro_desejada=20.0,
                tipo_pagamento="pix",
                vendas_mensais_estimadas=qtd,
            )
            return calcular_preco_por_markup(p).das_mei_valor_unitario

        assert calcular_das_no_preco(10) > calcular_das_no_preco(100)


# -------------------------------------------------------------------
# Testes: Validação de entradas inválidas
# -------------------------------------------------------------------

class TestValidacaoEntrada:

    def test_custo_zero_levanta_erro(self):
        with pytest.raises(ValueError, match="positivo"):
            calcular_preco_por_markup(ParametrosEntrada(
                custo_produto=0.0, margem_lucro_desejada=20.0,
                tipo_pagamento="pix", vendas_mensais_estimadas=50,
            ))

    def test_margem_100_levanta_erro(self):
        with pytest.raises(ValueError):
            calcular_preco_por_markup(ParametrosEntrada(
                custo_produto=100.0, margem_lucro_desejada=100.0,
                tipo_pagamento="pix", vendas_mensais_estimadas=50,
            ))

    def test_soma_percentuais_acima_100_levanta_erro(self):
        """Taxa + fixas + margem >= 100% deve ser rejeitado."""
        with pytest.raises(ValueError, match="100%"):
            calcular_preco_por_markup(ParametrosEntrada(
                custo_produto=100.0,
                margem_lucro_desejada=60.0,
                tipo_pagamento="credito_7a12",   # 4.99%
                despesas_fixas_percentual=40.0,  # total = 60+4.99+40 = 104.99%
                vendas_mensais_estimadas=50,
            ))

    def test_tipo_pagamento_invalido_levanta_erro(self):
        with pytest.raises(ValueError, match="não reconhecido"):
            calcular_preco_por_markup(ParametrosEntrada(
                custo_produto=100.0, margem_lucro_desejada=20.0,
                tipo_pagamento="boleto",  # não existe
                vendas_mensais_estimadas=50,
            ))


# -------------------------------------------------------------------
# Teste de validação manual (Matriz de Precisão do projeto)
# -------------------------------------------------------------------

class TestMatrizPrecisao:
    """
    Compara resultados do sistema com cálculo manual documentado.
    Estes são os casos que serão apresentados na Semana 7 (homologação).
    """

    def test_caso_referencia_documentado(self):
        """
        Caso documentado:
          Custo R$ 85 | Margem 30% | Crédito Vista | Fixas 5% | 40 vendas/mês
          DAS unitário = 76.90 / 40 = 1.9225
          Markup divisor = 1 - (2.99 + 5 + 30)/100 = 0.6201
          Preço = (85 + 1.9225) / 0.6201 ≈ R$ 140.17
        """
        params = ParametrosEntrada(
            custo_produto=85.0,
            margem_lucro_desejada=30.0,
            tipo_pagamento="credito_vista",
            despesas_fixas_percentual=5.0,
            vendas_mensais_estimadas=40,
            tipo_mei="comercio",
        )
        r = calcular_preco_por_markup(params)

        assert r.preco_venda_sugerido == pytest.approx(140.17, rel=0.005)
        assert r.lucro_real_valor     == pytest.approx(42.05, rel=0.01)
        assert r.markup_divisor       == pytest.approx(0.6201, rel=0.001)
