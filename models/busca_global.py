from models.database import get_db_connection

def busca_global(termo, limit=100, offset=0):
    """
    Realiza uma busca global em múltiplos campos da tabela de registros
    
    Args:
        termo: Termo de busca a ser encontrado em qualquer coluna relevante
        limit: Limite de resultados a retornar
        offset: Offset para paginação
        
    Returns:
        Lista de registros que correspondem à busca
    """
    try:
        if not termo or termo.strip() == '':
            return []
            
        termo = termo.strip()
        base_query = "SELECT * FROM registros WHERE "
        
        # Lista de campos para buscar - USANDO NOMES CORRETOS DAS COLUNAS DO BANCO DE DADOS
        campos_busca = [
            'id', 'usuario', 'placa', 'motorista', 'cpf', 'mot_loc',
            'carreta', 'carreta_loc', 'cliente', 'loc_cliente',
            'container_1', 'container_2', 'numero_sm', 'numero_ae',
            'arquivo', 'data_registro', 'status_sm'
        ]
        
        # Criar condições para cada campo
        search_conditions = []
        params = []
        
        for campo in campos_busca:
            search_conditions.append(f"{campo} LIKE ?")
            params.append(f"%{termo}%")
            
        # Combinar condições com OR
        query = base_query + "(" + " OR ".join(search_conditions) + ") ORDER BY data_registro DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            registros = cursor.fetchall()
            return [dict(reg) for reg in registros]
            
    except Exception as e:
        print(f"Erro ao realizar busca global: {e}")
        return []
        
def contar_busca_global(termo):
    """
    Conta o número total de registros que correspondem a uma busca global
    
    Args:
        termo: Termo de busca a ser encontrado
        
    Returns:
        Número total de registros encontrados
    """
    try:
        if not termo or termo.strip() == '':
            return 0
            
        termo = termo.strip()
        base_query = "SELECT COUNT(*) FROM registros WHERE "
        
        # Lista de campos para buscar - USANDO NOMES CORRETOS DAS COLUNAS DO BANCO DE DADOS
        campos_busca = [
            'id', 'usuario', 'placa', 'motorista', 'cpf', 'mot_loc',
            'carreta', 'carreta_loc', 'cliente', 'loc_cliente',
            'container_1', 'container_2', 'numero_sm', 'numero_ae',
            'arquivo', 'data_registro', 'status_sm'
        ]
        
        # Criar condições para cada campo
        search_conditions = []
        params = []
        
        for campo in campos_busca:
            search_conditions.append(f"{campo} LIKE ?")
            params.append(f"%{termo}%")
            
        # Combinar condições com OR
        query = base_query + "(" + " OR ".join(search_conditions) + ")"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            resultado = cursor.fetchone()
            return resultado[0] if resultado else 0
            
    except Exception as e:
        print(f"Erro ao contar resultados de busca global: {e}")
        return 0
