# Plano de Agentes de IA — Uso Pessoal e Familiar
**Escopo:** agenda, marketing (Instagram), notícias, finanças/IR, e código. Dois computadores (Linux + Windows), arquitetura híbrida cloud + local.
**Data de referência:** agosto/2026

---

## 1. Resumo executivo — a decisão

| Camada | Escolha | Por quê |
|---|---|---|
| **Modelo cloud (orquestrador principal)** | **Claude Code** (assinatura Pro ou Max) | Já é sua inclinação, tem o melhor suporte a MCP (o "USB" de agentes) do mercado, roda igual em Linux e Windows, e cobre coding + orquestração de todas as outras tarefas na mesma ferramenta. |
| **Modelo local (dados sensíveis)** | **Não é o Kimi K2.6 "puro"** — ver seção 3. Recomendo **Qwen3 (8B–30B) ou Devstral Small 24B via Ollama**, com **Kimi K2.7 Code via Ollama `:cloud`** como opção intermediária *não-100%-local* para tarefas de código pesadas. | O Kimi K2.6/K2.7 "de verdade" (pesos completos) precisa de ~350 GB de RAM+VRAM — inviável em hardware doméstico. O tag `kimi-k2.6:cloud` do Ollama parece local mas **na verdade roda nos servidores da Moonshot AI** — ou seja, não resolve seu requisito de privacidade. Isso muda a arquitetura que você propôs, e é a correção mais importante deste plano. |
| **Orquestração** | Claude Code como "maestro", chamando ferramentas MCP e, quando necessário, delegando para o modelo local via um MCP/CLI ponte. | Mantém uma interface única para você e sua esposa, mas permite trocar peças (modelo cloud, modelo local, ferramentas) sem reescrever tudo — atende seu requisito de flexibilidade. |
| **SO** | Claude Code roda em Linux nativamente e em Windows (nativo ou via WSL2). Ollama roda nos dois. | Mesma stack nos dois computadores, reduz manutenção. |

**Regra de ouro de privacidade que vamos seguir a partir daqui:** dado bancário, senha de gov.br, CPF completo, e qualquer PII vão **sempre** para o modelo local ou ficam fora de qualquer modelo — nunca trafegam para a nuvem. Detalhamos isso na seção 5.

---

## 2. Por que Claude Code para a camada cloud/orquestração

- **MCP nativo:** Claude Code é hoje o cliente com o ecossistema MCP mais maduro — há servidores prontos (ou fáceis de hospedar) para Google Calendar, Instagram/Meta Graph API, Gmail, Google Drive, e ferramentas de terminal/código. Isso é o que viabiliza "um agente, várias tarefas" sem você programar cada integração do zero.
- **Coding:** é o uso principal do produto — terminal, VS Code, JetBrains, contexto de até 1M tokens, e "Agent Teams" para tarefas paralelas.
- **Multiplataforma real:** funciona em Linux e Windows sem mudar de produto — importante porque você e sua esposa usam SOs diferentes.
- **Custo prático:** um plano **Pro (~US$20/mês)** cobre uso leve e diário; se o uso for pesado (várias horas de agente por dia), o **Max 5x (~US$100/mês)** evita ficar esbarrando em limite de sessão. Dá para começar em Pro e migrar depois — baixo compromisso inicial.
- **Contraponto honesto:** Claude Code está na nuvem da Anthropic. Qualquer coisa que você mandar para ele (mesmo em uso de código) passa pelos servidores da Anthropic. Isso é aceitável para: agenda, rascunho de posts, leitura de notícias, código genérico. **Não** é aceitável, na sua definição de privacidade, para: números de conta, extratos bancários, senha de gov.br, dados médicos ligados a CPF.

*(Verifique preços atuais em claude.com/pricing antes de assinar — mudam com frequência.)*

---

## 3. Por que (e como) o modelo local — a parte que precisa de ajuste

Sua ideia de "Claude Code + Kimi no Ollama" está certa na filosofia (híbrido cloud/local), mas precisa de um ajuste técnico importante:

### O problema com "Kimi no Ollama" como você imaginou
- Kimi K2.6/K2.7 tem ~1 trilhão de parâmetros (mesmo "ativando" só ~32B por token). Para rodar os pesos completos localmente com qualidade plena, hoje se precisa de **~350 GB de RAM+VRAM combinados** — isso é hardware de servidor, não um PC doméstico.
- O Ollama oferece um atalho, o tag `kimi-k2.6:cloud`, que parece "local" (aparece no `ollama list`) mas **na verdade só encaminha sua requisição para os servidores da Moonshot AI** na China. Ou seja: **não é privado**. Para tarefas de finanças/PII isso anula exatamente o motivo pelo qual você queria um modelo local.

### O que recomendo para a camada realmente local e privada
Para hardware doméstico (mesmo um notebook razoável com 16–32 GB de RAM, idealmente com GPU de 8–24 GB VRAM):

| Modelo | Tamanho | Uso recomendado | Observação |
|---|---|---|---|
| **Qwen3 8B** | ~5 GB VRAM | Máquinas mais simples (8 GB RAM), tarefas de PII leves | Melhor custo-benefício para hardware modesto |
| **Qwen3 27B/30B** | ~20 GB VRAM (ou CPU com RAM suficiente, mais lento) | Análise financeira, organização de dados de IR, leitura de extratos | Bom equilíbrio qualidade/hardware |
| **Devstral Small 24B** | ~16–20 GB VRAM | Coding local privado (ex.: código que toca dados do projeto de fraude) | Focado em fluxos agênticos de código |
| **Kimi K2.7 Code (`:cloud`)** | N/A (roda remoto) | Coding pesado **não sensível**, quando quiser qualidade topo de linha sem gastar tokens Claude | **Não usar para dados privados** — é cloud disfarçado de local |

**Decisão prática:** compre/reaproveite uma GPU de 12–24 GB (ex.: RTX 4070/4080/4090 ou equivalente) em uma das duas máquinas — a Linux, provavelmente a sua — e use-a como "servidor" Ollama local que ambos os computadores podem acessar na rede doméstica (Ollama expõe uma API local em `localhost:11434`, que pode ser exposta na LAN com `OLLAMA_HOST=0.0.0.0`). Isso evita comprar duas GPUs.

Se não quiser investir em GPU agora: rode Qwen3 8B em CPU mesmo (mais lento, mas funcional) até decidir se vale o investimento.

---

## 4. Mapeamento de tarefas → modelo → ferramenta

| Tarefa | Modelo | Onde roda | Ferramenta/integração |
|---|---|---|---|
| Agendar reuniões no Google Calendar | Claude Code (cloud) | Ambos os PCs | MCP do Google Calendar (OAuth, sem senha compartilhada com o modelo) |
| Criar posts de marketing para Instagram | Claude Code (cloud) | Ambos | MCP oficial da Meta (`mcp.meta.com/ads/<business-id>`) ou MCP de Instagram Graph API — requer conta Business/Creator |
| Coletar notícias de várias fontes | Claude Code (cloud) + busca web | Ambos | Ferramenta de busca web nativa do Claude Code, RSS feeds |
| Organizar/categorizar despesas para o Imposto de Renda | **Modelo local** (Qwen3) | PC Linux (servidor local) | Extratos exportados manualmente (CSV/OFX) — nunca login automatizado no banco |
| Preparar rascunho de dados para a declaração pré-preenchida (Receita Saúde já integra isso automaticamente) | **Modelo local** | Local | Leitura de PDFs/recibos locais; envio final sempre manual, feito por você no app oficial |
| Código para o projeto de detecção de fraude (dados com PII) | **Modelo local** (Devstral/Qwen3) | Local | Ambiente isolado, sem chamadas de API externas nos dados reais |
| Código genérico (não sensível) | Claude Code (cloud) | Ambos | Terminal / VS Code / JetBrains |

---

## 5. Privacidade e segurança — os limites que não vamos cruzar

Isso é importante o suficiente para detalhar antes da instalação:

1. **Gov.br e Receita Federal:** não existe (e não deveria existir) uma API pública para automação de terceiros logarem na sua conta gov.br ou submeterem sua declaração de IR por você. A própria Receita Federal alerta publicamente que **nunca** pede senha bancária ou de gov.br por nenhum canal — qualquer ferramenta que peça essas credenciais para "automatizar" é, na prática, um vetor de fraude, mesmo que você mesmo esteja programando. **Recomendação:** o agente (local) organiza e categoriza dados (recibos, extratos), mas o login no e-CAC / app "Meu Imposto de Renda" e o envio final da declaração continuam sendo feitos manualmente por você, com seu segundo fator (conta prata/ouro).
2. **Dados bancários:** o caminho regulado é o **Open Finance Brasil**, mas ele foi desenhado para instituições credenciadas pelo Banco Central (bancos, fintechs, software houses homologadas) — não é prático nem necessário um usuário individual se credenciar. Para uso doméstico: exporte extratos em CSV/OFX pelo app do banco e processe **localmente**. Não dê ao agente sua senha do internet banking, nem para o modelo local.
3. **Instagram/Meta:** use uma conta Business/Creator com token OAuth oficial (MCP oficial da Meta ou um MCP de terceiros com boa reputação). Nunca compartilhe a senha da conta pessoal com nenhum agente.
4. **LGPD:** como isso envolve dados pessoais seus e da sua esposa, trate qualquer armazenamento de histórico/log do agente (mesmo local) como dado sensível — criptografe o disco (LUKS no Linux, BitLocker no Windows) onde os dados financeiros/IR ficarem.
5. **Regra prática:** antes de qualquer tarefa nova, pergunte "isso envolve senha, número de conta, CPF completo ou dado de saúde vinculado a nome?" → se sim, vai para o modelo local, nunca para o Claude Code (cloud).

---

## 6. Guia passo a passo — do zero à primeira automação

### Etapa 0 — Levantamento de hardware (antes de instalar qualquer coisa)
- No PC Linux: rode `nvidia-smi` (se GPU NVIDIA) ou verifique RAM total (`free -h`). Isso define qual tamanho de modelo local dá para rodar.
- Decida qual máquina será o "servidor Ollama" da casa (recomendo a Linux, se tiver a melhor GPU/RAM).

### Etapa 1 — Conta e assinatura Claude Code
1. Crie conta em **claude.ai** (ou já use a existente).
2. Assine o plano **Pro** para começar (dá para trocar para Max depois sem perda de configuração).
3. Instale o Claude Code:
   - **Linux:** `curl -fsSL https://claude.ai/install.sh | bash` (ou via npm: `npm install -g @anthropic-ai/claude-code`) — confirme o comando atual na documentação, pois muda.
   - **Windows (sua esposa):** instale via o instalador nativo do Claude Code para Windows, ou rode dentro do WSL2 se preferir um ambiente tipo Linux.
4. Rode `claude` no terminal, autentique com a conta Anthropic, faça um teste simples: "liste os arquivos desta pasta".

### Etapa 2 — Instalar e configurar o Ollama (camada local/privada)
1. **Linux (servidor):**
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:8b        # modelo leve para começar
   ollama pull devstral-small  # coding local, se hardware permitir
   ```
2. Para permitir acesso da máquina Windows na rede local:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```
   (configure isso como serviço systemd para persistir após reiniciar; restrinja por firewall só à sua rede doméstica).
3. **Windows:** instale o Ollama para Windows (opcional, só se quiser rodar modelos locais também nessa máquina, além de acessar o servidor Linux).
4. Teste: `ollama run qwen3:8b "resuma este texto: ..."`.

### Etapa 3 — Conectar Google Calendar via MCP
1. No Google Cloud Console, crie um projeto e habilite a Calendar API; gere credenciais OAuth (client ID/secret) — isso fica só com você, nunca "solto" em texto para o modelo.
2. Configure o MCP server de Google Calendar no Claude Code (via `claude mcp add` ou editando o arquivo de configuração MCP), apontando para essas credenciais.
3. Teste: peça ao Claude Code "crie um evento teste amanhã às 10h no meu calendário" e confirme que aparece no Google Calendar.

### Etapa 4 — Conectar Instagram (marketing)
1. Transforme (ou confirme) a conta do Instagram como **Business ou Creator**, vinculada a uma Página do Facebook.
2. Use o **MCP oficial da Meta** (`mcp.meta.com/ads/<business-id>`) via OAuth padrão de negócios — evita o processo antigo de App Review de 4–6 semanas.
3. Como alternativa, avalie MCPs de terceiros bem avaliados (ex.: cobertura completa do Graph API v25) se precisar de recursos que o oficial ainda não cobre.
4. Teste: peça para o Claude Code "gerar 3 opções de legenda para um post sobre [assunto]" (sem publicar ainda) e depois "publicar um post de teste" numa conta de testes antes de usar a conta real.

### Etapa 5 — Notícias
1. Configure uma lista de fontes confiáveis (RSS ou sites específicos).
2. Use a busca web nativa do Claude Code / peça um resumo diário: "traga as 5 principais notícias de [tema] de hoje, com fonte".
3. Opcional: crie uma rotina agendada (cron no Linux, Agendador de Tarefas no Windows) que dispara o Claude Code em modo não-interativo (`claude -p "..."`) todo dia de manhã.

### Etapa 6 — Finanças e IR (camada local)
1. Exporte extratos bancários em CSV/OFX manualmente pelo app/site do banco (nunca automatize login).
2. Aponte o modelo local (via Ollama, usando uma interface como **Open WebUI** ou um script simples) para ler esses arquivos localmente e categorizar despesas (ex.: saúde, educação, dedutíveis).
3. Para Receita Saúde: como profissional de saúde ou paciente, os recibos já ficam automaticamente na declaração pré-preenchida — o agente local pode ajudar a **conferir** esses valores contra seus próprios registros, mas o envio da declaração continua manual, por você, no programa oficial (PGD IRPF) ou app "Meu Imposto de Renda".

### Etapa 7 — Coding
- Código sensível (projeto de fraude, com dados reais de `V1`–`V28`/`Amount`/`Class` ou qualquer dado real de cliente): trabalhe com o **modelo local** (Devstral ou Qwen3) rodando no ambiente isolado, sem enviar os dados reais para a nuvem — use dados sintéticos/anonimizados se precisar mostrar exemplos ao Claude Code na nuvem para pedir ajuda de arquitetura.
- Código geral: Claude Code normalmente, no terminal ou IDE.

### Etapa 8 — Primeiros testes (checklist)
- [ ] Claude Code autenticado e respondendo em ambas as máquinas
- [ ] Ollama servindo modelo local acessível pela rede doméstica
- [ ] Evento de teste criado no Google Calendar via agente
- [ ] Post de teste gerado (e opcionalmente publicado) no Instagram via MCP
- [ ] Resumo de notícias gerado com sucesso
- [ ] Extrato de teste (dado fictício) categorizado pelo modelo local, sem sair da rede local
- [ ] Script de coding rodando localmente sem chamadas externas quando lidar com dado sensível

---

## 7. Flexibilidade — como não ficar preso a nenhum fornecedor

- **Camada de orquestração separada da escolha de modelo:** sempre que possível, use MCP (padrão aberto) em vez de integrações proprietárias — assim, se trocar o Claude Code por outro cliente MCP no futuro, as integrações (Calendar, Instagram) continuam funcionando.
- **Modelos locais são intercambiáveis por padrão:** o Ollama usa a mesma interface para qualquer modelo (`ollama run <modelo>`) — trocar Qwen3 por outro modelo (ex.: um lançamento futuro melhor) é só um `ollama pull` novo, sem mudar o resto do sistema.
- **Revisão trimestral recomendada:** este é um campo que muda a cada poucos meses (como você mesmo notou). Reserve 30 minutos a cada 3 meses para checar: (1) se saiu um modelo local melhor para o seu hardware, (2) se o Claude Code ainda é a melhor opção cloud ou se vale testar alternativas, (3) se os MCPs usados continuam mantidos.

---

## 8. Estimativa de custo mensal (ordem de grandeza, ago/2026)

| Item | Custo aproximado |
|---|---|
| Claude Pro (2 pessoas, ou 1 conta compartilhada com cautela) | US$20–40/mês |
| Ollama + modelos locais | US$0 (só eletricidade/hardware já existente) |
| GPU dedicada (se comprar, custo único) | US$400–1200 (uma vez) |
| MCP de Instagram/Meta (planos gratuitos costumam cobrir uso pessoal) | US$0–20/mês |

Comece em Pro; migre para Max ($100/mês) só se o uso diário de código/agentes esbarrar frequentemente no limite de sessão.

---

## 9. Riscos e avisos finais

- Não automatize login em gov.br, e-CAC ou internet banking — isso é tecnicamente possível via scraping, mas viola os termos de uso e cria um vetor real de fraude/phishing sobre seus próprios dados.
- Verifique sempre a documentação oficial (claude.com/docs, ollama.com, developers.facebook.com) antes de instalar, pois comandos e nomes de modelos mudam rápido — os comandos acima são um ponto de partida, não copie-e-cole sem checar a versão atual.
- Isto não é aconselhamento jurídico ou financeiro — para dúvidas específicas sobre obrigatoriedade de declaração, deduções, ou LGPD aplicada ao seu caso, vale confirmar com um contador ou advogado.
