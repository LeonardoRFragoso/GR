import os
import shutil
from datetime import datetime

# Caminho absoluto da pasta atual (bkp)
bkp_dir = os.path.dirname(os.path.abspath(__file__))

# Caminho do arquivo .db na raiz do projeto
db_file = os.path.join(bkp_dir, '..', 'usuarios.db')

# Nome do arquivo com data e hora
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_file = os.path.join(bkp_dir, f'usuarios_{timestamp}.db')

# Realiza o backup
shutil.copy2(db_file, backup_file)
print(f'✅ Backup criado em: {backup_file}')

# Limita a 5 backups
backups = sorted(
    [f for f in os.listdir(bkp_dir) if f.startswith("usuarios_") and f.endswith(".db")]
)
while len(backups) > 5:
    to_remove = backups.pop(0)
    os.remove(os.path.join(bkp_dir, to_remove))
    print(f'🗑️ Backup antigo removido: {to_remove}')
