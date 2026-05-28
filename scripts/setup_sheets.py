"""
setup_sheets.py
Configura a planilha Google Sheets automaticamente.

Execute UMA VEZ após configurar o .env e colocar o service_account.json:
    python scripts/setup_sheets.py

O que este script faz:
  1. Conecta na planilha pelo ID do .env
  2. Cria a aba 'taxas_maquininha' com taxas de mercado 2025 pré-preenchidas
  3. Cria a aba 'historico_calculos' com os cabeçalhos corretos
  4. Confirma que tudo está pronto para uso
"""

import os
import sys

# Garante que o script encontra os módulos do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def main():
    sheets_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json")

    if not sheets_id:
        print("❌  GOOGLE_SHEETS_ID não definido no arquivo .env")
        print("    Abra o .env e cole o ID da sua planilha Google Sheets.")
        sys.exit(1)

    if not os.path.exists(creds_path):
        print(f"❌  Arquivo de credenciais não encontrado: {creds_path}")
        print("    Baixe o JSON da conta de serviço no Google Cloud Console")
        print("    e salve em credentials/service_account.json")
        sys.exit(1)

    print("🔌  Conectando ao Google Sheets...")

    from database_sheets import RepositorioSheets
    repo = RepositorioSheets(id_planilha=sheets_id, caminho_credenciais=creds_path)

    print("📋  Criando abas e populando taxas...")
    sucesso = repo.inicializar_abas()

    if sucesso:
        print()
        print("✅  Planilha configurada com sucesso!")
        print()
        print("   Abas criadas:")
        print("   • taxas_maquininha  — taxas pré-preenchidas (mercado 2025)")
        print("   • historico_calculos — pronta para receber logs")
        print()
        print("   Próximo passo: inicie o servidor")
        print("   uvicorn main:app --host 0.0.0.0 --port 8000")
    else:
        print()
        print("❌  Falha ao configurar a planilha.")
        print("   Verifique se:")
        print("   1. O GOOGLE_SHEETS_ID está correto")
        print("   2. A planilha foi compartilhada com o e-mail da conta de serviço")
        print("   3. As APIs Google Sheets e Drive estão ativadas no Google Cloud")
        sys.exit(1)


if __name__ == "__main__":
    main()
