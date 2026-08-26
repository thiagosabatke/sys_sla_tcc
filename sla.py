from datetime import datetime, timedelta


MATRIZ_SLA_MINUTOS = {
    "Critica": {"resposta": 15, "resolucao": 240},
    "Alta": {"resposta": 60, "resolucao": 480},
    "Media": {"resposta": 240, "resolucao": 1440},
    "Baixa": {"resposta": 480, "resolucao": 4320},
}

LIMIAR_RISCO = 0.8

CORES_SLA = {
    "Dentro do prazo": "#16a34a",
    "Em risco": "#d97706",
    "Violado": "#dc2626",
    "Cumprido": "#2563eb",
    "Pausado": "#7c3aed",
    "Não aplicável": "#64748b",
}


def calcular_prazos(criado_em, urgencia):
    minutos = MATRIZ_SLA_MINUTOS.get(urgencia, MATRIZ_SLA_MINUTOS["Media"])
    prazo_resposta = criado_em + timedelta(minutes=minutos["resposta"])
    prazo_resolucao = criado_em + timedelta(minutes=minutos["resolucao"])
    return prazo_resposta, prazo_resolucao


def _prazo_efetivo(prazo, tempo_pausado_min, pausado_em, agora):
    pausa_total = tempo_pausado_min or 0
    if pausado_em:
        pausa_total += (agora - pausado_em).total_seconds() / 60
    return prazo + timedelta(minutes=pausa_total)


def avaliar_metrica(criado_em, prazo, concluido_em, pausado_em, tempo_pausado_min, agora=None):
    agora = agora or datetime.now()

    if prazo is None:
        return {"status": "Dentro do prazo", "prazo_efetivo": None, "minutos_restantes": None}

    prazo_efetivo = _prazo_efetivo(prazo, tempo_pausado_min, pausado_em, agora)

    if pausado_em and not concluido_em:
        minutos_restantes = (prazo_efetivo - agora).total_seconds() / 60
        return {"status": "Pausado", "prazo_efetivo": prazo_efetivo, "minutos_restantes": minutos_restantes}

    if concluido_em:
        status = "Cumprido" if concluido_em <= prazo_efetivo else "Violado"
        return {"status": status, "prazo_efetivo": prazo_efetivo, "minutos_restantes": None}

    minutos_restantes = (prazo_efetivo - agora).total_seconds() / 60
    duracao_total_min = (prazo_efetivo - criado_em).total_seconds() / 60

    if minutos_restantes < 0:
        status = "Violado"
    elif duracao_total_min > 0 and minutos_restantes <= duracao_total_min * (1 - LIMIAR_RISCO):
        status = "Em risco"
    else:
        status = "Dentro do prazo"

    return {"status": status, "prazo_efetivo": prazo_efetivo, "minutos_restantes": minutos_restantes}


def status_sla(chamado, agora=None):
    agora = agora or datetime.now()
    if chamado.get("status") == "Cancelado":
        nao_aplicavel = {
            "status": "Não aplicável",
            "prazo_efetivo": None,
            "minutos_restantes": None,
        }
        return {"resposta": nao_aplicavel, "resolucao": nao_aplicavel}

    resposta = avaliar_metrica(
        chamado["criado_em"],
        chamado.get("prazo_resposta"),
        chamado.get("primeira_resposta_em"),
        chamado.get("pausado_em"),
        chamado.get("tempo_pausado_min") or 0,
        agora,
    )
    resolucao = avaliar_metrica(
        chamado["criado_em"],
        chamado.get("prazo_resolucao"),
        chamado.get("resolvido_em"),
        chamado.get("pausado_em"),
        chamado.get("tempo_pausado_min") or 0,
        agora,
    )
    return {"resposta": resposta, "resolucao": resolucao}


def pior_status(estado):
    prioridade = ["Violado", "Em risco", "Pausado", "Dentro do prazo", "Cumprido", "Não aplicável"]
    estados = [estado["resposta"]["status"], estado["resolucao"]["status"]]
    for nivel in prioridade:
        if nivel in estados:
            return nivel
    return "Dentro do prazo"


def formatar_tempo_restante(minutos):
    if minutos is None:
        return ""
    minutos_abs = int(abs(minutos))
    dias, resto = divmod(minutos_abs, 1440)
    horas, mins = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if mins or not partes:
        partes.append(f"{mins}min")
    texto = " ".join(partes)
    return f"atrasado há {texto}" if minutos < 0 else f"restam {texto}"


def formatar_data(dt):
    return dt.strftime("%d/%m %H:%M") if dt else "—"
