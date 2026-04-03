# Workflow: WhatsApp Bot — Agente das Metas

## Objetivo
Gerenciar metas operacionais de um grupo de restaurantes via WhatsApp,
permitindo que usuários autorizados verifiquem indicadores e que
administradores apontem ocorrências e configurem novas metas.

## Inputs necessários
- Mensagem recebida pelo webhook (texto ou resposta interativa)
- Número de telefone do remetente (extraído do payload do webhook)

## Ferramentas utilizadas
- `tools/whatsapp_client.py` — Envio de mensagens via WhatsApp Cloud API
- `tools/supabase_client.py` — Leitura e escrita no Supabase
- `tools/conversation_handler.py` — Máquina de estados das conversas

## Fluxo Principal

### 1. Autenticação
- Recebe mensagem → extrai `from` (telefone) do payload
- Consulta `bot_users` pelo número
- **Não encontrado** → Envia "Acesso restrito" → Encerra
- **Encontrado** → Verifica estado da sessão em memória → Roteia

### 2. Menu principal
| Tipo de usuário | Opções disponíveis                        |
|-----------------|-------------------------------------------|
| Usuário comum   | 📊 Ver Metas                              |
| Administrador   | 📊 Ver Metas · 📝 Apontar · ⚙️ Admin     |

### 3. Ver Metas
1. Se acesso a múltiplas lojas → seleciona loja (lista)
2. Seleciona tipo de meta (lista)
3. Exibe resumo do mês atual por setor com status ✅/❌
4. Volta ao menu

### 4. Apontar Indicador _(admin)_
1. Seleciona loja (lista)
2. Seleciona tipo de meta (lista)
3. Seleciona setor (lista)
4. Tela de confirmação (botões)
5. Confirma → insere registro na tabela `bot_records_{meta}`

### 5. Menu Admin _(admin)_
- **Cadastrar usuário**: Coleta telefone → nome → perfil → loja → salva
- **Listar usuários**: Exibe todos os cadastros
- **Nova meta**: Coleta loja → nome → limite → setores → cria tabela + config
- **Nova loja**: Coleta nome → cadastra → vincula admins

## Output esperado
Mensagens interativas no WhatsApp (botões e listas) guiando o usuário
em cada passo sem necessidade de memorizar comandos.

## Tabelas do banco
| Tabela                  | Descrição                                      |
|-------------------------|------------------------------------------------|
| `bot_users`             | Usuários autorizados + flag is_admin           |
| `bot_stores`            | Restaurantes/lojas                             |
| `bot_user_store_access` | Quais usuários acessam quais lojas             |
| `bot_sectors`           | Setores por loja                               |
| `bot_meta_configs`      | Configurações de cada meta (nome, meta, tabela)|
| `bot_meta_sectors`      | Setores vinculados a cada meta                 |
| `bot_records_*`         | Registros de ocorrências (uma tabela por meta) |

## Metas configuradas — Moby Dick Cloud Kitchen
| Meta     | Meta          | Setores |
|----------|---------------|---------|
| Limpeza  | ≤2 ocorrências | Nippon Dia/Noite, TQ Dia/Delivery/Dom Severino, Aglio Nero |
| Estoque  | ≤2 ocorrências | Nippon Dia/Noite, TQ Dia/Delivery, Aglio Nero |
| Produção | ≤2 ocorrências | Nippon Dia/Noite, TQ Dia/Delivery/Dom Severino, Aglio Nero |

## Configuração inicial
```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Preencher .env com credenciais
# (WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, SUPABASE_URL, etc.)

# 3. Inicializar banco de dados (apenas uma vez)
python tools/db_setup.py

# 4. Iniciar servidor com ngrok
python start.py

# 5. Configurar webhook no Meta for Developers com a URL exibida
```

## Restrições da WhatsApp Cloud API
- Botões: máximo 3, título ≤ 20 caracteres
- Lista: máximo 10 itens, título da linha ≤ 24 caracteres
- Botão de abertura da lista: ≤ 20 caracteres
- O bot só pode iniciar conversa com templates aprovados
- Respostas livres funcionam dentro de 24h após mensagem do usuário

## Casos excepcionais
| Situação | Comportamento |
|---|---|
| Sessão expirada (30 min) | Usuário volta ao estado inicial ao enviar nova mensagem |
| Mensagem fora do fluxo | Palavras "menu", "oi", "início" resetam para o menu principal |
| Número já cadastrado | Admin recebe aviso, sem duplicar registro |
| Loja sem setores | Aviso ao criar meta, orienta cadastrar setores primeiro |
| Erro de API WhatsApp | Log no servidor, usuário recebe mensagem de erro genérica |

## Aprendizados / observações
_(Atualizar conforme o sistema evoluir)_
- Setores com nomes longos (>24 chars) são truncados na lista do WhatsApp — considerar abreviações no cadastro
