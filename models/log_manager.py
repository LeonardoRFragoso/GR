import sqlite3
from datetime import datetime
from models.database import get_db_connection

def registrar_log(usuario, nivel, acao, descricao, registro_id=None, detalhes=None, valor_anterior=None, valor_novo=None, objeto_tipo=None, ip=None):
    """
    Função centralizada para registrar logs no sistema.
    Todos os logs serão armazenados na tabela logs_unificados.
    
    Parâmetros:
    - usuario: Nome do usuário que realizou a ação
    - nivel: Nível do usuário (admin, comum, gr, sistema)
    - acao: Tipo de ação realizada (LOGIN, LOGOUT, EDIÇÃO, CRIAÇÃO, etc)
    - descricao: Descrição detalhada da ação
    - registro_id: ID do registro afetado (opcional)
    - detalhes: Detalhes adicionais (opcional)
    - valor_anterior: Valor anterior em caso de alteração (opcional)
    - valor_novo: Novo valor em caso de alteração (opcional)
    - objeto_tipo: Tipo de objeto afetado (opcional)
    - ip: Endereço IP do usuário (opcional)
    
    Retorna:
    - True se o log foi registrado com sucesso
    - False em caso de erro
    """
    try:
        data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela logs_unificados existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logs_unificados'")
            if not cursor.fetchone():
                # Tentar executar o script de migração
                try:
                    from scripts.unificar_logs import criar_tabela_unificada
                    criar_tabela_unificada()
                except ImportError:
                    # Criar a tabela simplificada se o script não estiver disponível
                    cursor.execute("""
                        CREATE TABLE logs_unificados (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            data_hora TEXT,
                            usuario TEXT,
                            nivel TEXT,
                            acao TEXT NOT NULL,
                            descricao TEXT,
                            detalhes TEXT,
                            registro_id INTEGER,
                            ip TEXT,
                            origem TEXT,
                            objeto_tipo TEXT,
                            valor_anterior TEXT,
                            valor_novo TEXT
                        )
                    """)
                    conn.commit()
            
            # Inserir o log na tabela unificada
            cursor.execute("""
                INSERT INTO logs_unificados (
                    data_hora, usuario, nivel, acao, descricao, detalhes, 
                    registro_id, ip, origem, objeto_tipo, valor_anterior, valor_novo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'api', ?, ?, ?)
            """, (
                data_hora, usuario, nivel, acao, descricao, detalhes,
                registro_id, ip, objeto_tipo, valor_anterior, valor_novo
            ))
            
            conn.commit()
            return True
    except Exception as e:
        print(f"Erro ao registrar log: {e}")
        return False

def obter_logs(filtros=None, pagina=1, itens_por_pagina=50):
    """
    Obtém logs do sistema com base nos filtros especificados.
    
    Parâmetros:
    - filtros: Dicionário com filtros a serem aplicados (opcional)
    - pagina: Número da página para paginação (padrão: 1)
    - itens_por_pagina: Número de itens por página (padrão: 50)
    
    Retorna:
    - Lista de logs, total de logs e total de páginas
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela logs_unificados existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logs_unificados'")
            if not cursor.fetchone():
                # Tentar executar a migração
                try:
                    from scripts.unificar_logs import executar_migracao
                    executar_migracao()
                except ImportError:
                    print("Módulo de migração não encontrado")
                    return [], 0, 0
            
            # Construir a consulta base
            query = "SELECT * FROM logs_unificados WHERE 1=1"
            params = []
            
            # Aplicar filtros
            if filtros:
                if 'usuario' in filtros and filtros['usuario']:
                    query += " AND usuario LIKE ?"
                    params.append(f"%{filtros['usuario']}%")
                
                if 'nivel' in filtros and filtros['nivel']:
                    query += " AND nivel = ?"
                    params.append(filtros['nivel'])
                
                if 'acao' in filtros and filtros['acao']:
                    query += " AND acao LIKE ?"
                    params.append(f"%{filtros['acao']}%")
                
                if 'data_inicio' in filtros and filtros['data_inicio']:
                    query += " AND data_hora >= ?"
                    params.append(filtros['data_inicio'])
                
                if 'data_fim' in filtros and filtros['data_fim']:
                    query += " AND data_hora <= ?"
                    params.append(filtros['data_fim'] + " 23:59:59")
                
                if 'registro_id' in filtros and filtros['registro_id']:
                    query += " AND registro_id = ?"
                    params.append(filtros['registro_id'])
            
            # Contar total de registros
            count_query = query.replace("SELECT *", "SELECT COUNT(*) as total")
            cursor.execute(count_query, params)
            total = cursor.fetchone()['total']
            
            # Calcular total de páginas
            total_paginas = (total + itens_por_pagina - 1) // itens_por_pagina if total > 0 else 1
            
            # Adicionar ordenação e paginação
            query += " ORDER BY data_hora DESC LIMIT ? OFFSET ?"
            params.append(itens_por_pagina)
            params.append((pagina - 1) * itens_por_pagina)
            
            # Executar consulta
            cursor.execute(query, params)
            logs = [dict(row) for row in cursor.fetchall()]
            
            return logs, total, total_paginas
    except Exception as e:
        print(f"Erro ao obter logs: {e}")
        return [], 0, 0
