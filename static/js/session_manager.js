/**
 * Gerenciador de sessão para manter a sessão ativa e detectar quando o usuário fecha a página
 */
(function() {
    // Intervalo de heartbeat em milissegundos (30 segundos)
    const HEARTBEAT_INTERVAL = 30000;
    
    // Variável para armazenar o ID do intervalo
    let heartbeatInterval;
    
    /**
     * Envia um heartbeat para o servidor para manter a sessão ativa
     */
    function sendHeartbeat() {
        fetch('/api/heartbeat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                // Se a resposta não for OK, a sessão pode ter expirado
                console.log('Sessão expirada ou inválida');
                window.location.href = '/login';
            }
            return response.json();
        })
        .then(data => {
            console.log('Heartbeat enviado com sucesso');
        })
        .catch(error => {
            console.error('Erro ao enviar heartbeat:', error);
        });
    }
    
    /**
     * Inicia o mecanismo de heartbeat
     */
    function startHeartbeat() {
        // Enviar um heartbeat imediatamente
        sendHeartbeat();
        
        // Configurar o intervalo para enviar heartbeats periodicamente
        heartbeatInterval = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
    }
    
    /**
     * Para o mecanismo de heartbeat
     */
    function stopHeartbeat() {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
        }
    }
    
    /**
     * Manipulador para quando a página é fechada ou o usuário navega para outra página
     */
    function handlePageUnload() {
        // Tentar fazer logout ao fechar a página
        navigator.sendBeacon('/auth/logout');
    }
    
    // Iniciar o mecanismo de heartbeat quando a página carregar
    document.addEventListener('DOMContentLoaded', startHeartbeat);
    
    // Detectar quando o usuário fecha a página ou navega para outra página
    window.addEventListener('beforeunload', handlePageUnload);
    
    // Expor funções para uso global
    window.sessionManager = {
        startHeartbeat,
        stopHeartbeat,
        sendHeartbeat
    };
})();
