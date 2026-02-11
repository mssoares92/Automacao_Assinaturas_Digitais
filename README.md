# 🤖 Projeto: Automação de Assinaturas Digital - API Cailun

Este ecossistema de scripts em Python automatiza o ciclo de vida de assinaturas digitais, integrando pastas de rede locais com a API Cailun. O foco principal é o envio em massa de **Contra-cheques, Cartões Ponto e Documentos de Férias**.

---

## 📑 Visão Geral dos Scripts

### 1. `autenticacao.py` (Módulo de Acesso)
* **Função:** Realiza o aperto de mão (*handshake*) com o servidor.
* **O que faz:** Envia as credenciais de administrador e recupera um **Token JWT (Bearer)** necessário para todas as requisições.

### 2. `busca_ids_pastas.py` (Módulo de Navegação Cloud)
* **Função:** Mapeia a árvore de diretórios no portal Cailun.
* **O que faz:** * Navega em **3 níveis**: Unidade (Matriz/Filial/Tele) -> Funcionário -> Pasta de Destino (RECIBOS).
    * **Busca Global:** Caso um funcionário não seja encontrado no setor indicado pela pasta de rede, o script realiza uma varredura automática em todos os outros setores sob a raiz `3073`.

### 3. `fluxo_assinatura.py` (O Orquestrador)
* **Função:** Coordena a execução de ponta a ponta.
* **O que faz:**
    1. Identifica a pasta de rede mais recente (Lógica Ano > Mês-Ano).
    2. Limpa os nomes dos arquivos PDF (remove sufixos como `_13`, `_AVISO` ou `_RECIBO`).
    3. Realiza o **Match Inteligente** cruzando o nome do PDF com a base Excel.
    4. Aciona a API para iniciar o fluxo e envia o link via **WhatsApp**.
    5. Move arquivos processados para a subpasta `ENVIADOS`.

---

## 📊 Estrutura da Base de Dados (`rel_funcionarios.xlsx`)

O robô utiliza a primeira aba deste arquivo. As colunas devem seguir exatamente este padrão:

| Coluna | Descrição | Regra de Preenchimento |
| :--- | :--- | :--- |
| **NOME** | Nome Completo | Deve ser idêntico ao registro oficial (Sem abreviações). |
| **CPF** | CPF do colaborador | Apenas números (o robô limpa pontuações). |
| **TELEFONE** | Número de WhatsApp | Com DDD (Ex: 51988887777). |
| **EMAIL** | E-mail do colaborador | Formato padrão (exemplo@tlt.com.br). |

---

## 🛠️ Regras de Operação

### 1. Organização da Rede
A rede deve seguir a hierarquia cronológica para ser lida corretamente:
`Pasta Base` > `Ano (Ex: 2025)` > `Mês-Ano (Ex: 12-2025)`

### 2. Nomenclatura de Arquivos
O algoritmo extrai as palavras principais do arquivo para busca. 
* **Exemplos aceitos:** `JOÃO SILVA_AVISO.pdf`, `JOÃO SILVA_13.pdf`.
* **Resultado:** O robô buscará por "JOÃO SILVA" na planilha.

---

## 🚀 Como Executar

1. Certifique-se de que a planilha `rel_funcionarios.xlsx` está atualizada.
2. Coloque os arquivos PDF na pasta do mês correspondente na rede.
3. Execute o script principal:
   ```bash
   python fluxo_assinatura.py
