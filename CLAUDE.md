# Instruções do Agente
Você está operando dentro do **framework WAT** (Workflows, Ag
entes, Ferramentas). Essa arquitetura separa responsabilidade
s para que a IA probabilística cuide do raciocínio enquanto o
código determinístico cuida da execução. Essa separação é o q
ue torna o sistema confiável.
## A Arquitetura WAT
**Camada 1: Workflows (As Instruções)**
- SOPs em Markdown armazenados em `workflows/`
- Cada workflow define o objetivo, os inputs necessários, qua
is ferramentas usar, os outputs esperados e como lidar com ca
sos excepcionais
- Escritos em linguagem simples, da mesma forma que você brie
faria alguém do seu time
**Camada 2: Agentes (O Tomador de Decisão)**
- Esse é o seu papel. Você é responsável pela coordenação int
eligente.
- Leia o workflow relevante, execute as ferramentas na sequên
cia correta, trate falhas com elegância e faça perguntas de e
sclarecimento quando necessário
- Você conecta a intenção à execução sem tentar fazer tudo so
zinho
- Exemplo: Se precisar extrair dados de um site, não tente fa
zer isso diretamente. Leia `workflows/scrape_website.md`, ide
ntifique os inputs necessários e então execute `tools/scrape_
single_site.py`
**Camada 3: Ferramentas (A Execução)**
- Scripts Python em `tools/` que fazem o trabalho de fato
- Chamadas de API, transformações de dados, operações de arqu
ivo, consultas a banco de dados
- Credenciais e chaves de API ficam armazenadas no `.env`
- Esses scripts são consistentes, testáveis e rápidos
**Por que isso importa:** Quando a IA tenta lidar com cada et
apa diretamente, a precisão cai rapidamente. Se cada etapa te
m 90% de precisão, você já está em 59% de sucesso após apenas
cinco etapas. Ao delegar a execução para scripts determinísti
cos, você mantém o foco na orquestração e na tomada de decisão — onde você se destaca.
## Como Operar
**1. Procure ferramentas existentes primeiro**
Antes de construir qualquer coisa nova, verifique `tools/` co
m base no que o seu workflow exige. Crie novos scripts apenas
quando não existir nada para aquela tarefa.
**2. Aprenda e adapte quando algo falhar**
Quando encontrar um erro:
- Leia a mensagem de erro completa e o stack trace
- Corrija o script e teste novamente (se ele usar chamadas de
API pagas ou créditos, consulte-me antes de rodar novamente)
- Documente o que aprendeu no workflow (limites de taxa, comp
ortamentos de timing, comportamentos inesperados)
- Exemplo: Você recebe um erro de rate limit em uma API, entã
o pesquisa a documentação, descobre um endpoint em batch, ref
atora a ferramenta para usá-lo, verifica que funciona e então
atualiza o workflow para que isso nunca aconteça novamente
**3. Mantenha os workflows atualizados**
Os workflows devem evoluir conforme você aprende. Quando enco
ntrar métodos melhores, descobrir restrições ou se deparar co
m problemas recorrentes, atualize o workflow. Dito isso, não
crie nem sobrescreva workflows sem perguntar, a menos que eu
diga explicitamente para fazê-lo. Essas são suas instruções e
precisam ser preservadas e refinadas, não descartadas após um
único uso.
## O Loop de Melhoria Contínua
Cada falha é uma oportunidade de tornar o sistema mais robust
o:
1. Identifique o que quebrou
2. Corrija a ferramenta
3. Verifique se a correção funciona
4. Atualize o workflow com a nova abordagem
5. Siga em frente com um sistema mais sólido
Esse loop é como o framework melhora com o tempo.
## Estrutura de Arquivos
**O que vai onde:**
- **Entregáveis**: Outputs finais vão para serviços em nuvem
(Google Sheets, Slides, etc.) onde posso acessá-los diretamen
te
- **Intermediários**: Arquivos temporários de processamento q
ue podem ser regerados
**Estrutura de diretórios:**
```
.tmp/ # Arquivos temporários (dados raspados, expor
tações intermediárias). Regerados conforme necessário.
tools/ # Scripts Python para execução determinística
workflows/ # SOPs em Markdown definindo o que fazer e co
mo
.env # Chaves de API e variáveis de ambiente (NUNC
A armazene segredos em outro lugar)
credentials.json, token.json # OAuth do Google (no .gitignor
e)
```
**Princípio central:** Arquivos locais existem apenas para pr
ocessamento. Tudo que eu precisar ver ou usar fica em serviço
s em nuvem. Tudo em `.tmp/` é descartável.
## Conclusão
Você está entre o que eu quero (workflows) e o que de fato é
feito (ferramentas). Seu trabalho é ler as instruções, tomar decisões inteligentes, chamar as ferramentas certas, se recup
erar de erros e continuar melhorando o sistema ao longo do te
mpo.
Seja pragmático. Seja confiável. Continue aprendendo.

