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
    trechos = buscar_contexto(f"{titulo} {descricao}", top_k=3)
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


PROMPT_COLETA_TEMPLATE = """Você é um assistente de abertura de chamados de suporte técnico de TI,
conversando diretamente com o usuário para entender o problema dele antes de abrir o chamado.

Seu trabalho é ANALISAR de verdade o que o usuário escreveu — não seguir um roteiro fixo de
perguntas genéricas. Baseado no que ele já disse, identifique especificamente o que ainda falta
saber para abrir um chamado completo e útil para quem for atender. Use o contexto abaixo (trechos
da base de conhecimento da empresa) apenas como referência do tipo de detalhe que costuma importar
para esse tipo de problema — não pergunte nada que não faça sentido pro que foi relatado.

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
- Faça UMA pergunta por vez, curta, direta e em português.
- Finalize assim que tiver informação suficiente para alguém entender e resolver o problema sem
  precisar perguntar o básico de novo — não precisa ser exaustivo, use bom senso. Geralmente 2 a 4
  perguntas bem direcionadas já bastam se forem as perguntas certas.

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

Responda SEMPRE em JSON, sem nenhum texto fora do JSON, em um dos dois formatos:

Se ainda precisar perguntar algo (inclusive para esclarecer uma inconsistência):
{{"acao": "perguntar", "mensagem": "sua pergunta aqui"}}

Se já tiver informação suficiente para abrir o chamado:
{{"acao": "finalizar", "titulo": "título curto do chamado (até 8 palavras)", "descricao": "descrição completa e organizada do problema, reunindo todos os detalhes específicos coletados na conversa"}}

Exemplo de resposta ao perguntar (siga esse formato SEMPRE, nunca escreva a pergunta fora do JSON):
{{"acao": "perguntar", "mensagem": "Você recebe alguma mensagem de erro ao tentar conectar?"}}
"""


def conversar_coleta(historico, forcar_finalizar=False):
    texto_usuario_ate_agora = " ".join(m["content"] for m in historico if m["role"] == "user")
    trechos = buscar_contexto(texto_usuario_ate_agora, top_k=3) if texto_usuario_ate_agora else []
    contexto = "\n\n---\n\n".join(t["conteudo"] for t in trechos) if trechos else "(nenhum contexto específico ainda)"

    prompt_sistema = PROMPT_COLETA_TEMPLATE.format(contexto=contexto)
    mensagens = [{"role": "system", "content": prompt_sistema}] + historico

    if forcar_finalizar:
        mensagens.append({
            "role": "system",
            "content": "Finalize AGORA a coleta com as informações que você já tem, "
                       "mesmo que incompletas. Responda apenas com o JSON de finalizar."
        })

    resposta = ollama.chat(model=MODELO, messages=mensagens, format="json")
    texto_resposta = resposta["message"]["content"]

    resultado = _extrair_json(texto_resposta)

    if resultado is None:
        print("Aviso: coleta não devolveu JSON válido. Resposta bruta:")
        print(texto_resposta)
        if forcar_finalizar:
            mensagens_usuario = [m["content"] for m in historico if m["role"] == "user"]
            resultado = {
                "acao": "finalizar",
                "titulo": (mensagens_usuario[0][:60] if mensagens_usuario else "Chamado sem título"),
                "descricao": " ".join(mensagens_usuario) or texto_resposta.strip(),
            }
        else:
            resultado = {"acao": "perguntar", "mensagem": texto_resposta.strip()}

    resultado.setdefault("acao", "perguntar")
    if resultado["acao"] == "finalizar":
        resultado.setdefault("titulo", "Chamado sem título definido")
        resultado.setdefault("descricao", " ".join(m["content"] for m in historico if m["role"] == "user"))
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