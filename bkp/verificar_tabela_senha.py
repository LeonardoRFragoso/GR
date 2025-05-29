import sqlite3
import os

def verificar_tabela():
    try:
        # Conectar ao banco de dados
        conn = sqlite3.connect('usuarios.db')
        cursor = conn.cursor()
        
        # Verificar se a tabela solicitacoes_senha existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitacoes_senha'")
        if cursor.fetchone():
            print("Tabela solicitacoes_senha existe!")
            
            # Verificar a estrutura da tabela
            cursor.execute("PRAGMA table_info(solicitacoes_senha)")
            colunas = cursor.fetchall()
            print("\nEstrutura da tabela solicitacoes_senha:")
            for coluna in colunas:
                print(f"  {coluna[1]} ({coluna[2]})")
        else:
            print("Tabela solicitacoes_senha NÃO existe!")
            
            # Criar a tabela se não existir
            print("\nCriando tabela solicitacoes_senha...")
            cursor.execute('''
                CREATE TABLE solicitacoes_senha (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    status TEXT NOT NULL,
                    data_solicitacao TIMESTAMP NOT NULL,
                    data_processamento TIMESTAMP,
                    processado_por TEXT,
                    observacao TEXT
                )
            ''')
            conn.commit()
            print("Tabela solicitacoes_senha criada com sucesso!")
        
        conn.close()
    except Exception as e:
        print(f"Erro ao verificar tabela: {e}")

if __name__ == "__main__":
    verificar_tabela()
