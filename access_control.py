"""
Módulo de controle de acesso para o sistema de Atendimento GR.
Define os campos, seções e permissões para cada nível de usuário.
"""

# Definição dos campos por perfil
CAMPOS_POR_NIVEL = {
    'admin': [
        'UNIDADE', 'CLIENTE', 'MOTORISTA', 'CPF MOTORISTA', 'CAVALO 1', 'CARRETA 1', 'CARRETA 2',
        'CONTAINER 1', 'CONTAINER 2', 'TIPO DE CARGA', 'STATUS CONTAINER', 'MODALIDADE',
        'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'HORÁRIO PREVISTO DE INÍCIO', 'ON TIME (CLIENTE)',
        'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'LOTE CS', 'Nº NF', 'SÉRIE', 'QUANTIDADE', 
        'PESO BRUTO', 'VALOR TOTAL DA NOTA', 'observacao_operacional',
        'OBSERVAÇÃO DE GR', 'NUMERO SM', 'NÚMERO AE', 'DATA SM', 'DATA AE', 'STATUS SM',
        'SLA SM', 'SLA AE', 'GERENCIADORA', 'ANEXAR NF', 'ANEXAR OS', 'ANEXAR AGENDAMENTO'
    ],
    'gr': [
        'CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
        'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
        'HORÁRIO PREVISTO DE INÍCIO', 'observacao_operacional', 'NUMERO SM', 'NÚMERO AE',
        'STATUS CONTAINER', 'MODALIDADE', 'MOTORISTA', 'CPF MOTORISTA', 'CAVALO 1', 'CARRETA 1', 'CARRETA 2',
        'TIPO DE CARGA', 'DATA AE', 'DATA SM', 'OBSERVAÇÃO DE GR', 'SLA SM', 'SLA AE', 'STATUS SM', 'GERENCIADORA'
    ],
    'comum': [
        'CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
        'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
        'HORÁRIO PREVISTO DE INÍCIO', 'observacao_operacional', 'NUMERO SM', 'NÚMERO AE',
        'STATUS CONTAINER', 'MODALIDADE'
    ]
}

# Seções visíveis por perfil
SECOES_VISIVEIS = {
    'admin': ['unidade', 'cliente', 'transporte', 'cargas', 'observacoes', 'documentos', 'gr'],
    'gr': ['unidade', 'cliente', 'transporte', 'cargas', 'gr', 'observacoes'],
    'comum': ['unidade', 'cliente', 'transporte', 'cargas', 'observacoes', 'documentos']
}

# Campos somente leitura por perfil
CAMPOS_SOMENTE_LEITURA = {
    'admin': [],
    'gr': [
        'CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI', 'CONTAINER 1', 'CONTAINER 2', 
        'LOTE CS', 'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'ON TIME (CLIENTE)', 
        'HORÁRIO PREVISTO DE INÍCIO', 'observacao_operacional', 'MOTORISTA', 'CPF MOTORISTA',
        'STATUS CONTAINER', 'TIPO DE CARGA', 'MODALIDADE', 'Nº NF', 'SÉRIE', 'QUANTIDADE',
        'PESO BRUTO', 'VALOR TOTAL DA NOTA', 'ANEXAR NF', 'ANEXAR OS', 'ANEXAR AGENDAMENTO'
    ],
    'comum': [
        'OBSERVAÇÃO DE GR', 'STATUS SM', 'SLA SM', 'SLA AE', 'GERENCIADORA'
    ]
}

# Campos ocultos por perfil
CAMPOS_OCULTOS = {
    'admin': [],
    'gr': [
        'TIPO DE CARGA', 'MODALIDADE', 
        'Nº NF', 'SÉRIE', 'QUANTIDADE', 'PESO BRUTO', 'VALOR TOTAL DA NOTA',
        'ANEXAR NF', 'ANEXAR OS', 'ANEXAR AGENDAMENTO'
    ],
    'comum': [
        'OBSERVAÇÃO DE GR', 'STATUS SM', 'SLA SM', 'SLA AE', 'GERENCIADORA'
    ]
}

# Mapeamento padronizado entre campos do banco e campos do formulário
CAMPO_MAPPING = {
    # Campos exatos conforme a estrutura da tabela registros
    'unidade': 'UNIDADE',
    'cliente': 'CLIENTE',
    'motorista': 'MOTORISTA',
    'cpf': 'CPF MOTORISTA',
    'placa': 'CAVALO',  # Campo CAVALO do formulário deve ser salvo na coluna placa
    'carreta1': 'CARRETA 1',
    'carreta2': 'CARRETA 2',
    'container_1': 'CONTAINER 1',
    'container_2': 'CONTAINER 2',
    'tipo_carga': 'TIPO DE CARGA',
    'status_container': 'STATUS CONTAINER',
    'modalidade': 'MODALIDADE',
    'destino_intermediario': 'DESTINO INTERMEDIÁRIO',
    'destino_final': 'DESTINO FINAL',
    'horario_previsto': 'HORÁRIO PREVISTO DE INÍCIO',
    'on_time_cliente': 'ON TIME (CLIENTE)',
    'pedido_referencia': 'PEDIDO/REFERÊNCIA',
    'booking_di': 'BOOKING / DI',
    'lote_cs': 'LOTE CS',
    'numero_nf': 'Nº NF',
    'origem': 'ORIGEM',
    'data_registro': 'DATA',
    'serie': 'SÉRIE',
    'quantidade': 'QUANTIDADE',
    'peso_bruto': 'PESO BRUTO',
    'valor_total_nota': 'VALOR TOTAL DA NOTA',
    'anexar_nf': 'ANEXAR NF',
    'anexar_os': 'ANEXAR OS',
    'anexar_agendamento': 'ANEXAR AGENDAMENTO',
    'observacao_operacional': 'observacao_operacional',
    'observacao_gr': 'OBSERVAÇÃO DE GR',
    'numero_sm': 'NUMERO SM',
    'numero_ae': 'NÚMERO AE',
    'data_sm': 'DATA SM',
    'data_ae': 'DATA AE',
    'status_sm': 'STATUS SM',
    'sla_sm': 'SLA SM',
    'sla_ae': 'SLA AE',
    'gerenciadora': 'GERENCIADORA',
    'arquivo_nf_nome': 'ARQUIVO NF NOME',
    'arquivo_os_nome': 'ARQUIVO OS NOME',
    'arquivo_agendamento_nome': 'ARQUIVO AGENDAMENTO NOME',
    'excluido': 'EXCLUIDO',
    # Campos adicionais que estavam faltando no mapeamento
    'mot_loc': 'MOTORISTA LOCAÇÃO',
    'carreta': 'CARRETA',  # Coluna adicional além de carreta1 e carreta2
    'carreta_loc': 'CARRETA LOCAÇÃO',
    'loc_cliente': 'LOCALIZAÇÃO CLIENTE',
    'arquivo': 'ARQUIVO',  # Coluna genérica para arquivos
    'alteracoes_verificadas': 'ALTERAÇÕES VERIFICADAS'
}

# Mapeamento inverso (do formulário para o banco)
# Reconstruir o mapeamento inverso para garantir que está atualizado
CAMPO_MAPPING_INVERSO = {v: k for k, v in CAMPO_MAPPING.items()}

# Ícones para cada seção
ICONES_SECOES = {
    'unidade': 'building',
    'cliente': 'user',
    'transporte': 'truck',
    'cargas': 'box',
    'observacoes': 'comment',
    'documentos': 'file-alt',
    'gr': 'clipboard-list'
}

# Títulos para cada seção
TITULOS_SECOES = {
    'unidade': 'Dados da Unidade',
    'cliente': 'Dados do Cliente',
    'transporte': 'Dados da Operação',
    'cargas': 'Dados da Carga',
    'observacoes': 'Observações',
    'documentos': 'Anexos',
    'gr': 'Dados de GR'
}

# Campos por seção
CAMPOS_SECAO = {
    'unidade': ['UNIDADE'],
    'cliente': ['CLIENTE', 'PEDIDO/REFERÊNCIA', 'BOOKING / DI'],
    'transporte': ['MOTORISTA', 'CPF MOTORISTA', 'CAVALO', 'CARRETA 1', 'CARRETA 2', 'TIPO DE CARGA', 'HORÁRIO PREVISTO DE INÍCIO', 'ON TIME (CLIENTE)'],
    'cargas': [
        'CONTAINER 1', 'CONTAINER 2', 'STATUS CONTAINER', 'MODALIDADE',
        'ORIGEM', 'DESTINO INTERMEDIÁRIO', 'DESTINO FINAL', 'LOTE CS'
    ],
    'observacoes': ['observacao_operacional'],
    'documentos': ['ANEXAR NF', 'ANEXAR OS', 'ANEXAR AGENDAMENTO'],
    'gr': [
        'NUMERO SM', 'DATA SM', 'STATUS SM', 'NÚMERO AE', 'DATA AE', 
        'OBSERVAÇÃO DE GR', 'SLA SM', 'SLA AE', 'GERENCIADORA'
    ]
}

def campo_visivel(campo, nivel):
    """
    Verifica se um campo é visível para um perfil.
    
    Args:
        campo: Nome do campo
        nivel: Nível do usuário (admin, gr, comum)
        
    Returns:
        True se o campo for visível, False caso contrário
    """
    if nivel == 'admin':
        return True
    
    if campo in CAMPOS_OCULTOS.get(nivel, []):
        return False
    
    return campo in CAMPOS_POR_NIVEL.get(nivel, CAMPOS_POR_NIVEL['comum'])

def campo_editavel(campo, nivel):
    """
    Verifica se um campo é editável para um perfil.
    
    Args:
        campo: Nome do campo
        nivel: Nível do usuário (admin, gr, comum)
        
    Returns:
        True se o campo for editável, False caso contrário
    """
    if nivel == 'admin':
        return True
    
    return campo not in CAMPOS_SOMENTE_LEITURA.get(nivel, [])

def mapear_db_para_campo(campo_db):
    """
    Mapeia um nome de campo do banco de dados para o nome no formulário.
    
    Args:
        campo_db: Nome do campo no banco de dados
        
    Returns:
        Nome do campo no formulário ou o próprio campo_db se não houver mapeamento
    """
    return CAMPO_MAPPING.get(campo_db, campo_db)

def mapear_campo_para_db(campo_form):
    """
    Mapeia um nome de campo do formulário para o nome no banco de dados.
    
    Args:
        campo_form: Nome do campo no formulário
        
    Returns:
        Nome do campo no banco de dados ou o próprio campo_form se não houver mapeamento
    """
    return CAMPO_MAPPING_INVERSO.get(campo_form, campo_form)

def get_campos_permitidos(nivel):
    """
    Retorna a lista de campos permitidos para um nível de usuário.
    
    Args:
        nivel: Nível do usuário (admin, gr, comum)
        
    Returns:
        Lista de campos permitidos
    """
    return CAMPOS_POR_NIVEL.get(nivel, CAMPOS_POR_NIVEL['comum'])

def get_secoes_visiveis(nivel):
    """
    Retorna a lista de seções visíveis para um nível de usuário.
    
    Args:
        nivel: Nível do usuário (admin, gr, comum)
        
    Returns:
        Lista de seções visíveis
    """
    return SECOES_VISIVEIS.get(nivel, SECOES_VISIVEIS['comum'])

