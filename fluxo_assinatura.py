# -*- coding: utf-8 -*-
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
    ID_PASTA_RAIZ_SISTEMA, 
    buscar_id_final_recibos
)

# --- CAMINHO ONDE ESTÁ O ARQUIVO EXCEL QUE CONTEM OS DADOS DOS FUNCIONÁRIOS, COMO: NOME, CPF E NÚMERO ---
CAMINHO_PLANILHA = r"\\fs\tlt\ADMINISTRATIVO\RH\DEPTO PESSOAL\FOLHA DE PAGTO\folha Conferencia GZ\rel_funcionarios.xlsx"


# --- CAMINHO DOS ARQUIVOS PDFs QUE SERÃO ENVIADOS PARA OS FUNCINÁRIOS --- #
PASTAS_REDE = [

    #CONTRA-CHEQUES
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\FOLHA DE PAGTO\folha Conferencia GZ\TELE FILIAL",
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\FOLHA DE PAGTO\folha Conferencia GZ\TELE MATRIZ",

    #PONTOS

    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\PONTO BIOMETRIA - I9PONTO\CARTAO PONTO\TELE - FILIAL",
    r"\\fs\TLT\ADMINISTRATIVO\RH\DEPTO PESSOAL\PONTO BIOMETRIA - I9PONTO\CARTAO PONTO\TELE - MATRIZ",
]

# --- 1. FUNÇÕES DE SUPORTE ---

def limpar_numero(dado):
    if pd.isna(dado): return ""
    return re.sub(r'[^0-9]', '', str(dado))

def formatar_telefone_cailun(telefone_limpo: str) -> str:
    if not 12 <= len(telefone_limpo) <= 13:
        return telefone_limpo
    ddi, ddd, numero = telefone_limpo[:2], telefone_limpo[2:4], telefone_limpo[4:]
    if len(numero) == 9:
        return f"{ddi}({ddd}){numero[:5]}-{numero[5:]}"
    elif len(numero) == 8:
        return f"{ddi}({ddd}){numero[:4]}-{numero[4:]}"
    return telefone_limpo

def carregar_dados_excel(caminho):
    try:
        df = pd.read_excel(caminho, dtype=str) 
        dados_dict = {}
        for _, row in df.iterrows():
            nome_completo = str(row['NOME']).strip().upper() 
            tel = limpar_numero(row['TELEFONE'])
            if tel and not tel.startswith('55'): tel = f"55{tel}"
            dados_dict[nome_completo] = { 
                "name": nome_completo.title(), 
                "cpf": limpar_numero(row['CPF']), 
                "phone": formatar_telefone_cailun(tel),
                "email": str(row['EMAIL']).strip() 
            }
        return dados_dict
    except Exception as e:
        print(f"❌ Erro ao ler Excel: {e}"); return {}

def buscar_dados_por_nome_curto(db_funcionarios: dict, nome_curto: str):
    palavras_chave_filtradas = {p for p in nome_curto.upper().split() if len(p) > 2}
    if not palavras_chave_filtradas: return None, None

    for nome_completo, dados in db_funcionarios.items():
        palavras_nome_completo = set(nome_completo.split())
        if palavras_chave_filtradas.issubset(palavras_nome_completo):
            return dados, nome_completo
    return None, None 

def encontrar_pasta_recente(caminho_base):
    if not os.path.exists(caminho_base): return None
    try:
        anos = sorted([d for d in os.listdir(caminho_base) if d.isdigit() and len(d) == 4], reverse=True)
        if not anos: return None
        caminho_ano = os.path.join(caminho_base, anos[0])
        meses = []
        for d in os.listdir(caminho_ano):
            if re.match(r"(\d{2})-(\d{4})", d):
                meses.append((datetime.strptime(d, "%m-%Y"), d))
        if not meses: return None
        return os.path.join(caminho_ano, sorted(meses, reverse=True)[0][1])
    except: return None

def mover_para_enviados(caminho_arquivo):
    diretorio_enviados = os.path.join(os.path.dirname(caminho_arquivo), "ENVIADOS")
    try:
        if not os.path.exists(diretorio_enviados): os.makedirs(diretorio_enviados)
        shutil.move(caminho_arquivo, os.path.join(diretorio_enviados, os.path.basename(caminho_arquivo)))
        return True
    except Exception as e:
        print(f"   🛑 Erro ao organizar arquivo: {e}"); return False

# --- 2. LÓGICA DE ENVIO ---

def enviar_fluxo_assinatura(token, caminho_arquivo, dados_func, id_pasta_destino):
    url = "https://api.cailun.com.br/subscriptionFlow" 
    dt_limite = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "name": os.path.basename(caminho_arquivo),
        "folderId": id_pasta_destino, 
        "signatureLimitDate": dt_limite, 
        "reminder": "true", "reminderDays": "2",
        "message": f"Olá {dados_func['name']}, segue seu documento para assinatura via WhatsApp.",
        "signatories[0][name]": dados_func['name'],
        "signatories[0][cpf]": dados_func['cpf'], 
        "signatories[0][phone]": dados_func['phone'], 
        "signatories[0][email]": dados_func['email'],
        "signatories[0][signAsId]": "1", "signatories[0][requiredAuthenticationType]": "11",
        "signatories[0][groupId]": "0"                   
    }
    try:
        with open(caminho_arquivo, 'rb') as f:
            header = {"Authorization": f"Bearer {token}"}
            resp = requests.post(url, headers=header, data=payload, files={'file': f})
            return resp.status_code in [200, 201]
    except: return False

# --- 3. ORQUESTRADOR COM INTERFACE PERSONALIZADA ---

def orquestrar_automacao():
    print(f"\n{'#'*60}")
    print(f"{' '*10}🤖 INICIANDO SISTEMA DE ASSINATURAS CAILUN")
    print(f"{'#'*60}\n")
    
    token = login_cailun()
    if not token: 
        print("🛑 Erro crítico: Falha na autenticação com a API.")
        return

    db_funcionarios = carregar_dados_excel(CAMINHO_PLANILHA)
    mapa_pastas_mae = mapear_pastas_cailun(token, ID_PASTA_RAIZ_SISTEMA)
    
    if not db_funcionarios or not mapa_pastas_mae: 
        print("🛑 Erro crítico: Falha ao carregar base Excel ou estrutura Cailun.")
        return

    for caminho_base_rede in PASTAS_REDE:
        setor_nome = os.path.basename(caminho_base_rede).upper()
        setor_cailun = setor_nome.replace("FOLHA ", "").replace("DISK - ", "").strip()
        id_setor_sugerido = mapa_pastas_mae.get(setor_cailun)
        
        pasta_alvo = encontrar_pasta_recente(caminho_base_rede)
        if not pasta_alvo: continue

        print(f"📂 VARRENDO PASTA: {pasta_alvo}")
        arquivos = [f for f in os.listdir(pasta_alvo) if f.lower().endswith('.pdf')]

        for arq in arquivos:
            print(f"\n{'-'*50}")
            print(f"📄 DOCUMENTO: {arq}")
            
            # Etapa 1: Leitura
            print("   ↳ 📂 Arquivo identificado na rede... check ✔️")

            nome_limpo = re.sub(r'[_\-\sº\.]+', ' ', arq.replace(".pdf", "").upper()).strip()
            nome_busca = " ".join(nome_limpo.split()[:3]) 

            # Etapa 2: Identificação do Funcionário
            dados_func, nome_completo = buscar_dados_por_nome_curto(db_funcionarios, nome_busca)

            if not dados_func:
                print(f"   ↳ ⚠️ Funcionário '{nome_busca}' não localizado no Excel... ❌")
                continue
            print(f"   ↳ 👤 Funcionário: {nome_completo}... check ✔️")

            # Etapa 3: Localização no Cailun
            id_recibos = buscar_id_final_recibos(token, id_setor_sugerido, nome_completo)
            
            if not id_recibos:
                print(f"   ↳ 🛑 Pasta 'RECIBOS' não encontrada no Cailun... ❌")
                continue
            print(f"   ↳ 🔍 Localização no Cailun confirmada... check ✔️")

            # Etapa 4: Envio
            print(f"   ↳ ✈️  Enviando para a API...")
            if enviar_fluxo_assinatura(token, os.path.join(pasta_alvo, arq), dados_func, id_recibos):
                print(f"   ↳ 📲 FINALIZADO: Enviado para o WhatsApp: {dados_func['phone']} 📱")
                mover_para_enviados(os.path.join(pasta_alvo, arq))
            else:
                print(f"   ↳ 💥 ERRO: Falha na comunicação com a API Cailun... 🛑")

    print(f"\n{'#'*60}")
    print(f"{' '*15}✅ PROCESSO FINALIZADO COM SUCESSO")
    print(f"{'#'*60}\n")
    input("Pressione Enter para fechar...")

if __name__ == "__main__":
    orquestrar_automacao()