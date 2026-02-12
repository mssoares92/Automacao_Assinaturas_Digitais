import os
import re
import shutil
import pandas as pd
import requests
import json
from datetime import datetime, timedelta 

# --- IMPORTAÇÃO DE MÓDULOS ESSENCIAIS ---
from autenticacao import login_cailun
from busca_ids_pastas import (
    mapear_pastas_cailun, 
    NOME_PASTA_TERCEIRO_NIVEL, 
    ID_PASTA_RAIZ_TESTE,
    buscar_id_final_recibos
)

# --- CONFIGURAÇÕES CRÍTICAS ---

# SUBSTITUA PELO CAMINHO REAL DA SUA PLANILHA DE FUNCIONÁRIOS
CAMINHO_PLANILHA = r"C:\Users\matheus.soares\Desktop\AutomacoesPython\API_Cailun\rel_funcionarios.xlsx" 

# CONFIGURAÇÃO DE FÉRIAS: Caminhos específicos para os Recibos de Férias
PASTAS_REDE_FERIAS = [
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\FERIAS\RECIBOS DE FERIAS\MATRIZ",
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\FERIAS\RECIBOS DE FERIAS\FILIAL",
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\FERIAS\RECIBOS DE FERIAS\TELE"
]

# DADOS FIXOS DO DIRETOR (PRIMEIRO SIGNATÁRIO, VIA E-MAIL)
DIRETOR_CONFIG = {
    "name": "nome diretor",
    "cpf": "cpf diretor", 
    "email": "email diretor"
}


# --- FUNÇÕES DE SUPORTE (MANTIDAS) ---

def limpar_numero(dado):
    """ Remove tudo que não for número (para CPF e Telefone). """
    if pd.isna(dado): return ""
    return re.sub(r'[^0-9]', '', str(dado))

def formatar_telefone_cailun(telefone_limpo: str) -> str:
    """ Formata o telefone no padrão estrito da API: XX(XX)XXXXX-XXXX. """
    if not 12 <= len(telefone_limpo) <= 13: return telefone_limpo
    ddi = telefone_limpo[:2]
    ddd = telefone_limpo[2:4]
    numero = telefone_limpo[4:]
    if len(numero) == 9:
        formatado = f"{ddi}({ddd}){numero[:5]}-{numero[5:]}"
    elif len(numero) == 8:
        formatado = f"{ddi}({ddd}){numero[:4]}-{numero[4:]}"
    else:
        return telefone_limpo 
    return formatado

def carregar_dados_excel(caminho):
    """ LÊ O EXCEL, USANDO NOME COMPLETO COMO CHAVE. """
    try:
        df = pd.read_excel(caminho, dtype=str) 
        dados_dict = {}
        for _, row in df.iterrows():
            nome_completo = str(row['NOME']).strip().upper() 
            telefone_limpo = limpar_numero(row['TELEFONE'])
            if telefone_limpo and not telefone_limpo.startswith('55'):
                telefone_limpo = f"55{telefone_limpo}"
            dados_dict[nome_completo] = { 
                "name": nome_completo.title(), 
                "cpf": limpar_numero(row['CPF']), 
                "phone": formatar_telefone_cailun(telefone_limpo),
                "email": str(row['EMAIL']).strip() 
            }
        return dados_dict
    except Exception as e:
        print(f"❌ Erro ao ler Excel: {e}") 
        return {}

def buscar_dados_por_nome_curto(db_funcionarios: dict, nome_curto: str):
    """
    Função de match: Procura o funcionário verificando se TODAS as palavras-chave 
    do nome curto estão contidas no nome completo.
    """
    palavras_chave = set(nome_curto.upper().split())
    palavras_chave_filtradas = {p for p in palavras_chave if len(p) > 2}

    if not palavras_chave_filtradas:
        return None, None

    for nome_completo, dados in db_funcionarios.items():
        palavras_nome_completo = set(nome_completo.split())
        
        if palavras_chave_filtradas.issubset(palavras_nome_completo):
            return dados, nome_completo
    
    return None, None 

def encontrar_pasta_recente(caminho_base):
    """ Encontra o caminho da pasta do mês/ano mais recente na rede. """
    if not os.path.exists(caminho_base): return None
    try:
        itens_ano = os.listdir(caminho_base)
        anos = sorted([d for d in itens_ano if d.isdigit() and len(d) == 4 and os.path.isdir(os.path.join(caminho_base, d))], reverse=True)
        if not anos: return None
        caminho_ano = os.path.join(caminho_base, anos[0])

        itens_mes = os.listdir(caminho_ano)
        meses_validos = []
        padrao_mes = re.compile(r"(\d{2})-(\d{4})")
        for item in itens_mes:
            if padrao_mes.match(item) and os.path.isdir(os.path.join(caminho_ano, item)):
                meses_validos.append((datetime.strptime(item, "%m-%Y"), item))
        
        if not meses_validos: return None
        meses_validos.sort(key=lambda x: x[0], reverse=True)
        
        return os.path.join(caminho_ano, meses_validos[0][1])

    except Exception as e:
        return None

def mover_para_enviados(caminho_arquivo):
    """ Cria a subpasta 'ENVIADOS' e move o arquivo após o processamento. """
    diretorio_origem = os.path.dirname(caminho_arquivo)
    diretorio_enviados = os.path.join(diretorio_origem, "ENVIADOS")
    
    try:
        if not os.path.exists(diretorio_enviados):
            os.makedirs(diretorio_enviados)
        shutil.move(caminho_arquivo, os.path.join(diretorio_enviados, os.path.basename(caminho_arquivo)))
        print(f"   ✅ Arquivo movido para ENVIADOS.")
        return True
    except Exception as e:
        print(f"   ❌ ERRO ao mover arquivo: {e}")
        return False


# --- 2. LÓGICA DE ENVIO DO FLUXO DE FÉRIAS (API) ---

def enviar_fluxo_assinatura_ferias(token, caminho_arquivo, dados_func, id_pasta_destino):
    """ 
    Executa o POST /subscriptionFlow com 2 signatários em ordem: 
    1. Diretor (E-MAIL); 2. Funcionário (WHATSAPP).
    """
    url = "https://api.cailun.com.br/subscriptionFlow" 
    dt_limite = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # 1. Payload base
    payload = {
        "name": os.path.basename(caminho_arquivo), 
        "folderId": id_pasta_destino, 
        "signatureLimitDate": dt_limite, 
        "reminder": "true",          
        "reminderDays": "2",         
        "message": f"Documento de Férias de {dados_func['name']} para assinatura sequencial.",
    }

    # 2. Signatário 0: DIRETOR (Assina Primeiro, via E-MAIL)
    payload["signatories[0][name]"] = DIRETOR_CONFIG['name']
    payload["signatories[0][cpf]"] = DIRETOR_CONFIG['cpf']
    payload["signatories[0][email]"] = DIRETOR_CONFIG['email']
    payload["signatories[0][signAsId]"] = "1"
    payload["signatories[0][requiredAuthenticationType]"] = "1" # E-MAIL
    payload["signatories[0][groupId]"] = "0" 
    
    # 3. Signatário 1: FUNCIONÁRIO (Assina Depois, via WHATSAPP)
    payload["signatories[1][name]"] = dados_func['name']
    payload["signatories[1][cpf]"] = dados_func['cpf']
    payload["signatories[1][phone]"] = dados_func['phone']
    payload["signatories[1][email]"] = dados_func['email']
    payload["signatories[1][signAsId]"] = "1"
    payload["signatories[1][requiredAuthenticationType]"] = "11" # WHATSAPP
    payload["signatories[1][groupId]"] = "0"
    
    try:
        with open(caminho_arquivo, 'rb') as f:
            files = {'file': f}
            header = {"Authorization": f"Bearer {token}"}
            resp = requests.post(url, headers=header, data=payload, files=files)
            
            if resp.status_code in [200, 201]:
                print(f"   ✅ SUCESSO! Fluxo iniciado (Diretor via Email -> Func. via WhatsApp).")
                return True
            else:
                print(f"   ❌ FALHA NO FLUXO ({resp.status_code}): {resp.text}") 
                return False
    except Exception as e:
        print(f"   ❌ Erro de envio: {e}")
        return False


# --- 3. FLUXO PRINCIPAL DE FÉRIAS (ORQUESTRAÇÃO) ---

def orquestrar_automacao_ferias():
    print("--- 🤖 ORQUESTRADOR: INICIANDO FLUXO DE ASSINATURA DE FÉRIAS (Multi-Signatário e Multi-Arquivo) ---")
    
    token = login_cailun()
    if not token: 
        return

    db_funcionarios = carregar_dados_excel(CAMINHO_PLANILHA)
    if not db_funcionarios: return
    
    mapa_pastas_mae = mapear_pastas_cailun(token, ID_PASTA_RAIZ_TESTE)
    if not mapa_pastas_mae:
        print("Finalizando: Não foi possível mapear as pastas mãe.")
        return
    
    for caminho_base_rede in PASTAS_REDE_FERIAS:
        
        # 1. Determina a pasta alvo (mantida a lógica de fallback)
        pasta_alvo_recente = encontrar_pasta_recente(caminho_base_rede)
        if not pasta_alvo_recente or not os.path.exists(pasta_alvo_recente):
            pasta_alvo_recente = caminho_base_rede
            if not os.path.exists(pasta_alvo_recente):
                print(f"⚠️ PULAR: Caminho de rede inacessível: {caminho_base_rede}")
                continue
        
        # Extração e validação do setor (mantida)
        nome_setor_bruto = os.path.basename(caminho_base_rede).upper()
        nome_setor_cailun = nome_setor_bruto.replace("FOLHA ", "").replace("DISK - ", "").strip() 
        id_pasta_mae = mapa_pastas_mae.get(nome_setor_cailun)
        
        if not id_pasta_mae:
            print(f"\n⚠️ PULAR: Pasta de setor '{nome_setor_cailun}' não mapeada no Cailun.")
            continue

        arquivos = [f for f in os.listdir(pasta_alvo_recente) if f.lower().endswith('.pdf') and not os.path.isdir(os.path.join(pasta_alvo_recente, f))]
        
        if not arquivos:
            print(f"DEBUG: NENHUM arquivo PDF encontrado em {pasta_alvo_recente}")
            continue
        
        # --- LOOP PRINCIPAL: PROCESSAR CADA ARQUIVO SEPARADAMENTE ---
        
        for arq in arquivos:
            caminho_completo = os.path.join(pasta_alvo_recente, arq)
            nome_arquivo_bruto = arq.replace(".pdf", "").strip()
            
            # 3. LIMPEZA E EXTRAÇÃO DE NOME (Foco em remover sufixos para o Match)
            
            nome_limpo = nome_arquivo_bruto.upper()
            
            # Remove padrões de sufixo (AVISO, RECIBO, 13, etc.) para isolar o nome.
            nome_limpo = re.sub(r'(_AVISO|_RECIBO|_13º|_13)', '', nome_limpo)
            
            nome_limpo_espacado = re.sub(r'[_\-\sº\.]+', ' ', nome_limpo).strip()
            partes_do_nome = nome_limpo_espacado.split(' ')
            nome_extraido_para_busca = " ".join(partes_do_nome[:3])
            
            # --- FIM DA EXTRAÇÃO ---

            # 4. BUSCA INTELIGENTE: Busca os dados na planilha
            dados_func, nome_completo_cailun = buscar_dados_por_nome_curto(db_funcionarios, nome_extraido_para_busca)

            if dados_func:
                # 5. Busca o ID FINAL DA PASTA RECIBOS (3 NÍVEIS)
                id_final_recibos = buscar_id_final_recibos(token, id_pasta_mae, nome_completo_cailun)
                
                if id_final_recibos:
                    print(f"   🚀 Processando: {nome_completo_cailun} (Arquivo: {arq})...")
                    
                    # 6. Envio do Fluxo de Assinatura de Férias (2 Signatários)
                    sucesso_envio = enviar_fluxo_assinatura_ferias(token, caminho_completo, dados_func, id_final_recibos)
                    
                    if sucesso_envio:
                        mover_para_enviados(caminho_completo)
                else:
                    print(f"   ⚠️ PULAR: {nome_completo_cailun} (ID FINAL RECIBOS não encontrado).")

            else:
                print(f"   ⚠️ PULAR: {nome_extraido_para_busca} (FALTA DADO NO EXCEL ou NOME NÃO CORRESPONDE).")

if __name__ == "__main__":
    orquestrar_automacao_ferias()