from flask import request, session, flash
import sqlite3
import os
import json
import time
import logging
import sys
import traceback
from datetime import datetime, timedelta
from models.historico import Historico
from access_control import mapear_db_para_campo

# Adiciona o diretório principal ao path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import get_db_connection
from utils.file_utils import save_uploaded_file, allowed_file

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def processar_edicao_registro_direto(registro_id):
    """
    Versão consolidada e otimizada para processar a edição de um registro diretamente
    com detecção adequada de alterações em campos importantes.
    
    Esta função detecta quando um usuário comum edita um registro que já possui SM ou AE,
    e marca essas alterações para verificação pelo GR atualizando os campos data_modificacao
    e alteracoes_verificadas.
    
    Esta função também garante que os campos 'horario_previsto' e 'on_time_cliente' sejam
    preservados mesmo quando não são alterados explicitamente no formulário.
    
    Args:
        registro_id: ID do registro a ser editado
        
    Returns:
        True se a edição foi bem-sucedida, False caso contrário
    """
    print(f"\n\n=== PROCESSANDO EDIÇÃO DIRETA PARA REGISTRO {registro_id} ===")
    
    # Se não for POST, retornar para exibir o formulário
    if request.method != 'POST':
        print("Método não é POST, retornando None")
        return None
    
    # Definir mapeamento direto entre campos do formulário e colunas do banco de dados
    # Baseado no template form_new.html que funciona corretamente
    campo_mapping = {
        'UNIDADE': 'unidade',
        'Requisitante': 'usuario',
        'DATA': 'data_registro',
        'CLIENTE': 'cliente',
        'MODALIDADE': 'modalidade',
        'PEDIDO/REFERÊNCIA': 'pedido_referencia',
        'BOOKING / DI': 'booking_di',
        'CONTAINER 1': 'container_1',
        'CONTAINER 2': 'container_2',
        'LOTE CS': 'lote_cs',
        'STATUS CONTAINER': 'status_container',
        'ORIGEM': 'origem',
        'DESTINO INTERMEDIÁRIO': 'destino_intermediario',
        'DESTINO FINAL': 'destino_final',
        'MOTORISTA': 'motorista',
        'CPF MOTORISTA': 'cpf',
        'CAVALO': 'placa',
        'CARRETA 1': 'carreta1',
        'CARRETA 2': 'carreta2',
        'TIPO DE CARGA': 'tipo_carga',
        'HORÁRIO PREVISTO DE INÍCIO': 'horario_previsto',
        'ON TIME (CLIENTE)': 'on_time_cliente',
        'GERENCIADORA': 'gerenciadora',
        'NÚMERO AE': 'numero_ae',
        'DT CRIACAO AE': 'data_ae',
        'NUMERO SM': 'numero_sm',
        'DT CRIACAO SM': 'data_sm',
        'STATUS SM': 'status_sm',
        'OBSERVACAO OPERACIONAL': 'observacao_operacional',
        'OBSERVAÇÃO DE GR': 'observacao_gr',
        'ANEXAR NF': 'anexar_nf',
        'ANEXAR OS': 'anexar_os',
        'ANEXAR AGENDAMENTO': 'anexar_agendamento'
    }
    
    # Coletar todos os dados do formulário e mapê-los para as colunas do banco de dados
    dados_form = {}
    print("\n=== DADOS DO FORMULÁRIO ===\n")
    print(f"Total de campos no formulário: {len(request.form)}")
    
    # Primeiro, imprimir todos os campos do formulário para depuração
    print("Campos recebidos no formulário:")
    for campo, valor in request.form.items():
        if campo != 'csrf_token':
            print(f"  - {campo}: {valor[:30]}{'...' if len(valor) > 30 else ''}")
    
    # Processar os campos usando o mapeamento direto
    for campo_form, valor in request.form.items():
        # Ignorar o token CSRF e outros campos especiais
        if campo_form not in ['csrf_token']:
            # Verificar se o campo existe no mapeamento
            campo_db = campo_mapping.get(campo_form)
            
            # Se não encontrar no mapeamento, usar o campo original
            if not campo_db:
                # Tentar remover espaços e verificar novamente
                campo_sem_espacos = campo_form.replace(' ', '_').lower()
                if campo_sem_espacos in [col.lower() for col in campo_mapping.values()]:
                    campo_db = campo_sem_espacos
                else:
                    campo_db = campo_form
                    print(f"AVISO: Campo '{campo_form}' não encontrado no mapeamento, usando o nome original")
            
            # Adicionar ao dicionário de dados
            dados_form[campo_db] = valor.strip() if valor else ''
            print(f"Mapeado campo '{campo_form}' para '{campo_db}' com valor: {valor[:30]}{'...' if len(valor) > 30 else ''}")
    
    # Processar explicitamente os campos da seção "Dados da Operação"
    campos_operacao = {
        'MOTORISTA': 'motorista',
        'CPF MOTORISTA': 'cpf',
        'CAVALO': 'placa',
        'CARRETA 1': 'carreta1',
        'CARRETA 2': 'carreta2',
        'TIPO DE CARGA': 'tipo_carga',
        'HORÁRIO PREVISTO DE INÍCIO': 'horario_previsto',
        'ON TIME (CLIENTE)': 'on_time_cliente'
    }
    
    print("\n=== PROCESSANDO CAMPOS DA SEÇÃO 'DADOS DA OPERAÇÃO' ===\n")
    for campo_form, campo_db in campos_operacao.items():
        if campo_form in request.form and request.form[campo_form].strip():
            valor = request.form[campo_form].strip()
            
            # Remover pontos, traços e espaços do CPF do motorista
            if campo_form == 'CPF MOTORISTA':
                valor_original = valor
                valor = valor.replace('.', '').replace('-', '').replace(' ', '')
                print(f"CPF do motorista formatado: {valor_original} -> {valor}")
                
            dados_form[campo_db] = valor
            print(f"Campo da seção 'Dados da Operação' processado: {campo_form} -> {campo_db}: {valor}")
    
    print(f"\nTotal de campos mapeados para o banco: {len(dados_form)}")
    print("Campos mapeados para o banco:")
    for campo, valor in dados_form.items():
        print(f"  - {campo}: {valor[:30]}{'...' if len(valor) > 30 else ''}")
    
    # Processar anexos
    print("\n=== PROCESSANDO ANEXOS ===")
    
    # Definir os tipos de anexos a serem verificados
    tipos_anexos = [
        {'campo_form': 'ANEXAR NF', 'campo_db': 'anexar_nf', 'campo_nome': 'arquivo_nf_nome'},
        {'campo_form': 'ANEXAR OS', 'campo_db': 'anexar_os', 'campo_nome': 'arquivo_os_nome'},
        {'campo_form': 'ANEXAR AGENDAMENTO', 'campo_db': 'anexar_agendamento', 'campo_nome': 'arquivo_agendamento_nome'}
    ]
    
    # Verificar campos de data e hora 'horario_previsto' e 'on_time_cliente'
    # e permitir que sejam alterados pelo usuário
    campos_data_hora = ['horario_previsto', 'on_time_cliente']
    
    # Verificar e preservar os campos SM e AE se o usuário for comum
    if session.get('nivel') == 'comum':
        campos_gr = ['numero_sm', 'data_sm', 'numero_ae', 'data_ae']
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {', '.join(campos_gr)} FROM registros WHERE id = ?", (registro_id,))
            dados_gr = cursor.fetchone()
            
            if dados_gr:
                print("\n=== PRESERVANDO CAMPOS GR (SM/AE) ===\n")
                for campo in campos_gr:
                    valor_original = dados_gr[campo] if dados_gr[campo] else ''
                    if valor_original:
                        print(f"Preservando campo {campo} com valor: {valor_original}")
                        dados_form[campo] = valor_original
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {', '.join(campos_data_hora)} FROM registros WHERE id = ?", (registro_id,))
        dados_originais = cursor.fetchone()
        
        if dados_originais:
            for campo in campos_data_hora:
                # Verificar se o campo tem valor no banco de dados
                valor_original = dados_originais[campo] if dados_originais[campo] else ''
                
                # Obter o nome do campo no formulário
                campo_form = mapear_db_para_campo(campo)
                
                # Verificar se há um valor no formulário
                valor_form = request.form.get(campo_form, '')
                valor_form_original = request.form.get(f"{campo_form}_original", '')
                
                print(f"Campo {campo} (form: {campo_form})")
                print(f"  - Valor original no banco: {valor_original}")
                print(f"  - Valor no formulário: {valor_form}")
                print(f"  - Valor original no formulário: {valor_form_original}")
                
                # Verificar se o usuário alterou o valor
                if valor_form and valor_form.strip() != '':
                    # O usuário preencheu o campo, usar o valor do formulário
                    try:
                        # Converter o valor do formulário para o formato do banco
                        # datetime already imported at the top level
                        
                        # Verificar se o valor está no formato datetime-local (YYYY-MM-DDTHH:MM)
                        if 'T' in valor_form:
                            dt_form = datetime.strptime(valor_form, '%Y-%m-%dT%H:%M')
                            # Converter para o formato do banco (HH:MM:SS DD-MM-AAAA)
                            novo_valor = dt_form.strftime('%H:%M:%S %d-%m-%Y')
                            print(f"  - Valor convertido do formulário: {novo_valor}")
                            dados_form[campo] = novo_valor
                        # Verificar se temos o valor original do formulário
                        elif valor_form_original and valor_form_original.strip():
                            # Verificar se o valor original já está no formato do banco
                            if ' ' in valor_form_original and ('-' in valor_form_original or '/' in valor_form_original):
                                # Tentar converter para garantir que está no formato correto
                                try:
                                    # Verificar se usa / ou - como separador de data
                                    if '/' in valor_form_original:
                                        # Formato DD/MM/AAAA HH:MM
                                        dt_form = datetime.strptime(valor_form_original, '%d/%m/%Y %H:%M')
                                    else:
                                        # Formato HH:MM:SS DD-MM-AAAA
                                        hora_parte = valor_form_original.split(' ')[0]
                                        data_parte = valor_form_original.split(' ')[1]
                                        
                                        if ':' in hora_parte and '-' in data_parte:
                                            # Verificar se tem segundos
                                            if hora_parte.count(':') == 2:
                                                dt_form = datetime.strptime(valor_form_original, '%H:%M:%S %d-%m-%Y')
                                            else:
                                                dt_form = datetime.strptime(f"{hora_parte}:00 {data_parte}", '%H:%M:%S %d-%m-%Y')
                                    
                                    # Sempre converter para o formato padrão do banco
                                    novo_valor = dt_form.strftime('%H:%M:%S %d-%m-%Y')
                                    print(f"  - Valor original convertido: {valor_form_original} -> {novo_valor}")
                                    dados_form[campo] = novo_valor
                                except Exception as e:
                                    print(f"  - Erro ao converter valor original: {e}")
                                    # Usar o valor original como está
                                    dados_form[campo] = valor_form_original
                            else:
                                # Usar o valor original como está
                                print(f"  - Usando valor do formulário sem conversão: {valor_form}")
                                dados_form[campo] = valor_form
                    except Exception as e:
                        print(f"  - Erro ao processar valor do formulário: {e}")
                        # Em caso de erro, verificar se há um valor original no formulário
                        if valor_form_original and valor_form_original.strip() != '':
                            print(f"  - Usando valor original do formulário: {valor_form_original}")
                            # Tentar converter para o formato do banco
                            try:
                                # Try multiple formats
                                for fmt in ['%d/%m/%Y %H:%M', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M']:
                                    try:
                                        dt_form = datetime.strptime(valor_form_original, fmt)
                                        novo_valor = dt_form.strftime('%d-%m-%Y %H:%M:%S')
                                        dados_form[campo] = novo_valor
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    # If no format worked, use the original value
                                    dados_form[campo] = valor_form_original
                            except ValueError:
                                # Se não conseguir converter, usar o valor como está
                                dados_form[campo] = valor_form_original
                        else:
                            # Se não há valor original no formulário, manter o valor do banco
                            print(f"  - Preservando valor original do banco: {valor_original}")
                            dados_form[campo] = valor_original
                elif valor_form_original and valor_form_original.strip() != '':
                    # O campo está vazio, mas há um valor original no formulário
                    print(f"  - Usando valor original do formulário: {valor_form_original}")
                    # Tentar converter para o formato do banco
                    try:
                        # datetime already imported at the top level
                        # Try multiple formats
                        for fmt in ['%d/%m/%Y %H:%M', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M']:
                            try:
                                dt_form = datetime.strptime(valor_form_original, fmt)
                                novo_valor = dt_form.strftime('%d-%m-%Y %H:%M:%S')
                                dados_form[campo] = novo_valor
                                break
                            except ValueError:
                                continue
                        else:
                            # If no format worked, use the original value
                            dados_form[campo] = valor_form_original
                    except Exception as e:
                        print(f"Erro ao processar data {valor_form_original}: {e}")
                        # Se não conseguir converter, usar o valor como está
                        dados_form[campo] = valor_form_original
                else:
                    # Não há valor no formulário nem valor original, manter o valor do banco
                    print(f"  - Preservando valor original do banco: {valor_original}")
                    dados_form[campo] = valor_original
    
    # Verificar cada tipo de anexo
    for tipo in tipos_anexos:
        campo_form = tipo['campo_form']
        campo_db = tipo['campo_db']
        campo_nome = tipo['campo_nome']
        
        print(f"Verificando anexo: {campo_form} (campo DB: {campo_db})")
        
        # Verificar se há um arquivo existente que deve ser mantido
        campo_existente = f"{campo_db}_existente"
        nome_existente = f"{campo_nome}_existente"
        
        # Verificar se o campo existente está no formulário
        if campo_existente in request.form and request.form[campo_existente].strip():
            valor_existente = request.form[campo_existente].strip()
            print(f"Mantendo anexo existente (via {campo_existente}): {valor_existente}")
            dados_form[campo_db] = valor_existente
            
            # Se temos o nome do arquivo, também manter
            if nome_existente in request.form and request.form[nome_existente].strip():
                nome_arquivo = request.form[nome_existente].strip()
                print(f"Mantendo nome do anexo existente: {nome_arquivo}")
                dados_form[campo_nome] = nome_arquivo
            
            continue
        
        # Verificar se o campo já existe no banco de dados
        # Isso é uma verificação adicional para garantir que não perdemos anexos existentes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {campo_db}, {campo_nome} FROM registros WHERE id = ?", (registro_id,))
            anexo_existente = cursor.fetchone()
            
            if anexo_existente and anexo_existente[campo_db]:
                print(f"Anexo existente encontrado no banco de dados: {anexo_existente[campo_db]}")
                # Manter o anexo existente se não houver um novo
                if campo_form not in request.files or not request.files[campo_form].filename:
                    print(f"Mantendo anexo existente do banco: {anexo_existente[campo_db]}")
                    dados_form[campo_db] = anexo_existente[campo_db]
                    dados_form[campo_nome] = anexo_existente[campo_nome]
                    continue
        
        # Verificar se o campo existe no request.files
        if campo_form in request.files:
            file = request.files[campo_form]
            
            if file and file.filename and file.filename.strip() != '':
                print(f"Anexo encontrado: {file.filename}")
                
                try:
                    # Salvar o arquivo usando a função auxiliar
                    arquivo_salvo = save_uploaded_file(file)
                    if arquivo_salvo:
                        print(f"Arquivo salvo com sucesso: {arquivo_salvo}")
                        
                        # Adicionar informações do arquivo aos dados do formulário
                        dados_form[campo_db] = arquivo_salvo
                        dados_form[campo_nome] = file.filename
                        
                        print(f"Informações do anexo adicionadas aos dados do formulário")
                    else:
                        print(f"Falha ao salvar o arquivo {file.filename}")
                except Exception as e:
                    print(f"Erro ao processar anexo {file.filename}: {str(e)}")
                    
                    # Método alternativo de salvar arquivo se a função auxiliar falhar
                    try:
                        # Criar diretório de upload se não existir
                        tipo_anexo = campo_db.replace('anexar_', '')
                        diretorio_upload = os.path.join('static', 'uploads', tipo_anexo)
                        os.makedirs(diretorio_upload, exist_ok=True)
                        
                        # Gerar nome de arquivo único
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        nome_arquivo = f"{registro_id}_{tipo_anexo}_{timestamp}_{file.filename}"
                        caminho_arquivo = os.path.join(diretorio_upload, nome_arquivo)
                        
                        # Salvar o arquivo
                        file.save(caminho_arquivo)
                        print(f"Arquivo salvo com método alternativo em: {caminho_arquivo}")
                        
                        # Atualizar os dados do formulário com o caminho e nome do arquivo
                        dados_form[campo_db] = caminho_arquivo
                        dados_form[campo_nome] = file.filename
                    except Exception as e2:
                        print(f"Erro também no método alternativo: {str(e2)}")
            else:
                print(f"Nenhum arquivo selecionado ou arquivo inválido para {campo_form}")
        else:
            print(f"Campo '{campo_form}' não encontrado no request.files")
    
    # Conectar ao banco de dados e atualizar o registro
    try:
        print("\n=== CONECTANDO AO BANCO DE DADOS ===")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se a tabela registros existe e quais colunas ela tem
            cursor.execute("PRAGMA table_info(registros)")
            colunas_tabela = cursor.fetchall()
            nomes_colunas = [coluna[1] for coluna in colunas_tabela]
            
            print(f"\n=== COLUNAS DA TABELA REGISTROS ===\n")
            print(f"Total de colunas na tabela: {len(nomes_colunas)}")
            print(f"Colunas na tabela: {nomes_colunas}")
            
            # Obter os dados atuais do registro para comparação
            cursor.execute("SELECT * FROM registros WHERE id = ?", (registro_id,))
            registro_atual = cursor.fetchone()
            
            if not registro_atual:
                print(f"ERRO: Registro com ID {registro_id} não encontrado no banco de dados")
                return False
                
            registro_atual_dict = dict(registro_atual)
            print(f"Registro atual obtido do banco de dados: {registro_id}")
            
            # Verificar se o registro tem SM ou AE
            numero_sm = registro_atual_dict.get('numero_sm')
            numero_ae = registro_atual_dict.get('numero_ae')
            tem_sm_ae = (numero_sm and str(numero_sm).strip()) or (numero_ae and str(numero_ae).strip())
            print(f"Verificação de SM/AE - numero_sm: '{numero_sm}', numero_ae: '{numero_ae}', tem_sm_ae: {tem_sm_ae}")
            
            # Lista de campos importantes que, quando alterados, devem marcar o registro como modificado
            campos_importantes = [
                'cliente', 'container_1', 'container_2', 'lote_cs', 'status_container',
                'destino_intermediario', 'destino_final', 'origem', 'booking_di', 'pedido_referencia',
                'modalidade', 'observacao_operacional', 'motorista', 'cpf', 'placa', 'carreta1', 'carreta2',
                'tipo_carga', 'horario_previsto', 'on_time_cliente'
            ]
            
            # Verificar se algum campo importante foi alterado
            campos_alterados = False
            alteracoes = {}
            for campo in campos_importantes:
                if campo in dados_form and campo in registro_atual_dict:
                    valor_novo = str(dados_form[campo]) if dados_form[campo] is not None else ''
                    valor_antigo = str(registro_atual_dict[campo]) if registro_atual_dict[campo] is not None else ''
                    if valor_novo != valor_antigo:
                        print(f"Campo importante alterado: {campo} - de '{valor_antigo}' para '{valor_novo}'")
                        campos_alterados = True
                        alteracoes[campo] = {
                            'valor_antigo': valor_antigo,
                            'valor_novo': valor_novo
                        }
            
            # Verificar explicitamente os campos da seção "Dados da Operação"
            campos_operacao_db = ['motorista', 'cpf', 'placa', 'carreta1', 'carreta2', 'tipo_carga', 'horario_previsto', 'on_time_cliente']
            for campo in campos_operacao_db:
                if campo in dados_form and campo in registro_atual_dict:
                    valor_novo = str(dados_form[campo]) if dados_form[campo] is not None else ''
                    valor_antigo = str(registro_atual_dict[campo]) if registro_atual_dict[campo] is not None else ''
                    if valor_novo != valor_antigo:
                        print(f"Campo da seção 'Dados da Operação' alterado: {campo} - de '{valor_antigo}' para '{valor_novo}'")
                        campos_alterados = True
                        alteracoes[campo] = {
                            'valor_antigo': valor_antigo,
                            'valor_novo': valor_novo
                        }
            
            # Construir a query de atualização apenas com campos válidos
            campos_update = []
            valores = []
            campos_ignorados = []
            campos_alterados_lista = []
            # Não redefinir a variável alteracoes aqui, pois já foi preenchida acima
            
            for campo, valor in dados_form.items():
                # Verificar se o campo existe na tabela
                if campo in nomes_colunas:
                    # Verificar se o valor é diferente do atual
                    valor_atual = registro_atual_dict.get(campo)
                    
                    # Converter para string para comparação adequada
                    valor_atual_str = str(valor_atual) if valor_atual is not None else ''
                    novo_valor_str = str(valor) if valor is not None else ''
                    
                    if valor_atual_str != novo_valor_str:
                        campos_update.append(f"{campo} = ?")
                        valores.append(valor)
                        
                        # Registrar a alteração para histórico
                        alteracoes[campo] = {
                            'valor_antigo': valor_atual_str,
                            'valor_novo': novo_valor_str
                        }
                        
                        print(f"Campo alterado: {campo} = {novo_valor_str[:30]}{'...' if len(novo_valor_str) > 30 else ''} (anterior: {valor_atual_str[:30]}{'...' if len(valor_atual_str) > 30 else ''})")
                        
                        # Verificar se é um campo monitorado (usando campos_importantes definido acima)
                        if campo.lower() in [c.lower() for c in campos_importantes]:
                            campos_alterados_lista.append(campo)
                    else:
                        print(f"Campo não alterado (mesmo valor): {campo}")
                else:
                    campos_ignorados.append(campo)
                    print(f"AVISO: Campo '{campo}' não existe na tabela e será ignorado")
            
            # Garantir que os campos SM e AE sejam preservados na atualização
            if session.get('nivel') == 'comum':
                campos_gr = ['numero_sm', 'data_sm', 'numero_ae', 'data_ae']
                for campo in campos_gr:
                    if campo in registro_atual_dict and registro_atual_dict[campo] and campo not in [c.split(' = ')[0] for c in campos_update]:
                        valor = registro_atual_dict[campo]
                        print(f"Adicionando campo GR {campo} = {valor} à query de atualização para preservá-lo")
                        campos_update.append(f"{campo} = ?")
                        valores.append(valor)
            
            # Se não houver campos alterados para atualizar, retornar sucesso sem fazer alterações
            if not campos_update:
                print("Nenhum campo foi alterado, não é necessário atualizar o registro")
                return True
            
            # Verificar se é um usuário comum
            usuario_comum = session.get('nivel') == 'comum'
            print(f"Usuário é comum: {usuario_comum}")
            print(f"Campos monitorados alterados: {campos_alterados_lista}")
            
            # Data atual para registro de modificação
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Se for usuário comum e o registro tem SM/AE e houve alterações em campos monitorados
            if usuario_comum and tem_sm_ae and campos_alterados_lista:
                print(f"Usuário comum alterou campos monitorados em registro com SM/AE: {campos_alterados_lista}")
                campos_update.append("data_modificacao = ?")
                valores.append(now)
                campos_update.append("alteracoes_verificadas = ?")
                valores.append(0)
                campos_update.append("modificado_por = ?")
                valores.append(session.get('user', 'sistema'))
                print("Marcando registro para verificação pelo GR")
            else:
                # Apenas atualizar a data de modificação
                campos_update.append("data_modificacao = ?")
                valores.append(now)
                # Registrar quem fez a modificação
                campos_update.append("modificado_por = ?")
                valores.append(session.get('user', 'sistema'))
            
            # Adicionar o ID do registro para a cláusula WHERE
            valores.append(registro_id)
            
            # Construir e executar a query
            query = f"UPDATE registros SET {', '.join(campos_update)} WHERE id = ?"
            
            print(f"\n=== QUERY SQL ===\n")
            print(f"Query: {query}")
            print(f"Total de campos a atualizar: {len(campos_update)}")
            print(f"Campos ignorados: {campos_ignorados}")
            
            # Imprimir valores para depuração (sem mostrar valores muito longos)
            print("Valores para a query:")
            for i, valor in enumerate(valores[:-1]):
                valor_str = str(valor)
                print(f"  - Param {i+1}: {valor_str[:30]}{'...' if len(valor_str) > 30 else ''}")
            print(f"  - Param {len(valores)}: {registro_id} (registro_id)")
            
            # Executar a query
            try:
                cursor.execute(query, valores)
                
                # Verificar se alguma linha foi afetada
                if cursor.rowcount > 0:
                    print(f"Registro atualizado com sucesso. Linhas afetadas: {cursor.rowcount}")
                    
                    # Registrar alterações no histórico
                    if alteracoes:
                        usuario = session.get('user', 'sistema')
                        try:
                            cursor.execute(
                                "INSERT INTO historico (registro_id, alterado_por, alteracoes, data_alteracao) VALUES (?, ?, ?, ?)",
                                (registro_id, usuario, json.dumps(alteracoes), now)
                            )
                            print(f"Histórico de alterações registrado para {len(alteracoes)} campos")
                        except Exception as e:
                            print(f"Erro ao registrar histórico: {e}")
                    
                    # Registrar a ação no histórico geral
                    try:
                        historico = Historico()
                        historico.registrar_acao(
                            'alteracao',
                            'registros',
                            registro_id,
                            f"Registro editado por {session.get('user')}",
                            session.get('user')
                        )
                        print("Ação registrada no histórico geral")
                    except Exception as e:
                        print(f"Erro ao registrar no histórico geral: {e}")
                    
                    # Verificar se o anexo foi salvo corretamente
                    if 'arquivo_agendamento_nome' in dados_form:
                        cursor.execute("SELECT arquivo_agendamento_nome FROM registros WHERE id = ?", (registro_id,))
                        resultado = cursor.fetchone()
                        if resultado and resultado[0] == dados_form['arquivo_agendamento_nome']:
                            print(f"Anexo confirmado no banco de dados: {resultado[0]}")
                        else:
                            print(f"ALERTA: Anexo não encontrado no banco após atualização")
                    
                    conn.commit()
                    print("Commit realizado com sucesso")
                    return True
                else:
                    print("Nenhuma linha foi atualizada. Verificando se o registro existe...")
                    cursor.execute("SELECT COUNT(*) FROM registros WHERE id = ?", (registro_id,))
                    existe = cursor.fetchone()[0]
                    
                    if existe > 0:
                        print("O registro existe, mas nenhuma alteração foi feita")
                        conn.commit()  # Commit mesmo sem alterações
                        return True
                    else:
                        print(f"ERRO: Registro com ID {registro_id} não encontrado")
                        return False
                    
            except Exception as e:
                print(f"Erro ao atualizar registro: {e}")
                conn.rollback()
                return False
                
    except Exception as e:
        print(f"Erro ao processar edição: {e}")
        return False
