# historico.py

import json
import re
import logging
from datetime import datetime
from flask import session
from constants import TABLE_HISTORICO, TABLE_REGISTROS, TABLE_USUARIOS, ALTERACAO_EDICAO_GR, MSG_TABELA_HISTORICO_NAO_ENCONTRADA
from db import get_db_connection, verificar_criar_colunas
from historico_utils import sanitize_json_string

logger = logging.getLogger(__name__)

def registrar_historico(cursor, registro_id, tipo_alteracao, campos, valores=None, usuario=None, conn=None):
    try:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_HISTORICO}'")
        if not cursor.fetchone():
            logger.warning(MSG_TABELA_HISTORICO_NAO_ENCONTRADA)
            return False
        if usuario is None:
            usuario = session.get('user', 'Sistema')
        alteracoes = {"tipo": tipo_alteracao, "campos": campos, "usuario": usuario}
        if valores:
            alteracoes["valores"] = valores
        cursor.execute(f"""
            INSERT INTO {TABLE_HISTORICO} (registro_id, alterado_por, alteracoes, data_alteracao)
            VALUES (?, ?, ?, ?)
        """, (registro_id, usuario, json.dumps(alteracoes), datetime.now().strftime('%d-%m-%Y %H:%M:%S')))
        if conn:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return False

def get_registros_com_alteracoes_pos_smae(cursor=None, colunas=None):
    registros_alterados = []
    registros_alterados_ids = []
    conn_local = None
    if cursor is None:
        conn_local = get_db_connection()
        cursor = conn_local.cursor()
        if colunas is None:
            colunas = verificar_criar_colunas(conn_local, cursor)
    try:
        campos_monitorados = [
            'usuario', 'placa', 'motorista', 'cpf', 'mot_loc', 'carreta', 'carreta1', 'carreta2',
            'carreta_loc', 'cliente', 'loc_cliente', 'arquivo', 'container_1', 'container_2',
            'status_sm', 'tipo_carga', 'status_container', 'modalidade', 'gerenciadora',
            'booking_di', 'pedido_referencia', 'lote_cs', 'on_time_cliente', 'horario_previsto',
            'observacao_operacional', 'observacao_gr', 'destino_intermediario', 'destino_final',
            'anexar_nf', 'anexar_os', 'anexar_agendamento', 'numero_nf', 'serie', 'quantidade',
            'peso_bruto', 'valor_total_nota', 'unidade', 'arquivo_nf_nome', 'arquivo_os_nome',
            'arquivo_agendamento_nome', 'origem'
        ]
        campos_existentes = [campo for campo in campos_monitorados if campo in colunas]
        if not campos_existentes:
            logger.warning("Nenhum campo monitorado encontrado na tabela registros")
            return registros_alterados, registros_alterados_ids
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
        if not cursor.fetchone():
            return [], []
        query_ids = f"""
            SELECT DISTINCT r.id FROM {TABLE_REGISTROS} r
            JOIN {TABLE_HISTORICO} h ON r.id = h.registro_id
            WHERE ((r.numero_sm IS NOT NULL AND r.numero_sm != '' AND r.numero_sm != '0')
                OR (r.numero_ae IS NOT NULL AND r.numero_ae != '' AND r.numero_ae != '0'))
                AND r.excluido = 0
                AND r.alteracoes_verificadas = 0
                AND h.data_alteracao >
                    CASE
                        WHEN r.data_sm IS NOT NULL AND r.data_sm > r.data_ae THEN r.data_sm
                        WHEN r.data_ae IS NOT NULL THEN r.data_ae
                        ELSE r.data_sm
                    END
                AND h.alterado_por NOT IN (SELECT username FROM {TABLE_USUARIOS} WHERE nivel = 'gr')
                AND h.alteracoes NOT LIKE '%\"tipo\": \"{ALTERACAO_EDICAO_GR}\"%'
                AND h.alteracoes NOT LIKE '%numero_sm%'
                AND h.alteracoes NOT LIKE '%numero_ae%'
        """
        cursor.execute(query_ids)
        id_rows = cursor.fetchall()
        ids_registros = [str(row[0]) for row in id_rows]
        if not ids_registros:
            return [], []
        placeholders = ', '.join(['?' for _ in ids_registros])
        query_registros = f"""
            SELECT * FROM {TABLE_REGISTROS} 
            WHERE id IN ({placeholders}) 
            AND excluido = 0
        """
        cursor.execute(query_registros, [int(id) for id in ids_registros])
        registros = cursor.fetchall()
        registros_dict = [dict(zip([col[0] for col in cursor.description], row)) for row in registros]
        registros_filtrados = []
        ids_filtrados = []
        for registro_dict in registros_dict:
            registro_id = registro_dict['id']
            cursor.execute(f"""
                SELECT alteracoes FROM {TABLE_HISTORICO} 
                WHERE registro_id = ? 
                AND data_alteracao > 
                    CASE
                        WHEN ? IS NOT NULL AND ? > ? THEN ?
                        WHEN ? IS NOT NULL THEN ?
                        ELSE ?
                    END
                AND alterado_por NOT IN (SELECT username FROM {TABLE_USUARIOS} WHERE nivel = 'gr')
            """, (
                registro_id,
                registro_dict.get('data_sm'), registro_dict.get('data_sm'), registro_dict.get('data_ae'), registro_dict.get('data_sm'),
                registro_dict.get('data_ae'), registro_dict.get('data_ae'), registro_dict.get('data_sm')))
            historico_rows = cursor.fetchall()
            for hist_row in historico_rows:
                alteracoes_json = hist_row[0]
                try:
                    alteracoes_json_sanitizado = sanitize_json_string(alteracoes_json)
                    if not alteracoes_json_sanitizado or alteracoes_json_sanitizado == '{}':
                        alteracoes_json_sanitizado = re.sub(r'\\', '', alteracoes_json)
                        alteracoes_json_sanitizado = re.sub(r'[\x00-\x1F\x7F]', '', alteracoes_json_sanitizado)
                    if any(campo in alteracoes_json_sanitizado for campo in campos_existentes):
                        if 'numero_sm' in alteracoes_json_sanitizado or 'numero_ae' in alteracoes_json_sanitizado:
                            continue
                        if 'tipo' in alteracoes_json_sanitizado and ALTERACAO_EDICAO_GR in alteracoes_json_sanitizado:
                            continue
                        registros_filtrados.append(registro_dict)
                        ids_filtrados.append(str(registro_id))
                        break
                except Exception as e:
                    logger.error(f"Erro ao processar JSON do histórico para registro {registro_id}: {e}")
                    continue
        return registros_filtrados, ids_filtrados
    except Exception as e:
        logger.error(f"Erro ao obter registros com alterações pós SM/AE: {e}")
        return [], []
    finally:
        if conn_local:
            conn_local.close()
