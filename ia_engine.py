import os
import json
import ollama
from dotenv import load_dotenv
from rag import buscar_contexto

load_dotenv()

MODELO = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

PROMPT_SISTEMA = """Persona: Você é um Analista de Suporte de TI Sênior, especializado em ITIL 4,
gerenciamento de incidentes e Processamento de Linguagem Natural.

Tarefa: Interprete semanticamente a descrição do chamado usando o contexto (base de
conhecimento) fornecido, identifique a intenção do usuário, classifique a categoria,
a urgência, o impacto, defina os tempos de SLA consultando a matriz abaixo (NUNCA
invente um tempo fora dela), encaminhe para a equipe responsável e informe sua própria
autoavaliação de confiança na classificação.

Categorias disponíveis e equipe de destino correspondente (use exatamente este mapeamento):
- Acesso    -> equipe_destino: Suporte
- Software  -> equipe_destino: Software
- Hardware  -> equipe_destino: Hardware
- Rede      -> equipe_destino: Redes
- Outros    -> equipe_destino: Suporte

Matriz de SLA (use estes valores exatos, não crie outros):
- Crítica: tempo_sla_resposta = "15 minutos", tempo_sla_resolucao = "4 horas"
- Alta:    tempo_sla_resposta = "1 hora",      tempo_sla_resolucao = "8 horas"
- Media:   tempo_sla_resposta = "4 horas",     tempo_sla_resolucao = "24 horas"
- Baixa:   tempo_sla_resposta = "8 horas",     tempo_sla_resolucao = "72 horas"

Critério de urgência: considere o impacto no atendimento e a quantidade de usuários
afetados (ex: sistema crítico ou setor inteiro parado = Crítica/Alta; usuário
individual com alternativa disponível = Media/Baixa).

Campo "confiabilidade": isto é uma AUTOAVALIAÇÃO textual sua sobre o quão claro e
inequívoco foi o chamado para classificar (não é um cálculo estatístico). Use "Alta"
quando a descrição foi clara e objetiva, "Media" quando havia alguma ambiguidade, e
"Baixa" quando a descrição foi vaga ou incompleta.

Responda APENAS com um JSON válido, sem nenhum texto antes ou depois, neste formato exato:
{"categoria": "Acesso|Software|Hardware|Rede|Outros", "urgencia": "Baixa|Media|Alta|Critica", "tempo_sla_resposta": "...", "tempo_sla_resolucao": "...", "equipe_destino": "Suporte|Software|Hardware|Redes", "titulo_resumido": "resumo em até 5 palavras", "descricao_padronizada": "descrição técnica limpa e objetiva", "confiabilidade": "Alta|Media|Baixa"}

Exemplo:
Chamado: "Título: Não consigo imprimir. Descrição: a impressora do setor financeiro parou de funcionar, ninguém do setor consegue imprimir os boletos hoje."
Resposta: {"categoria": "Hardware", "urgencia": "Alta", "tempo_sla_resposta": "1 hora", "tempo_sla_resolucao": "8 horas", "equipe_destino": "Hardware", "titulo_resumido": "Impressora do financeiro parada", "descricao_padronizada": "Impressora do setor financeiro sem funcionamento, impedindo a emissão de boletos por todo o setor.", "confiabilidade": "Alta"}
"""


def classificar_chamado(titulo, descricao):
    trechos = buscar_contexto(f"{titulo} {descricao}", top_k=2)
    contexto = "\n\n---\n\n".join(t["conteudo"] for t in trechos)

    prompt_usuario = f"""Contexto (base de conhecimento):
{contexto}

Chamado do usuário:
Título: {titulo}
Descrição: {descricao}

Classifique este chamado."""

    resposta = ollama.chat(
        model=MODELO,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": prompt_usuario},
        ],
        format="json",
        options={"num_predict": 220},
    )

    texto_resposta = resposta["message"]["content"]

    try:
        resultado = json.loads(texto_resposta)
    except json.JSONDecodeError:

        print("Aviso: o modelo não devolveu um JSON válido. Resposta bruta:")
        print(texto_resposta)
        resultado = {
            "categoria": "Outros",
            "urgencia": "Media",
            "tempo_sla_resposta": "4 horas",
            "tempo_sla_resolucao": "24 horas",
            "equipe_destino": "Suporte",
            "titulo_resumido": titulo[:50],
            "descricao_padronizada": descricao,
            "confiabilidade": "Baixa",
            "erro_parsing": texto_resposta,
        }

    resultado["arquivos_consultados"] = [t["arquivo"] for t in trechos]

    campos_padrao = {
        "categoria": "Outros",
        "urgencia": "Media",
        "tempo_sla_resposta": "4 horas",
        "tempo_sla_resolucao": "24 horas",
        "equipe_destino": "Suporte",
        "titulo_resumido": titulo[:50],
        "descricao_padronizada": descricao,
        "confiabilidade": "Baixa",
    }
    campos_faltando = [c for c in campos_padrao if c not in resultado]
    if campos_faltando:
        print(f"Aviso: o modelo não preencheu os campos {campos_faltando}. Usando valores padrão.")
    for campo, valor_padrao in campos_padrao.items():
        resultado.setdefault(campo, valor_padrao)

    return resultado


PROMPT_COLETA_TEMPLATE = """Você é um assistente de suporte técnico de TI,
conversando diretamente com o usuário para orientar dúvidas, resolver problemas simples ou abrir chamados.

Seu trabalho é ANALISAR de verdade o que o usuário escreveu — não seguir um roteiro fixo de
perguntas genéricas. Antes de fazer uma pergunta, avalie se já há informação suficiente para
orientar o usuário, sugerir uma solução segura ou abrir um chamado útil. Use o contexto abaixo
(trechos da base de conhecimento da empresa) somente como fonte para orientações e procedimentos.

Contexto (base de conhecimento, para orientar quais detalhes são relevantes neste tipo de problema):
{contexto}

Regras:
- Leia com atenção tudo que o usuário já escreveu antes de decidir o que perguntar.
- Faça perguntas ESPECÍFICAS sobre o problema relatado, nunca perguntas genéricas que serviriam
  para qualquer chamado. Exemplos: se for impressora, pergunte qual/onde fica, se aparece alguma
  mensagem de erro, se outras pessoas também usam ela. Se for rede/internet, pergunte quais
  sites ou sistemas não abrem, se é só wifi ou cabo também, se começou depois de alguma mudança.
  Se for sistema/software, peça a mensagem de erro exata e em que momento ela aparece.
- Nunca repita uma pergunta sobre algo que o usuário já respondeu, mesmo que indiretamente.
- Faça UMA pergunta por vez, curta, direta e em português, somente se ela alterar a orientação,
  a solução ou a abertura do chamado. Não peça dados administrativos, patrimônio, localização,
  horário ou impacto se eles não forem necessários para a próxima ação.
- Não faça perguntas apenas para completar uma lista. Se equipamento/sistema afetado e sintoma já
  estiverem claros, ofereça a solução segura disponível ou finalize o chamado com o que já foi
  informado. Para abrir chamado, localização e impacto são desejáveis, mas não bloqueiam a abertura
  quando o relato já permite atendimento.
- Faça no máximo DUAS perguntas de esclarecimento para o mesmo problema. A exceção é quando uma
  informação adicional for indispensável para segurança ou para resolver uma contradição.

Pensamento crítico (importante): não aceite automaticamente tudo que o usuário disser como verdade.
Você é um analista, não um bajulador. Se algo que o usuário descrever for tecnicamente inconsistente,
contradizer o que ele mesmo disse antes, contradizer o contexto da base de conhecimento, ou parecer
improvável, questione educadamente antes de aceitar — não concorde só para ser agradável. Exemplos:
- Usuário diz que "a internet da empresa inteira caiu" mas depois menciona que só o computador dele
  está sem acesso -> pergunte se é só o computador dele ou realmente o setor/empresa toda, apontando
  a contradição.
- Usuário culpa um componente que não bate com o sintoma descrito (ex: "o monitor está com vírus")
  -> pergunte com cuidado o que o levou a essa conclusão, sem simplesmente aceitar o diagnóstico dele.
- Usuário dá uma informação vaga como se fosse certeza (ex: "com certeza é a mesma coisa de semana
  passada") -> confirme se é mesmo o mesmo problema antes de assumir isso como fato.
Seja respeitoso e nunca debochado ao questionar — o objetivo é chegar num chamado preciso, não
"vencer" uma discussão com o usuário.

Responda SEMPRE em JSON, sem nenhum texto fora do JSON, em um dos quatro formatos:

Se for uma dúvida/orientação sem falha a ser atendida, responda de forma curta e somente com base
no contexto. Não abra chamado:
{{"acao": "orientar", "mensagem": "orientação objetiva para o usuário"}}

Se ainda precisar perguntar algo (inclusive para esclarecer uma inconsistência):
{{"acao": "perguntar", "mensagem": "sua pergunta aqui"}}

Se os dados já forem suficientes e o contexto trouxer uma orientação segura, concreta e
aplicável para a situação relatada, apresente a solução antes de propor a abertura de
chamado. Só use esta ação quando a solução estiver fundamentada no contexto fornecido;
não invente procedimentos, permissões ou diagnósticos. A solução deve ser curta, ter
passos numerados e, quando existir no contexto, incluir cuidados importantes:
{{"acao": "solucionar", "mensagem": "orientação curta para o usuário", "solucao": "1. Primeiro passo\\n2. Segundo passo", "titulo": "título curto do chamado (até 8 palavras)", "descricao": "descrição completa e organizada do problema, reunindo todos os detalhes específicos coletados na conversa"}}

Se já tiver informação suficiente para abrir o chamado:
{{"acao": "finalizar", "titulo": "título curto do chamado (até 8 palavras)", "descricao": "descrição completa e organizada do problema, reunindo todos os detalhes específicos coletados na conversa"}}

Exemplo de resposta ao perguntar (siga esse formato SEMPRE, nunca escreva a pergunta fora do JSON):
{{"acao": "perguntar", "mensagem": "Você recebe alguma mensagem de erro ao tentar conectar?"}}
"""


PROMPT_INTENCAO = """Você é o ponto inicial de atendimento de uma central de suporte de TI.
Classifique somente a última mensagem do usuário em uma destas intenções:

- "duvida": a pessoa quer uma orientação, explicação, instrução ou confirmação e não
  relata uma falha que precise de atendimento.
- "problema": a pessoa relata uma falha, indisponibilidade, erro, solicitação de reparo
  ou qualquer situação que possa exigir abertura de chamado.

Considere o significado da mensagem, não apenas a presença de uma interrogação. Quando
houver dúvida razoável, escolha "problema" para que a central colete os dados necessários.

Responda APENAS com JSON válido neste formato:
{{"intencao": "duvida|problema"}}
"""


PROMPT_RESPOSTA_DUVIDA = """Você é um assistente de suporte de TI. Responda à dúvida do usuário
de modo curto, objetivo e em português, usando exclusivamente o contexto fornecido quando
ele trouxer uma orientação específica. Não invente procedimentos, permissões ou políticas.
Se o contexto não for suficiente, explique isso e peça um detalhe que permita orientar melhor.
Não abra chamado e não diga que ele foi aberto.
"""


def _intencao_por_fallback(mensagem):
    """Retorna uma classificação conservadora se o modelo não responder em JSON válido."""
    texto = mensagem.lower().strip()
    marcadores_problema = (
        "não consigo", "nao consigo", "não funciona", "nao funciona", "erro",
        "parou", "falha", "caiu", "bloqueado", "lento", "problema", "sem acesso",
    )
    if any(marcador in texto for marcador in marcadores_problema):
        return "problema"
    return "duvida" if "?" in texto else "problema"


def identificar_intencao(mensagem):
    """Classifica a mensagem inicial como dúvida ou problema para direcionar o atendimento."""
    resposta = ollama.chat(
        model=MODELO,
        messages=[
            {"role": "system", "content": PROMPT_INTENCAO},
            {"role": "user", "content": mensagem},
        ],
        format="json",
    )
    resultado = _extrair_json(resposta["message"]["content"])
    intencao = (resultado or {}).get("intencao", "").lower().strip()
    if intencao not in {"duvida", "problema"}:
        intencao = _intencao_por_fallback(mensagem)
    return intencao


def responder_duvida(mensagem):
    """Busca a base de conhecimento e responde sem iniciar uma abertura de chamado."""
    trechos = buscar_contexto(mensagem, top_k=3)
    contexto = "\n\n---\n\n".join(t["conteudo"] for t in trechos)
    if not contexto:
        contexto = "(Não há orientação específica na base de conhecimento.)"

    resposta = ollama.chat(
        model=MODELO,
        messages=[
            {"role": "system", "content": PROMPT_RESPOSTA_DUVIDA},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nDúvida do usuário:\n{mensagem}"},
        ],
    )
    texto = resposta["message"]["content"].strip()
    return texto or "Não consegui elaborar uma orientação agora. Pode reformular sua dúvida?"


def conversar_coleta(historico):
    texto_usuario_ate_agora = " ".join(m["content"] for m in historico if m["role"] == "user")
    # Um artigo mais aderente costuma conter o procedimento completo; limitar o
    # contexto evita atrasar cada turno com conteúdo que não muda a decisão.
    trechos = buscar_contexto(texto_usuario_ate_agora, top_k=1) if texto_usuario_ate_agora else []
    contexto = "\n\n---\n\n".join(t["conteudo"] for t in trechos) if trechos else "(nenhum contexto específico ainda)"

    prompt_sistema = PROMPT_COLETA_TEMPLATE.format(contexto=contexto)
    mensagens = [{"role": "system", "content": prompt_sistema}] + historico

    resposta = ollama.chat(
        model=MODELO,
        messages=mensagens,
        format="json",
        options={"num_predict": 280},
    )
    texto_resposta = resposta["message"]["content"]

    resultado = _extrair_json(texto_resposta)

    if resultado is None:
        print("Aviso: coleta não devolveu JSON válido. Resposta bruta:")
        print(texto_resposta)
        resultado = {"acao": "perguntar", "mensagem": texto_resposta.strip()}

    resultado.setdefault("acao", "perguntar")
    if resultado["acao"] not in {"orientar", "perguntar", "solucionar", "finalizar"}:
        resultado["acao"] = "perguntar"

    if resultado["acao"] in {"solucionar", "finalizar"}:
        resultado.setdefault("titulo", "Chamado sem título definido")
        resultado.setdefault("descricao", " ".join(m["content"] for m in historico if m["role"] == "user"))
    if resultado["acao"] == "solucionar":
        resultado.setdefault("mensagem", "Com os dados informados, encontrei uma orientação que pode resolver o problema.")
        resultado.setdefault("solucao", "Não foi possível detalhar uma solução segura. Você pode abrir um chamado para atendimento.")
    elif resultado["acao"] == "orientar":
        resultado.setdefault("mensagem", "Não encontrei uma orientação específica. Pode explicar um pouco mais o que precisa?")
    else:
        resultado.setdefault("mensagem", "Pode detalhar um pouco mais o problema?")

    return resultado


def _extrair_json(texto):
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim != -1 and fim > inicio:
        try:
            return json.loads(texto[inicio:fim + 1])
        except json.JSONDecodeError:
            pass

    return None


if __name__ == "__main__":
    exemplo = classificar_chamado(
        titulo="Internet não funciona",
        descricao="não consigo acessar nenhum site desde hoje de manhã, o wifi conecta mas não navega",
    )
    print(json.dumps(exemplo, indent=2, ensure_ascii=False))
