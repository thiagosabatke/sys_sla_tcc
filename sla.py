import json
from datetime import datetime, time, timedelta

MATRIZ_SLA_MINUTOS = {
    "Critica": {"resposta": 15, "resolucao": 240}, "Alta": {"resposta": 60, "resolucao": 480},
    "Media": {"resposta": 240, "resolucao": 1440}, "Baixa": {"resposta": 480, "resolucao": 4320},
}
LIMIAR_RISCO = 0.8
CONFIGURACAO_PADRAO = {"usar_horario_comercial": True, "dias_uteis": [0, 1, 2, 3, 4], "hora_inicio": "08:00", "hora_fim": "18:00", "limiar_risco": LIMIAR_RISCO, "horas_fechamento_automatico": 72, "matriz": MATRIZ_SLA_MINUTOS}
CORES_SLA = {"Dentro do prazo": "#15803d", "Em risco": "#a16207", "Violado": "#dc2626", "Cumprido": "#15803d", "Pausado": "#5b3f88", "Não aplicável": "#50535a"}


def _ausente(valor):
    """Reconhece None, NaN e NaT sem depender do pandas."""
    if valor is None:
        return True
    try:
        return bool(valor != valor)
    except (TypeError, ValueError):
        return False


def normalizar_configuracao(configuracao=None):
    if isinstance(configuracao, str):
        try: configuracao = json.loads(configuracao)
        except json.JSONDecodeError: configuracao = None
    # Ao transformar chamados em DataFrame, campos JSON ausentes podem virar NaN
    # (um float). Configurações inválidas devem usar o padrão de SLA.
    if not isinstance(configuracao, dict):
        configuracao = None
    configuracao = configuracao or {}
    matriz = configuracao.get("matriz") or MATRIZ_SLA_MINUTOS
    return {"usar_horario_comercial": bool(configuracao.get("usar_horario_comercial", True)), "dias_uteis": sorted({int(d) for d in configuracao.get("dias_uteis", [0, 1, 2, 3, 4]) if 0 <= int(d) <= 6}), "hora_inicio": str(configuracao.get("hora_inicio", "08:00"))[:5], "hora_fim": str(configuracao.get("hora_fim", "18:00"))[:5], "limiar_risco": float(configuracao.get("limiar_risco", LIMIAR_RISCO)), "horas_fechamento_automatico": int(configuracao.get("horas_fechamento_automatico", 72)), "matriz": matriz}


def _hora(valor):
    h, m = map(int, valor.split(":")); return time(h, m)


def _janela(atual, config):
    config = normalizar_configuracao(config)
    if atual.weekday() not in config["dias_uteis"]: return None
    inicio, fim = _hora(config["hora_inicio"]), _hora(config["hora_fim"])
    return None if fim <= inicio else (datetime.combine(atual.date(), inicio), datetime.combine(atual.date(), fim))


def adicionar_minutos_uteis(inicio, minutos, configuracao=None):
    restante, atual, config = max(0, float(minutos)), inicio, normalizar_configuracao(configuracao)
    if not config["usar_horario_comercial"]: return inicio + timedelta(minutes=restante)
    while restante > 0:
        janela = _janela(atual, config)
        if not janela or atual >= janela[1]:
            atual = datetime.combine((atual + timedelta(days=1)).date(), time.min); continue
        atual = max(atual, janela[0]); consumo = min(restante, (janela[1] - atual).total_seconds() / 60)
        atual += timedelta(minutes=consumo); restante -= consumo
    return atual


def minutos_uteis_entre(inicio, fim, configuracao=None):
    if _ausente(inicio) or _ausente(fim): return 0
    if fim < inicio: return -minutos_uteis_entre(fim, inicio, configuracao)
    total, atual, config = 0.0, inicio, normalizar_configuracao(configuracao)
    if not config["usar_horario_comercial"]: return (fim - inicio).total_seconds() / 60
    while atual.date() <= fim.date():
        janela = _janela(atual, config)
        if janela:
            inicio_trecho, fim_trecho = max(atual, janela[0]), min(fim, janela[1])
            if fim_trecho > inicio_trecho: total += (fim_trecho - inicio_trecho).total_seconds() / 60
        atual = datetime.combine((atual + timedelta(days=1)).date(), time.min)
    return total


def calcular_prazos(criado_em, urgencia, configuracao=None):
    config = normalizar_configuracao(configuracao); minutos = config["matriz"].get(urgencia, config["matriz"]["Media"])
    return adicionar_minutos_uteis(criado_em, minutos["resposta"], config), adicionar_minutos_uteis(criado_em, minutos["resolucao"], config)


def _prazo_efetivo(prazo, pausado, pausado_em, agora, config):
    total = 0 if _ausente(pausado) else pausado
    if not _ausente(pausado_em): total += minutos_uteis_entre(pausado_em, agora, config)
    return adicionar_minutos_uteis(prazo, total, config)


def avaliar_metrica(criado_em, prazo, concluido_em, pausado_em, tempo_pausado_min, configuracao=None, agora=None):
    agora, config = agora or datetime.now(), normalizar_configuracao(configuracao)
    if _ausente(prazo): return {"status": "Dentro do prazo", "prazo_efetivo": None, "minutos_restantes": None}
    if _ausente(criado_em): return {"status": "Não aplicável", "prazo_efetivo": None, "minutos_restantes": None}
    concluido_em = None if _ausente(concluido_em) else concluido_em
    pausado_em = None if _ausente(pausado_em) else pausado_em
    efetivo = _prazo_efetivo(prazo, tempo_pausado_min, pausado_em, agora, config); restantes = minutos_uteis_entre(agora, efetivo, config)
    if pausado_em and not concluido_em: return {"status": "Pausado", "prazo_efetivo": efetivo, "minutos_restantes": restantes}
    if concluido_em: return {"status": "Cumprido" if concluido_em <= efetivo else "Violado", "prazo_efetivo": efetivo, "minutos_restantes": None}
    total = minutos_uteis_entre(criado_em, prazo, config); status = "Violado" if restantes < 0 else "Em risco" if total > 0 and restantes <= total * (1 - config["limiar_risco"]) else "Dentro do prazo"
    return {"status": status, "prazo_efetivo": efetivo, "minutos_restantes": restantes}


def status_sla(chamado, agora=None):
    if chamado.get("status") == "Cancelado":
        estado = {"status": "Não aplicável", "prazo_efetivo": None, "minutos_restantes": None}; return {"resposta": estado, "resolucao": estado}
    configuracao = chamado.get("sla_configuracao") or {"usar_horario_comercial": False}
    dados = (chamado["criado_em"], chamado.get("pausado_em"), chamado.get("tempo_pausado_min") or 0, configuracao, agora)
    return {"resposta": avaliar_metrica(dados[0], chamado.get("prazo_resposta"), chamado.get("primeira_resposta_em"), *dados[1:]), "resolucao": avaliar_metrica(dados[0], chamado.get("prazo_resolucao"), chamado.get("resolvido_em"), *dados[1:])}


def pior_status(estado):
    for nivel in ["Violado", "Em risco", "Pausado", "Dentro do prazo", "Cumprido", "Não aplicável"]:
        if nivel in (estado["resposta"]["status"], estado["resolucao"]["status"]): return nivel
    return "Dentro do prazo"


def formatar_tempo_restante(minutos):
    if minutos is None: return ""
    m = int(abs(minutos)); d, resto = divmod(m, 1440); h, m = divmod(resto, 60); partes = ([f"{d}d"] if d else []) + ([f"{h}h"] if h else []) + ([f"{m}min"] if m or not (d or h) else [])
    return ("atrasado há " if minutos < 0 else "restam ") + " ".join(partes)


def formatar_data(dt): return dt.strftime("%d/%m %H:%M") if dt else "—"
