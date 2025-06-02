import sqlite3
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_database():
    """Atualiza o banco de dados adicionando colunas para controle de visualização de alterações."""
    try:
        # Caminho do banco de dados
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usuarios.db')
        
        # Verificar se o banco de dados existe
        if not os.path.exists(db_path):
            logger.error(f"Banco de dados não encontrado em: {db_path}")
            return False
        
        # Conectar ao banco de dados
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar se as colunas já existem
        cursor.execute("PRAGMA table_info(historico)")
        colunas = [info[1] for info in cursor.fetchall()]
        
        # Adicionar coluna 'verificado' se não existir
        if 'verificado' not in colunas:
            logger.info("Adicionando coluna 'verificado' à tabela historico")
            cursor.execute("ALTER TABLE historico ADD COLUMN verificado INTEGER DEFAULT 0")
        else:
            logger.info("Coluna 'verificado' já existe na tabela historico")
        
        # Adicionar coluna 'data_verificacao' se não existir
        if 'data_verificacao' not in colunas:
            logger.info("Adicionando coluna 'data_verificacao' à tabela historico")
            cursor.execute("ALTER TABLE historico ADD COLUMN data_verificacao TEXT")
        else:
            logger.info("Coluna 'data_verificacao' já existe na tabela historico")
        
        # Commit e fechar conexão
        conn.commit()
        conn.close()
        
        logger.info("Banco de dados atualizado com sucesso!")
        return True
    
    except Exception as e:
        logger.error(f"Erro ao atualizar o banco de dados: {e}")
        return False

if __name__ == "__main__":
    update_database()
