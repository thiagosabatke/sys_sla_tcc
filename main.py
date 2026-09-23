from ia_engine import classificar_chamado
from database import salvar_chamado, criar_tabela_usuarios, criar_tabela_chamados, criar_tabela_auditoria
from observability import configurar_logging
import logging

logger = logging.getLogger(__name__)


def abrir_chamado(titulo, descricao):
    logger.info("Iniciando classificação do chamado.")

    resultado = classificar_chamado(titulo, descricao)

    titulo_final = resultado.get("titulo_resumido") or titulo
    descricao_final = resultado.get("descricao_padronizada") or descricao

    logger.info(
        "Classificação concluída: categoria=%s, urgência=%s, equipe=%s, confiança=%s.",
        resultado.get("categoria", "N/A"), resultado.get("urgencia", "N/A"),
        resultado.get("equipe_destino", "N/A"), resultado.get("confiabilidade", "N/A"),
    )

    chamado_id = salvar_chamado(
        titulo=titulo_final,
        descricao=descricao_final,
        categoria=resultado["categoria"],
        urgencia=resultado["urgencia"],
        sla_resposta=resultado.get("tempo_sla_resposta"),
        sla_resolucao=resultado.get("tempo_sla_resolucao"),
        equipe_destino=resultado.get("equipe_destino"),
        confiabilidade=resultado.get("confiabilidade"),
    )
    logger.info("Chamado #%s salvo no banco.", chamado_id)


if __name__ == "__main__":
    configurar_logging()
    criar_tabela_usuarios()
    criar_tabela_chamados()
    criar_tabela_auditoria()

    abrir_chamado(
        titulo="Impressora não liga",
        descricao="a impressora do 3º andar não acende nenhuma luz, já tentei trocar a tomada",
    )

    abrir_chamado(
        titulo="Sistema travando",
        descricao="o sistema de vendas está fechando sozinho toda vez que eu tento emitir uma nota",
    )
