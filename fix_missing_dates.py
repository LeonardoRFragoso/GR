import sqlite3
from datetime import datetime
import os

# Conectar ao banco de dados
conn = sqlite3.connect('usuarios.db')
cursor = conn.cursor()

# Data atual formatada no padrão DD-MM-YYYY HH:MM:SS (formato padrão do projeto)
data_atual = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

# Identificar registros sem data_registro
cursor.execute('SELECT id, data_modificacao FROM registros WHERE data_registro IS NULL OR data_registro = ""')
registros_sem_data = cursor.fetchall()

print(f"Encontrados {len(registros_sem_data)} registros sem data de registro.")

# Atualizar cada registro sem data_registro
for registro in registros_sem_data:
    registro_id = registro[0]
    data_modificacao = registro[1]
    
    # Se o registro tiver data de modificação, usar uma data anterior a ela
    # Caso contrário, usar a data atual
    data_a_usar = data_atual
    if data_modificacao:
        try:
            # Tentar converter a data de modificação para datetime
            # e subtrair 1 minuto para garantir que a data de registro seja anterior
            data_mod = None
            
            # Tentar diferentes formatos de data
            formatos = ['%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S']
            for formato in formatos:
                try:
                    data_mod = datetime.strptime(data_modificacao, formato)
                    break
                except ValueError:
                    continue
            
            if data_mod:
                # Subtrair 1 minuto para garantir que a data de registro seja anterior
                data_registro = data_mod.replace(minute=data_mod.minute-1)
                data_a_usar = data_registro.strftime('%d-%m-%Y %H:%M:%S')
        except Exception as e:
            print(f"Erro ao processar data de modificação para ID {registro_id}: {e}")
    
    cursor.execute('UPDATE registros SET data_registro = ? WHERE id = ?', (data_a_usar, registro_id))
    print(f"Atualizado registro ID {registro_id} com data_registro = {data_a_usar}")

# Commit das alterações
conn.commit()

# Verificar se todos os registros agora têm data_registro
cursor.execute('SELECT COUNT(*) FROM registros WHERE data_registro IS NULL OR data_registro = ""')
total_sem_data = cursor.fetchone()[0]
print(f"Total de registros sem data_registro após correção: {total_sem_data}")

# Criar um log da operação
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_path, exist_ok=True)

with open(os.path.join(log_path, 'correcao_datas_registro.log'), 'a') as log_file:
    log_file.write(f"[{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}] Corrigidos {len(registros_sem_data)} registros sem data de registro.\n")

# Fechar conexão
conn.close()

print("Processo de correção concluído!")
print("Um log da operação foi salvo na pasta 'logs'.")
