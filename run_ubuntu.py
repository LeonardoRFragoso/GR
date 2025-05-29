#!/usr/bin/env python3
"""
Script para executar a aplicação Flask no ambiente Ubuntu
Este arquivo simplifica a execução do aplicativo na porta 8520
Compatível com execução como serviço systemd
"""

import os
import sys
import logging
import platform
import time
import traceback
from datetime import datetime

# Configurar diretórios e arquivos para compatibilidade com Linux
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configurar logging específico para Ubuntu
log_dir = os.path.join(BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'ubuntu_app.log')
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Adicionar handler para stdout para ver logs no console e no journalctl
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# Verificar se estamos em um ambiente Linux
is_linux = platform.system().lower() == 'linux'

# Configurando para porta 8520 no Ubuntu
HOST = '0.0.0.0'  # Aceita conexões de qualquer IP
PORT = 8520     # Porta padrão para o ambiente Ubuntu
DEBUG = False   # Desativar modo debug em produção

# Garantir que o diretório de uploads existe
uploads_dir = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(uploads_dir, exist_ok=True)

logging.info(f"Iniciando aplicação Atendimento GR em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logging.info(f"Diretório base: {BASE_DIR}")

# Importar a aplicação somente após configurar o ambiente
try:
    logging.info("Importando aplicação de new_app.py")
    from new_app import app
    logging.info("Aplicação importada com sucesso")
except Exception as e:
    logging.error(f"Erro ao importar a aplicação: {e}")
    logging.error(traceback.format_exc())
    sys.exit(1)

# Verificar e configurar o ambiente Linux
def setup_linux_environment():
    """Configura o ambiente Linux para execução da aplicação.
    
    Verifica e ajusta permissões, cria diretórios necessários e valida arquivos importantes.
    """
    try:
        logging.info("Iniciando configuração do ambiente...")
        
        # Verificar sistema operacional
        if not is_linux:
            logging.warning("Não estamos em um ambiente Linux. Algumas configurações podem não funcionar corretamente.")
            return
            
        # Verificar permissões do banco de dados
        db_files = ['usuarios.db', 'database.db']
        for db_file in db_files:
            db_path = os.path.join(BASE_DIR, db_file)
            if os.path.exists(db_path):
                # Garantir que o arquivo de banco de dados tem permissões adequadas
                os.chmod(db_path, 0o664)  # rw-rw-r--
                logging.info(f"Permissões do banco de dados ajustadas: {db_path}")
            else:
                logging.warning(f"Banco de dados não encontrado em: {db_path}")
        
        # Verificar e criar diretórios necessários com permissões adequadas
        diretorios = [
            os.path.join(BASE_DIR, 'static'),
            os.path.join(BASE_DIR, 'static', 'uploads'),
            os.path.join(BASE_DIR, 'static', 'uploads', 'nf'),
            os.path.join(BASE_DIR, 'static', 'uploads', 'os'),
            os.path.join(BASE_DIR, 'static', 'uploads', 'agendamento'),
            os.path.join(BASE_DIR, 'logs'),
            os.path.join(BASE_DIR, 'static', 'assets')
        ]
        
        for diretorio in diretorios:
            if not os.path.exists(diretorio):
                os.makedirs(diretorio, mode=0o775, exist_ok=True)
                logging.info(f"Diretório criado: {diretorio}")
            
            # Ajustar permissões mesmo se o diretório já existir
            try:
                os.chmod(diretorio, 0o775)  # rwxrwxr-x
                logging.info(f"Permissões ajustadas para: {diretorio}")
            except Exception as e:
                logging.warning(f"Não foi possível ajustar permissões para {diretorio}: {e}")
        
        # Verificar permissões do arquivo de log
        log_file = os.path.join(log_dir, 'ubuntu_app.log')
        if os.path.exists(log_file):
            try:
                os.chmod(log_file, 0o664)  # rw-rw-r--
                logging.info(f"Permissões do arquivo de log ajustadas: {log_file}")
            except Exception as e:
                logging.warning(f"Não foi possível ajustar permissões do arquivo de log: {e}")
        
        # Verificar se o arquivo Excel existe
        excel_path = os.path.join(BASE_DIR, 'DADOS.xlsx')
        if not os.path.exists(excel_path):
            logging.warning(f"Arquivo Excel não encontrado: {excel_path}")
            logging.warning("O aplicativo pode não funcionar corretamente sem este arquivo.")
        else:
            logging.info(f"Arquivo Excel encontrado: {excel_path}")
            
        logging.info("Configuração do ambiente concluída com sucesso")
        return True
    
    except Exception as e:
        logging.error(f"Erro ao configurar ambiente Linux: {e}")
        logging.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    try:
        # Registrar início da aplicação
        logging.info("=== Iniciando Atendimento GR - Servidor Ubuntu ===")
        
        # Configurar o ambiente Linux
        if not setup_linux_environment():
            logging.error("Falha na configuração do ambiente. Verificando se é possível continuar...")
        
        # Verificar se o arquivo Excel existe
        excel_path = os.path.join(BASE_DIR, 'DADOS.xlsx')
        if not os.path.exists(excel_path):
            logging.warning(f"Arquivo Excel não encontrado em: {excel_path}")
            logging.warning("O aplicativo pode não funcionar corretamente sem este arquivo.")
        else:
            logging.info(f"Arquivo Excel encontrado: {excel_path}")
        
        # Verificar se estamos rodando como serviço ou em terminal interativo
        is_interactive = sys.stdout.isatty()
        
        if is_interactive:
            # Mensagens para terminal interativo
            print(f"\n=== Atendimento GR - Servidor Ubuntu ===")
            print(f"Iniciando servidor em http://{HOST}:{PORT}/")
            print(f"Logs sendo gravados em: {log_file}")
            print(f"Diretório de uploads: {uploads_dir}")
            print("Pressione CTRL+C para encerrar o servidor\n")
        
        # Registrar informações importantes nos logs
        logging.info(f"Iniciando servidor em http://{HOST}:{PORT}/")
        logging.info(f"Diretório de uploads: {uploads_dir}")
        
        # Iniciar o servidor Flask
        logging.info("Iniciando servidor Flask...")
        app.run(host=HOST, port=PORT, debug=DEBUG)
        
    except KeyboardInterrupt:
        logging.info("Servidor encerrado pelo usuário.")
        if sys.stdout.isatty():
            print("\nServidor encerrado pelo usuário.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Erro fatal ao iniciar o servidor: {e}")
        logging.error(traceback.format_exc())
        if sys.stdout.isatty():
            print(f"\nErro ao iniciar o servidor: {e}")
        sys.exit(1)

