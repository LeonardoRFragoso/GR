import sqlite3

# Conectar ao banco de dados
conn = sqlite3.connect('usuarios.db')
cursor = conn.cursor()

# Verificar registros sem data_registro
cursor.execute('SELECT id, data_registro FROM registros WHERE data_registro IS NULL OR data_registro = "" LIMIT 10')
print('Registros sem data_registro:')
results = cursor.fetchall()
for row in results:
    print(f'ID: {row[0]}, data_registro: {row[1]}')

# Contar total de registros sem data_registro
cursor.execute('SELECT COUNT(*) FROM registros WHERE data_registro IS NULL OR data_registro = ""')
total = cursor.fetchone()[0]
print(f'Total de registros sem data_registro: {total}')

# Contar total de registros
cursor.execute('SELECT COUNT(*) FROM registros')
total_all = cursor.fetchone()[0]
print(f'Total de registros no banco: {total_all}')
print(f'Porcentagem de registros sem data_registro: {(total/total_all)*100 if total_all > 0 else 0:.2f}%')

# Fechar conexão
conn.close()
