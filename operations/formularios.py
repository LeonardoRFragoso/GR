from flask import request, flash, redirect, url_for, session
import sys
import os
from datetime import datetime
import logging

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.registros import Registro
from utils.file_utils import save_uploaded_file, allowed_file
from operations.excel import excel_processor

def processar_formulario():
    """
    Processa o formulário de registro submetido pelo usuário
    
    Returns:
        Redirecionamento para a página apropriada após o processamento
    """
    if request.method != 'POST':
        return redirect(url_for('comum.novo_registro'))
    
    # Obter o usuário da sessão
    usuario = session.get('user')
    
    # Obter dados do formulário
    dados = {}
    
    # Para cada campo do formulário, adicionar ao dicionário de dados
    for campo in excel_processor.CAMPOS_FORM:
        valor = request.form.get(campo, '')
        dados[campo] = valor
    
    # Processar o arquivo, se houver
    arquivo = None
    if 'arquivo' in request.files:
        file = request.files['arquivo']
        if file and file.filename and allowed_file(file.filename):
            arquivo = save_uploaded_file(file)
            if arquivo:
                dados['arquivo'] = arquivo
    
    # Mapear os nomes dos campos do formulário para os nomes das colunas no banco de dados
    mapeamento_campos = {
        'UNIDADE': 'placa',  # Exemplo de mapeamento, ajustar conforme necessário
        'MOTORISTA': 'motorista',
        'CPF MOTORISTA': 'cpf',
        'CAVALO 1': 'placa',
        'CARRETA 1': 'carreta',
        'CLIENTE': 'cliente',
        'ORIGEM': 'origem',
        'NUMERO SM': 'numero_sm',
        'NUMERO AE': 'numero_ae',
        'CONTAINER 1': 'container_1',
        'CONTAINER 2': 'container_2',
        'TIPO DE CARGA': 'tipo_carga',
        'STATUS DO CONTAINER': 'status_container',
        'MODALIDADE': 'modalidade',
        'GERENCIADORA': 'gerenciadora',
        'BOOKING / DI': 'booking_di',
        'PEDIDO/REFERÊNCIA': 'pedido_referencia',
        'LOTE CS': 'lote_cs',
        'ON TIME (CLIENTE)': 'on_time_cliente',
        'HORÁRIO PREVISTO DE INÍCIO': 'horario_previsto',
        'OBSERVACAO OPERACIONAL': 'observacao_operacional',
        'OBSERVAÇÃO DE GR': 'observacao_gr',
        'DESTINO INTERMEDIÁRIO': 'destino_intermediario',
        'DESTINO FINAL': 'destino_final',
        'ANEXAR NF': 'anexar_nf',
        'ANEXAR OS': 'anexar_os',
        'Nº NF': 'numero_nf',
        'SÉRIE': 'serie',
        'QUANTIDADE': 'quantidade',
        'PESO BRUTO': 'peso_bruto',
        'VALOR TOTAL DA NOTA': 'valor_total_nota'
    }
    
    # Criar um dicionário com os dados convertidos para os nomes das colunas do banco
    dados_db = {}
    for campo_form, valor in dados.items():
        if campo_form in mapeamento_campos:
            dados_db[mapeamento_campos[campo_form]] = valor
    
    # Adicionar campos extras
    dados_db['data_registro'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dados_db['usuario'] = usuario
    
    # Se arquivo foi processado, adicionar ao dicionário de dados
    if arquivo:
        dados_db['arquivo'] = arquivo
    
    # Salvar o registro no banco de dados
    registro_id = Registro.create(usuario, dados_db)
    
    if registro_id:
        flash("Registro criado com sucesso!", "success")
        logging.info(f"Usuário {usuario} criou um novo registro (ID: {registro_id})")
        return redirect(url_for('main.view_registros'))
    else:
        flash("Erro ao criar o registro. Tente novamente.", "danger")
        return redirect(url_for('comum.novo_registro'))

def validar_campos_obrigatorios(dados):
    """
    Valida se todos os campos obrigatórios foram preenchidos
    
    Args:
        dados: Dicionário com os dados do formulário
        
    Returns:
        Tupla (válido, mensagem de erro)
    """
    campos_faltantes = []
    
    for campo in excel_processor.CAMPOS_OBRIGATORIOS:
        if campo not in dados or not dados[campo]:
            campos_faltantes.append(campo)
    
    if campos_faltantes:
        return False, f"Os seguintes campos obrigatórios não foram preenchidos: {', '.join(campos_faltantes)}"
    
    return True, ""
