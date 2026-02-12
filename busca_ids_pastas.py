import requests
import json
import os

# --- CONFIGURAÇÕES DE PARTIDA ---
ID_PASTA_RAIZ_SISTEMA = 3073  # ID que contém as pastas MATRIZ, FILIAL, TELE
NOME_PASTA_TERCEIRO_NIVEL = "RECIBOS" 
# -----------------------------------

def mapear_pastas_cailun(token: str, id_raiz: int) -> dict:
    """ 
    Busca as subpastas em um ID específico, retornando um dicionário {NOME_PASTA: ID}.
    """
    endpoint = f"https://api.cailun.com.br/storage/folder/{id_raiz}/folders" 
    headers = {"Authorization": f"Bearer {token}"}
    mapa_pastas = {}

    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            lista_itens = response.json().get('data')
            if not lista_itens or not isinstance(lista_itens, list):
                return {}
            for item in lista_itens:
                if 'id' in item and 'label' in item: 
                    nome = item.get('label', '').strip().upper() 
                    mapa_pastas[nome] = item.get('id')
            return mapa_pastas
        return {}
    except Exception as e:
        print(f"❌ Erro de conexão ao buscar pastas (ID: {id_raiz}): {e}")
        return {}

def buscar_id_final_recibos(token: str, id_raiz_setor_inicial: int, nome_funcionario: str) -> int or None:
    """
    Tenta encontrar a pasta RECIBOS do funcionário.
    Se não encontrar no setor inicial (ex: vindo da pasta MATRIZ na rede),
    ele faz uma busca global nas outras pastas irmãs (FILIAL, TELE).
    """
    
    # 1. Primeiro, tenta no setor que o orquestrador sugeriu (Baseado na pasta da Rede)
    id_final = _executar_busca_3_niveis(token, id_raiz_setor_inicial, nome_funcionario)
    
    if id_final:
        return id_final

    # 2. Se não encontrou, o funcionário pode estar em outro setor no Cailun.
    # Vamos mapear todos os setores disponíveis (MATRIZ, FILIAL, TELE, etc.)
    print(f"🔍 Buscando {nome_funcionario} em outros setores...")
    setores_disponiveis = mapear_pastas_cailun(token, ID_PASTA_RAIZ_SISTEMA)
    
    for nome_setor, id_setor in setores_disponiveis.items():
        # Pula o setor inicial pois já testamos ele
        if id_setor == id_raiz_setor_inicial:
            continue
            
        id_final = _executar_busca_3_niveis(token, id_setor, nome_funcionario)
        if id_final:
            print(f"   ✅ Encontrado na pasta setor: {nome_setor}")
            return id_final

    return None

def _executar_busca_3_niveis(token, id_setor, nome_funcionario):
    """ Função interna para evitar repetição de código (DRY) """
    # Nível 2: Buscar a Pasta do Funcionário
    mapa_funcionarios = mapear_pastas_cailun(token, id_setor)
    id_func = mapa_funcionarios.get(nome_funcionario.upper())
    
    if id_func:
        # Nível 3: Buscar a Pasta RECIBOS
        mapa_recibos = mapear_pastas_cailun(token, id_func)
        return mapa_recibos.get(NOME_PASTA_TERCEIRO_NIVEL.upper())
    
    return None