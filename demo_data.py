"""Cenários sintéticos para os cadastros existentes, sem persistência ou chamadas à IA."""

from datetime import timedelta
import json
import uuid
import sla


def gerar_cenarios_demonstracao(solicitantes, analistas, quantidade, agora, configuracao,
                              para_local, para_utc, marcador, inicio_indice=0, ativos_por_usuario=None):
    if not solicitantes:
        raise ValueError("Cadastre um solicitante com permissão para abrir e consultar os próprios chamados.")
    if not analistas:
        raise ValueError("Cadastre um analista com permissão para assumir, responder e resolver chamados.")
    configuracao = sla.normalizar_configuracao(configuracao)
    ativos = dict(ativos_por_usuario or {})
    # Deixa uma vaga para uma solicitação real; os outros exemplos vão para o histórico.
    limite_ativos = max(0, configuracao["limite_chamados_ativos_por_usuario"] - 1)
    lote = uuid.uuid4().hex
    temas = [
        ("Acesso", "Suporte", "Acesso ao sistema de trabalho", "Revisão das permissões e validação do acesso."),
        ("Software", "Software", "Erro ao abrir aplicativo", "Ajuste da configuração e teste do aplicativo."),
        ("Hardware", "Hardware", "Computador com lentidão", "Verificação do equipamento e validação do desempenho."),
        ("Rede", "Redes", "Falha na conexão de rede", "Correção da conectividade e validação da conexão."),
        ("Outros", "Suporte", "Orientação sobre ferramenta de trabalho", "Orientação registrada e procedimento validado."),
    ]
    estados = ["Novo", "Em Andamento", "Em Espera", "Resolvido", "Cancelado",
               "Fechado", "Fechado", "Fechado", "Fechado", "Fechado", "Fechado", "Fechado"]
    idades = [2, 10, 48, 120, 288, 576, 960, 1440, 2160]
    registros = []
    for posicao in range(quantidade):
        indice = inicio_indice + posicao
        solicitante = solicitantes[indice % len(solicitantes)]
        analista = analistas[(indice // len(solicitantes) + indice) % len(analistas)]
        categoria, equipe, assunto, solucao = temas[indice % len(temas)]
        urgencia = ["Baixa", "Media", "Alta", "Critica"][(indice + indice // len(temas)) % 4]
        status = estados[indice % len(estados)]
        if status not in {"Fechado", "Cancelado"}:
            if ativos.get(solicitante["id"], 0) >= limite_ativos:
                status = "Fechado"
            else:
                ativos[solicitante["id"]] = ativos.get(solicitante["id"], 0) + 1
        criado = agora - timedelta(hours=idades[indice % len(idades)], minutes=indice % 45)
        prazo_resposta, prazo_resolucao = sla.calcular_prazos(para_local(criado), urgencia, configuracao)
        prazo_resposta, prazo_resolucao = para_utc(prazo_resposta), para_utc(prazo_resolucao)
        atribuido = status not in {"Novo", "Cancelado"}
        resposta = None
        if atribuido:
            resposta = max(criado + timedelta(minutes=10), min(
                prazo_resposta + timedelta(minutes=30) if indice % 4 == 0 else criado + timedelta(minutes=10),
                agora - timedelta(minutes=10)))
        concluido = status in {"Resolvido", "Fechado"}
        resolvido = None
        if concluido:
            meta = (prazo_resolucao + timedelta(hours=2) if indice % 3 == 0
                    else criado + timedelta(hours=1))
            resolvido = max(resposta, min(meta, agora - timedelta(minutes=5)))
        pausado = resposta + timedelta(minutes=5) if status == "Em Espera" else None
        departamento = solicitante.get("departamento") or "Não informado"
        titulo = f"[DEMO DASHBOARD] {assunto} — {departamento} · cenário {indice + 1:03d}"
        metadados = {"origem": marcador, "sintetico": True, "versao": 2, "lote": lote,
                     "departamento_demo": departamento}
        registro = {
            "titulo": titulo,
            "descricao": f"[Demonstração] Cenário fictício de {categoria.lower()} para o departamento {departamento}. "
                         "Relato simulado para consultar o atendimento e os indicadores.",
            "categoria": categoria, "urgencia": urgencia,
            "confiabilidade": ["Alta", "Media", "Baixa"][indice % 3], "equipe_destino": equipe,
            "categoria_ia": categoria, "urgencia_ia": urgencia, "equipe_ia": equipe,
            "metadados_ia": json.dumps(metadados, ensure_ascii=False),
            "sla_resposta": f"{configuracao['matriz'][urgencia]['resposta']} minutos",
            "sla_resolucao": f"{configuracao['matriz'][urgencia]['resolucao']} minutos",
            "sla_configuracao": json.dumps(configuracao), "status": status,
            "criado_em": criado, "atualizado_em": resolvido or pausado or resposta or criado,
            "prazo_resposta": prazo_resposta, "prazo_resolucao": prazo_resolucao,
            "primeira_resposta_em": resposta, "resolvido_em": resolvido,
            "pausado_em": pausado, "tempo_pausado_min": 0,
            "usuario_id": solicitante["id"], "analista_id": analista["id"] if atribuido else None,
            "categoria_final": categoria if concluido else None,
            "urgencia_final": urgencia if concluido else None,
            "equipe_final": equipe if concluido else None,
            "diagnostico_final": f"[Demonstração] Ocorrência simulada de {categoria.lower()}." if concluido else None,
            "solucao_final": f"[Demonstração] {solucao}" if concluido else None,
            "motivo_cancelamento": "[Demonstração] Solicitação duplicada." if status == "Cancelado" else None,
            "compartilhar_conhecimento": False, "uso_ia_autorizado_em": None,
        }
        mensagens = [(solicitante, "usuario", f"[Demonstração] Preciso de apoio com: {assunto.lower()}.", criado)]
        eventos = [(solicitante["id"], "ABERTURA", {"categoria": categoria, "urgencia": urgencia}, criado)]
        if atribuido:
            eventos.append((analista["id"], "ATRIBUICAO", {"analista_id": analista["id"]}, criado + timedelta(minutes=5)))
            mensagens.append((analista, "analista", "[Demonstração] Solicitação recebida; análise iniciada.", resposta))
        if pausado:
            eventos.append((analista["id"], "ALTERACAO_STATUS", {"de": "Em Andamento", "para": "Em Espera"}, pausado))
            mensagens.append((analista, "analista", "[Demonstração] Aguardando confirmação do solicitante.", pausado))
        if concluido:
            eventos.append((analista["id"], "RESOLUCAO", {"sintetico": True}, resolvido))
            mensagens.append((analista, "analista", f"[Demonstração] {solucao}", resolvido))
        if status == "Fechado":
            registro["atualizado_em"] = resolvido + timedelta(minutes=2)
            eventos.append((solicitante["id"], "FECHAMENTO", {"sintetico": True}, resolvido + timedelta(minutes=2)))
            mensagens.append((solicitante, "usuario", "[Demonstração] Serviço validado; atendimento encerrado.", resolvido + timedelta(minutes=2)))
        if status == "Cancelado":
            registro["atualizado_em"] = criado + timedelta(minutes=15)
            eventos.append((solicitante["id"], "CANCELAMENTO", {"sintetico": True}, criado + timedelta(minutes=15)))
        registros.append({"chamado": registro, "mensagens": mensagens, "eventos": eventos,
                          "nota": 1 + indice % 5 if status == "Fechado" else None})
    return registros
