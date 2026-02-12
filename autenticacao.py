import requests

# --- VARIÁVEIS DE CONFIGURAÇÃO (PREENCHA AQUI) ---
# Embora as credenciais estejam hardcoded abaixo para o teste, o ideal é que elas
# sejam carregadas de variáveis de ambiente ou de um arquivo de configuração seguro.

def login_cailun():
    """ 
    Tenta logar na API Cailun e retorna o token JWT Bearer.
    Endpoint: POST https://api.cailun.com.br/login
    """
    url_login = "https://api.cailun.com.br/login"
    
    # Payload com as credenciais (que vieram da sua variável global no contexto original)
    payload = {
        "email": "seu email", # Substitua pelo e-mail real
        "password": "sua senha", # Substitua pela senha real
        "issuer": "cailun"
    }

    try:
        response = requests.post(url_login, json=payload)
        
        if response.status_code == 200:
            dados = response.json()
            
            # Extrai o token JWT (Bearer) corretamente aninhado em 'accessToken'
            token_jwt = dados.get("accessToken", {}).get("token")
            token_raiz = dados.get("token") # Backup (se existir)
            
            token_final = token_jwt if token_jwt else token_raiz
            
            return token_final
        else:
            print(f"❌ Erro no Login: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Erro de conexão no Login: {e}")
        return None

# Nota: O bloco de teste (if __name__ == "__main__":) foi omitido para manter este
# módulo focado estritamente na função de exportação do login.