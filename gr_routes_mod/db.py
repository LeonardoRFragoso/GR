# db.py

import sqlite3
import logging
from constants import TABLE_REGISTROS, COL_ALTERACOES_VERIFICADAS, COL_MODIFICADO_POR

logger = logging.getLogger(__name__)

class DatabaseConnection:
    def __init__(self, database='usuarios.db'):
        self.database = database
        self.conn = None

    def __enter__(self):
        try:
            self.conn = sqlite3.connect(self.database)
            self.conn.row_factory = sqlite3.Row
            return self.conn
        except sqlite3.Error as e:
            logger.error(f"Erro ao conectar ao banco de dados {self.database}: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is not None:
                self.conn.rollback()
                logger.error(f"Transação revertida devido a erro: {exc_val}")
            else:
                try:
                    self.conn.commit()
                except Exception as e:
                    self.conn.rollback()
                    logger.error(f"Erro ao fazer commit: {e}")
            self.conn.close()

def get_db_connection(database='usuarios.db'):
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Erro ao conectar ao banco de dados {database}: {e}")
        raise

def fetchone_dict(cursor):
    row = cursor.fetchone()
    return dict((cursor.description[i][0], value) for i, value in enumerate(row)) if row else None

def verificar_criar_colunas(conn, cursor):
    cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
    colunas = [col[1] for col in cursor.fetchall()]

    if COL_ALTERACOES_VERIFICADAS not in colunas:
        try:
            cursor.execute(f"ALTER TABLE {TABLE_REGISTROS} ADD COLUMN {COL_ALTERACOES_VERIFICADAS} INTEGER DEFAULT 0")
            conn.commit()
            logger.info(f"Coluna '{COL_ALTERACOES_VERIFICADAS}' adicionada à tabela {TABLE_REGISTROS}")
            cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
            colunas = [col[1] for col in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao adicionar coluna '{COL_ALTERACOES_VERIFICADAS}': {e}")

    if COL_MODIFICADO_POR not in colunas:
        try:
            cursor.execute(f"ALTER TABLE {TABLE_REGISTROS} ADD COLUMN {COL_MODIFICADO_POR} TEXT")
            conn.commit()
            logger.info(f"Coluna '{COL_MODIFICADO_POR}' adicionada à tabela {TABLE_REGISTROS}")
            cursor.execute(f"PRAGMA table_info({TABLE_REGISTROS})")
            colunas = [col[1] for col in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao adicionar coluna '{COL_MODIFICADO_POR}': {e}")

    return colunas
