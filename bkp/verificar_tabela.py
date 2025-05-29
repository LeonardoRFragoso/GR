import sqlite3
import os

def verificar_tabela():
    try:
        # Conectar ao banco de dados
        conn = sqlite3.connect('usuarios.db')
        cursor = conn.cursor()
        
        # Verificar se a tabela solicitacoes_acesso existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_acesso'")
        if cursor.fetchone():
            print("Tabela solicitacoes_acesso existe!")
            
            # Verificar a estrutura da tabela
            cursor.execute("PRAGMA table_info(solicitacoes_acesso)")
            colunas = cursor.fetchall()
            print("\nEstrutura da tabela solicitacoes_acesso:")
            for coluna in colunas:
                print(f"  {coluna[1]} ({coluna[2]})")
        else:
            print("Tabela solicitacoes_acesso NÃO existe!")
            
            # Criar a tabela se não existir
            print("\nCriando tabela solicitacoes_acesso...")
            cursor.execute('''
                CREATE TABLE solicitacoes_acesso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    setor TEXT NOT NULL,
                    justificativa TEXT NOT NULL,
                    status TEXT NOT NULL,
                    data_solicitacao TIMESTAMP NOT NULL,
                    data_processamento TIMESTAMP,
                    processado_por TEXT,
                    observacao TEXT
                )
            ''')
            conn.commit()
            print("Tabela solicitacoes_acesso criada com sucesso!")
        
        conn.close()
    except Exception as e:
        print(f"Erro ao verificar tabela: {e}")

if __name__ == "__main__":
    verificar_tabela()
