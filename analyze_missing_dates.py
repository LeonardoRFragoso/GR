import sqlite3
import os
from datetime import datetime

# Conectar ao banco de dados
conn = sqlite3.connect('usuarios.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Verificar registros sem data_registro
cursor.execute('''
    SELECT id, usuario, data_registro, data_modificacao, 
           numero_sm, data_sm, numero_ae, data_ae
    FROM registros 
    WHERE data_registro IS NULL OR data_registro = ""
''')

print("\n=== REGISTROS SEM DATA DE REGISTRO ===")
registros_sem_data = cursor.fetchall()
for r in registros_sem_data:
    print(f"ID: {r['id']}")
    print(f"  Usuário: {r['usuario']}")
    print(f"  Data Registro: {r['data_registro']}")
    print(f"  Data Modificação: {r['data_modificacao']}")
    print(f"  Número SM: {r['numero_sm']}, Data SM: {r['data_sm']}")
    print(f"  Número AE: {r['numero_ae']}, Data AE: {r['data_ae']}")
    print("  ---")

# Verificar registros criados antes e depois dos registros sem data
if registros_sem_data:
    min_id = min(r['id'] for r in registros_sem_data)
    max_id = max(r['id'] for r in registros_sem_data)
    
    # Verificar registros anteriores
    cursor.execute('''
        SELECT id, usuario, data_registro, data_modificacao
        FROM registros 
        WHERE id < ? 
        ORDER BY id DESC
        LIMIT 3
    ''', (min_id,))
    
    print("\n=== REGISTROS ANTERIORES AOS PROBLEMÁTICOS ===")
    for r in cursor.fetchall():
        print(f"ID: {r['id']}")
        print(f"  Usuário: {r['usuario']}")
        print(f"  Data Registro: {r['data_registro']}")
        print(f"  Data Modificação: {r['data_modificacao']}")
        print("  ---")
    
    # Verificar registros posteriores
    cursor.execute('''
        SELECT id, usuario, data_registro, data_modificacao
        FROM registros 
        WHERE id > ? 
        ORDER BY id ASC
        LIMIT 3
    ''', (max_id,))
    
    print("\n=== REGISTROS POSTERIORES AOS PROBLEMÁTICOS ===")
    for r in cursor.fetchall():
        print(f"ID: {r['id']}")
        print(f"  Usuário: {r['usuario']}")
        print(f"  Data Registro: {r['data_registro']}")
        print(f"  Data Modificação: {r['data_modificacao']}")
        print("  ---")

# Verificar se há algum padrão nos registros sem data
cursor.execute('''
    SELECT usuario, COUNT(*) as total
    FROM registros 
    WHERE data_registro IS NULL OR data_registro = ""
    GROUP BY usuario
''')

print("\n=== USUÁRIOS COM REGISTROS SEM DATA ===")
for r in cursor.fetchall():
    print(f"Usuário: {r['usuario']}, Total: {r['total']}")

# Verificar se há algum padrão temporal (baseado nos IDs)
print("\n=== ANÁLISE DE SEQUÊNCIA DE IDs ===")
if registros_sem_data:
    ids = [r['id'] for r in registros_sem_data]
    ids.sort()
    print(f"IDs dos registros sem data: {ids}")
    
    # Verificar se são IDs consecutivos
    if len(ids) > 1:
        consecutivos = all(ids[i+1] - ids[i] == 1 for i in range(len(ids)-1))
        print(f"Os IDs são consecutivos? {'Sim' if consecutivos else 'Não'}")

# Verificar histórico para esses registros
print("\n=== HISTÓRICO DE ALTERAÇÕES ===")
for r in registros_sem_data:
    cursor.execute('''
        SELECT * FROM historico
        WHERE registro_id = ?
        ORDER BY data_alteracao
    ''', (r['id'],))
    
    historico = cursor.fetchall()
    print(f"ID: {r['id']}, Total de alterações: {len(historico)}")
    
    for h in historico:
        print(f"  Data: {h['data_alteracao']}, Tipo: {h['tipo_alteracao']}")

# Fechar conexão
conn.close()

print("\n=== ANÁLISE CONCLUÍDA ===")
print("Recomendação: Verificar o código que cria registros para garantir que a data_registro sempre seja definida.")
