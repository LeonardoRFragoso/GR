#!/usr/bin/env python3
"""
Script para aplicar triggers no banco de dados SQLite
Este script lê arquivos SQL e executa os comandos no banco de dados
"""

import os
import sys
import sqlite3
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Adicionar o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar a função de conexão com o banco de dados
from models.database import get_db_connection

def apply_sql_file(file_path):
    """
    Aplica os comandos SQL de um arquivo no banco de dados
    
    Args:
        file_path: Caminho para o arquivo SQL
    """
    try:
        # Ler o conteúdo do arquivo SQL
        with open(file_path, 'r') as f:
            sql_content = f.read()
        
        # Executar os comandos como um script completo
        with get_db_connection() as conn:
            try:
                # Executar o script completo
                logger.info(f"Executando script SQL de {file_path}")
                conn.executescript(sql_content)
                logger.info("Script SQL executado com sucesso")
                conn.commit()
                logger.info(f"Arquivo SQL aplicado com sucesso: {file_path}")
            except sqlite3.Error as e:
                logger.error(f"Erro ao executar script SQL: {e}")
                conn.rollback()
    
    except Exception as e:
        logger.error(f"Erro ao aplicar arquivo SQL {file_path}: {e}")
        raise

def main():
    """
    Função principal
    """
    # Diretório onde estão os arquivos SQL
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Arquivo SQL com os triggers
    trigger_file = os.path.join(script_dir, 'create_trigger_horario_previsto.sql')
    
    if os.path.exists(trigger_file):
        logger.info(f"Aplicando triggers do arquivo: {trigger_file}")
        apply_sql_file(trigger_file)
    else:
        logger.error(f"Arquivo de triggers não encontrado: {trigger_file}")

if __name__ == "__main__":
    main()
