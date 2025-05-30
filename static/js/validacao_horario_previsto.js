// Validação de horário previsto
document.addEventListener('DOMContentLoaded', function() {
  // Função para formatar data no padrão DD-MM-YYYY HH:MM:SS
  function formatarDataBancoDados(data) {
    const ano = data.getFullYear();
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const dia = String(data.getDate()).padStart(2, '0');
    const hora = String(data.getHours()).padStart(2, '0');
    const minuto = String(data.getMinutes()).padStart(2, '0');
    const segundo = String(data.getSeconds()).padStart(2, '0');
    
    return `${dia}-${mes}-${ano} ${hora}:${minuto}:${segundo}`;
  }
  
  // Função para formatar data no padrão do input datetime-local: YYYY-MM-DDTHH:MM
  function formatarDataInput(data) {
    const ano = data.getFullYear();
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const dia = String(data.getDate()).padStart(2, '0');
    const hora = String(data.getHours()).padStart(2, '0');
    const minuto = String(data.getMinutes()).padStart(2, '0');
    
    return `${ano}-${mes}-${dia}T${hora}:${minuto}`;
  }
  
  // Função para validar que o horário previsto é posterior à data de registro
  function validarHorarioPrevisto() {
    const horarioPrevisto = document.querySelector('input[name="HORÁRIO PREVISTO DE INÍCIO"]');
    const dataRegistro = document.querySelector('input[name="data_registro"]');
    
    if (!horarioPrevisto || !dataRegistro) return true;
    
    const valorHorarioPrevisto = horarioPrevisto.value;
    const valorDataRegistro = dataRegistro.value;
    
    if (!valorHorarioPrevisto || !valorDataRegistro) return true;
    
    const dataHorarioPrevisto = new Date(valorHorarioPrevisto);
    const dataDataRegistro = new Date(valorDataRegistro);
    
    // Verificar se as datas são válidas
    if (isNaN(dataHorarioPrevisto.getTime()) || isNaN(dataDataRegistro.getTime())) return true;
    
    // Verificar se o horário previsto é posterior à data de registro
    if (dataHorarioPrevisto <= dataDataRegistro) {
      // Definir um valor padrão: data de registro + 24 horas
      const novaData = new Date(dataDataRegistro);
      novaData.setHours(novaData.getHours() + 24);
      
      // Formatar para o formato esperado pelo input datetime-local
      const novoValor = formatarDataInput(novaData);
      
      // Atualizar o valor do campo
      horarioPrevisto.value = novoValor;
      
      // Formatar para exibição no alerta (formato DD/MM/YYYY HH:MM:SS)
      const dataFormatada = novaData.toLocaleDateString('pt-BR') + ' ' + 
                           novaData.toLocaleTimeString('pt-BR');
      
      // Exibir alerta
      alert(`O horário previsto deve ser posterior à data de registro. Foi definido automaticamente para 24 horas após o registro: ${dataFormatada}`);
      
      // Adicionar um campo oculto com o valor formatado para o banco de dados
      let campoOculto = document.querySelector('input[name="horario_previsto_formatado"]');
      if (!campoOculto) {
        campoOculto = document.createElement('input');
        campoOculto.type = 'hidden';
        campoOculto.name = 'horario_previsto_formatado';
        horarioPrevisto.parentNode.appendChild(campoOculto);
      }
      campoOculto.value = formatarDataBancoDados(novaData);
      
      return false;
    }
    
    // Se o horário previsto é válido, também adicionar o campo oculto formatado
    let campoOculto = document.querySelector('input[name="horario_previsto_formatado"]');
    if (!campoOculto) {
      campoOculto = document.createElement('input');
      campoOculto.type = 'hidden';
      campoOculto.name = 'horario_previsto_formatado';
      horarioPrevisto.parentNode.appendChild(campoOculto);
    }
    campoOculto.value = formatarDataBancoDados(dataHorarioPrevisto);
    
    return true;
  }
  
  // Adicionar validação ao envio do formulário
  const formulario = document.querySelector('form');
  if (formulario) {
    formulario.addEventListener('submit', function(e) {
      if (!validarHorarioPrevisto()) {
        e.preventDefault();
      }
    });
  }
  
  // Adicionar validação ao mudar o valor do campo
  const horarioPrevisto = document.querySelector('input[name="HORÁRIO PREVISTO DE INÍCIO"]');
  if (horarioPrevisto) {
    horarioPrevisto.addEventListener('change', validarHorarioPrevisto);
    
    // Definir valor padrão ao criar um novo registro
    const dataRegistro = document.querySelector('input[name="data_registro"]');
    if (dataRegistro && !horarioPrevisto.value) {
      dataRegistro.addEventListener('change', function() {
        if (!horarioPrevisto.value) {
          const dataRegistroValue = new Date(this.value);
          if (!isNaN(dataRegistroValue.getTime())) {
            // Adicionar 24 horas à data de registro
            const novaData = new Date(dataRegistroValue);
            novaData.setHours(novaData.getHours() + 24);
            
            // Formatar para o formato esperado pelo input datetime-local
            const novoValor = formatarDataInput(novaData);
            
            // Atualizar o valor do campo
            horarioPrevisto.value = novoValor;
            
            // Adicionar um campo oculto com o valor formatado para o banco de dados
            let campoOculto = document.querySelector('input[name="horario_previsto_formatado"]');
            if (!campoOculto) {
              campoOculto = document.createElement('input');
              campoOculto.type = 'hidden';
              campoOculto.name = 'horario_previsto_formatado';
              horarioPrevisto.parentNode.appendChild(campoOculto);
            }
            campoOculto.value = formatarDataBancoDados(novaData);
          }
        }
      });
    }
  }
});
