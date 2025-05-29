# Importar a função consolidada para facilitar o acesso
from .registros_direto_final import processar_edicao_registro_direto

# Adicionar um aviso de depreciação para os arquivos antigos
import warnings

def _deprecated_import_warning(message):
    warnings.warn(message, DeprecationWarning, stacklevel=2)

# Configurar os avisos para os arquivos antigos
class RegistrosDiretoDeprecated:
    def __getattr__(self, name):
        _deprecated_import_warning(
            "O módulo 'operations.registros_direto' está depreciado. "
            "Use 'operations.registros_direto_final' em seu lugar."
        )
        # Importar do módulo final para manter compatibilidade
        from . import registros_direto_final
        return getattr(registros_direto_final, name)

# Substituir os módulos antigos com avisos de depreciação
import sys
sys.modules['operations.registros_direto_fix'] = RegistrosDiretoDeprecated()
sys.modules['operations.registros_direto_corrigido'] = RegistrosDiretoDeprecated()