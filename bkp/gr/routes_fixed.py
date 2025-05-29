from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import logging
from models.registros import Registro
from utils.database import get_db_connection
from utils.excel_processor import excel_processor
from admin.logs import log_admin_action

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

gr_bp = Blueprint('gr', __name__)

def gr_or_admin_required(f):
    """Decorator para exigir que o usuário seja GR ou admin"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'nivel' not in session or session['nivel'] not in ['gr', 'admin']:
            flash('Acesso não autorizado. Esta área requer privilégios de GR ou administrador.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    
    return decorated_function

@gr_bp.route('/dashboard')
@gr_or_admin_required
def dashboard():
    """Página inicial do painel GR"""
    return redirect(url_for('gr.ambiente'))

@gr_bp.route('/ambiente')
@gr_or_admin_required
def ambiente():
    """Ambiente específico para usuários do grupo GR"""
    usuario = session.get('user')
    nivel = session.get('nivel')
    
    # Obter parâmetros de filtragem e paginação da URL
    page = request.args.get('page', 1, type=int)
    filter_pendentes = request.args.get('pendentes', 'false') == 'true'
    filter_sem_sm = request.args.get('sem_sm', 'false') == 'true'
    filter_sem_ae = request.args.get('sem_ae', 'false') == 'true'
    filter_sem_container = request.args.get('sem_container', 'false') == 'true'
    registros_por_pagina = 10
    
    # Inicializar variáveis
    pendentes_sm = 0
    pendentes_ae = 0
    sem_container = 0
    distribuicao_status = []
    distribuicao_tipo_carga = []
    tempo_medio_inicio = 0
    tempo_medio_conclusao = 0
    alarmes = []
    registros = []
    total_registros = 0
    total_paginas = 1
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Buscar contagens para indicadores
            cursor.execute("SELECT COUNT(*) FROM registros WHERE (numero_sm IS NULL OR numero_sm = '') AND excluido = 0")
            pendentes_sm = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM registros WHERE (numero_ae IS NULL OR numero_ae = '') AND excluido = 0")
            pendentes_ae = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM registros WHERE (container_1 IS NULL OR container_1 = '') AND excluido = 0")
            sem_container = cursor.fetchone()[0]
            
            # 2. Distribuição de status para gráfico
            cursor.execute("""
                SELECT status_sm, COUNT(*) as total 
                FROM registros 
                WHERE status_sm IS NOT NULL AND status_sm != '' AND excluido = 0
                GROUP BY status_sm
                ORDER BY total DESC
            """)
            distribuicao_status = cursor.fetchall()
            
            # 3. Distribuição por tipo de carga
            cursor.execute("""
                SELECT tipo_carga, COUNT(*) as total 
                FROM registros 
                WHERE tipo_carga IS NOT NULL AND tipo_carga != '' AND excluido = 0
                GROUP BY tipo_carga
                ORDER BY total DESC
                LIMIT 5
            """)
            distribuicao_tipo_carga = cursor.fetchall()
            
            # 4. Tempo médio para início de atendimento 
            cursor.execute("""
                SELECT AVG(julianday(data_sm) - julianday(data_registro)) * 24 * 60 * 60 as segundos
                FROM registros 
                WHERE data_sm IS NOT NULL AND data_sm != '' 
                AND data_registro IS NOT NULL AND excluido = 0
            """)
            result = cursor.fetchone()
            tempo_medio_inicio = result[0] if result and result[0] else 0
            
            # 5. Tempo médio de conclusão
            cursor.execute("""
                SELECT AVG(julianday(data_ae) - julianday(data_sm)) * 24 * 60 * 60 as segundos
                FROM registros 
                WHERE data_ae IS NOT NULL AND data_ae != '' 
                AND data_sm IS NOT NULL AND data_sm != '' AND excluido = 0
            """)
            result = cursor.fetchone()
            tempo_medio_conclusao = result[0] if result and result[0] else 0
            
            # 6. Alarmes (registros com status de urgência ou problema)
            cursor.execute("""
                SELECT *
                FROM registros
                WHERE (status_sm = 'Urgente' OR status_sm = 'Problema') AND excluido = 0
                ORDER BY data_registro DESC
                LIMIT 5
            """)
            alarmes = cursor.fetchall()
            
            # 7. Registros para a tabela principal (com filtros aplicados)
            where_conditions = ["excluido = 0"]  # Apenas registros não excluídos
            params = []
            
            if filter_pendentes:
                where_conditions.append("(status_sm IS NULL OR status_sm = '' OR status_sm = 'Pendente')")
                
            if filter_sem_sm:
                where_conditions.append("(numero_sm IS NULL OR numero_sm = '')")
                
            if filter_sem_ae:
                where_conditions.append("(numero_ae IS NULL OR numero_ae = '')")
                
            if filter_sem_container:
                where_conditions.append("(container_1 IS NULL OR container_1 = '')")
            
            # Montar a consulta base para os registros
            query_base = "FROM registros"
            if where_conditions:
                query_base += " WHERE " + " AND ".join(where_conditions)
            
            # Contar total de registros para paginação
            cursor.execute(f"SELECT COUNT(*) {query_base}", params)
            total_registros = cursor.fetchone()[0]
            
            # Calcular o total de páginas
            total_paginas = (total_registros + registros_por_pagina - 1) // registros_por_pagina
            
            # Obter registros para a página atual
            offset = (page - 1) * registros_por_pagina
            query = f"""
                SELECT 
                    id, 
                    data_registro,
                    usuario,
                    cliente,
                    booking_di,
                    pedido_referencia,
                    container_1,
                    container_2,
                    motorista,
                    cavalo,
                    on_time_cliente,
                    horario_previsto,
                    numero_sm,
                    numero_ae
                {query_base} 
                ORDER BY data_registro DESC 
                LIMIT ? OFFSET ?
            """
            params.extend([registros_por_pagina, offset])
            
            cursor.execute(query, params)
            # Converter para dicionário para facilitar o acesso no template
            col_names = [description[0] for description in cursor.description]
            registros = [dict(zip(col_names, row)) for row in cursor.fetchall()]
            
    except Exception as e:
        flash(f"Erro ao carregar o ambiente GR: {e}", "danger")
        logger.error(f"Erro no ambiente GR: {str(e)}", exc_info=True)
    
    # Função para formatar o tempo em formato legível (HH:MM:SS)
    def segundos_para_hhmmss(segundos):
        if not segundos:
            return "00:00:00"
        try:
            segundos = int(segundos)
            horas = segundos // 3600
            minutos = (segundos % 3600) // 60
            segs = segundos % 60
            return f"{horas:02}:{minutos:02}:{segs:02}"
        except (ValueError, TypeError):
            return "00:00:00"
    
    # Preparar dados para gráficos
    labels_status = [row[0] for row in distribuicao_status] if distribuicao_status else []
    data_status = [row[1] for row in distribuicao_status] if distribuicao_status else []
    
    labels_tipo_carga = [row[0] for row in distribuicao_tipo_carga] if distribuicao_tipo_carga else []
    data_tipo_carga = [row[1] for row in distribuicao_tipo_carga] if distribuicao_tipo_carga else []
    
    # Opções de combobox do sistema
    combobox_options = excel_processor.COMBOBOX_OPTIONS if hasattr(excel_processor, 'COMBOBOX_OPTIONS') else {}
    
    # Criar URLs para paginação com os filtros preservados
    def gerar_url_paginacao(pagina):
        args = request.args.copy()
        args['page'] = pagina
        return url_for('gr.ambiente', **args)
    
    return render_template(
        'gr_ambiente.html',
        usuario=usuario,
        nivel=nivel,
        pendentes_sm=pendentes_sm,
        pendentes_ae=pendentes_ae,
        sem_container=sem_container,
        tempo_medio_inicio=segundos_para_hhmmss(tempo_medio_inicio),
        tempo_medio_conclusao=segundos_para_hhmmss(tempo_medio_conclusao),
        labels_status=labels_status,
        data_status=data_status,
        labels_tipo_carga=labels_tipo_carga,
        data_tipo_carga=data_tipo_carga,
        alarmes=alarmes,
        registros=registros,
        combobox_options=combobox_options,
        pagina_atual=page,
        total_paginas=total_paginas,
        total_registros=total_registros,
        filter_pendentes=filter_pendentes,
        filter_sem_sm=filter_sem_sm,
        filter_sem_ae=filter_sem_ae,
        filter_sem_container=filter_sem_container,
        gerar_url_paginacao=gerar_url_paginacao
    )

@gr_bp.route('/atualizar_registro/<int:registro_id>', methods=['POST'])
@gr_or_admin_required
def atualizar_registro(registro_id):
    """Atualiza um registro de atendimento com dados de GR"""
    usuario = session.get('user')
    
    # Obter os dados do formulário
    numero_sm = request.form.get('numero_sm', '')
    data_sm = request.form.get('data_sm', '')
    status_sm = request.form.get('status_sm', '')
    numero_ae = request.form.get('numero_ae', '')
    data_ae = request.form.get('data_ae', '')
    observacao_gr = request.form.get('observacao_gr', '')
    
    # Calcular SLA se necessário
    sla_sm = ""
    sla_ae = ""
    
    # Se temos data de SM e data de registro, calculamos o SLA SM
    if data_sm:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data_registro FROM registros WHERE id = ?", (registro_id,))
                registro = cursor.fetchone()
                
                if registro and registro['data_registro']:
                    # Calcular diferença em segundos
                    data_registro = datetime.strptime(registro['data_registro'], "%Y-%m-%d %H:%M:%S")
                    data_sm_dt = datetime.strptime(data_sm, "%Y-%m-%d %H:%M:%S")
                    diferenca = (data_sm_dt - data_registro).total_seconds()
                    
                    # Converter para horas com duas casas decimais
                    sla_sm = f"{diferenca / 3600:.2f}"
        except Exception as e:
            logger.error(f"Erro ao calcular SLA SM: {e}")
    
    # Se temos data de AE e data de SM, calculamos o SLA AE
    if data_ae and data_sm:
        try:
            data_sm_dt = datetime.strptime(data_sm, "%Y-%m-%d %H:%M:%S")
            data_ae_dt = datetime.strptime(data_ae, "%Y-%m-%d %H:%M:%S")
            diferenca = (data_ae_dt - data_sm_dt).total_seconds()
            
            # Converter para horas com duas casas decimais
            sla_ae = f"{diferenca / 3600:.2f}"
        except Exception as e:
            logger.error(f"Erro ao calcular SLA AE: {e}")
    
    # Preparar os dados para atualização
    dados = {
        'numero_sm': numero_sm,
        'data_sm': data_sm,
        'status_sm': status_sm,
        'numero_ae': numero_ae,
        'data_ae': data_ae,
        'observacao_gr': observacao_gr,
        'sla_sm': sla_sm,
        'sla_ae': sla_ae
    }
    
    # Remover campos vazios para não sobrescrever dados existentes
    dados = {k: v for k, v in dados.items() if v}
    
    # Atualizar o registro
    if Registro.update(registro_id, dados, usuario):
        # Registrar a ação no log administrativo
        log_admin_action(
            usuario,
            "ATUALIZAÇÃO DE REGISTRO GR",
            f"Registro ID: {registro_id}, Campos: {', '.join(dados.keys())}"
        )
        
        flash("Registro atualizado com sucesso.", "success")
    else:
        flash("Erro ao atualizar o registro.", "danger")
    
    # Redirecionar para a página apropriada
    referrer = request.form.get('referrer', '')
    if referrer == 'ambiente':
        return redirect(url_for('gr.ambiente'))
    else:
        return redirect(url_for('gr.dashboard'))
