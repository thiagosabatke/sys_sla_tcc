from ia_engine import classificar_chamado
from database import salvar_chamado, criar_tabela


def abrir_chamado(titulo, descricao):
    print(f"\n>>> Novo chamado: '{titulo}'")

    resultado = classificar_chamado(titulo, descricao)

    print(f"Categoria sugerida: {resultado.get('categoria', 'N/A')}")
    print(f"Urgência sugerida: {resultado.get('urgencia', 'N/A')}")
    print(f"SLA resposta: {resultado.get('tempo_sla_resposta', 'N/A')} | SLA resolução: {resultado.get('tempo_sla_resolucao', 'N/A')}")
    print(f"Equipe destino: {resultado.get('equipe_destino', 'N/A')}")
    print(f"Título resumido (IA): {resultado.get('titulo_resumido', 'N/A')}")
    print(f"Descrição padronizada (IA): {resultado.get('descricao_padronizada', 'N/A')}")
    print(f"Confiabilidade (autoavaliação da IA): {resultado.get('confiabilidade', 'N/A')}")
    print(f"Arquivos consultados (RAG): {resultado.get('arquivos_consultados', [])}")

    chamado_id = salvar_chamado(
        titulo=titulo,
        descricao=descricao,
        categoria=resultado["categoria"],
        urgencia=resultado["urgencia"],
        sla_resposta=resultado.get("tempo_sla_resposta"),
        sla_resolucao=resultado.get("tempo_sla_resolucao"),
        equipe_destino=resultado.get("equipe_destino"),
        titulo_resumido=resultado.get("titulo_resumido"),
        descricao_padronizada=resultado.get("descricao_padronizada"),
        confiabilidade=resultado.get("confiabilidade"),
    )
    print(f"Chamado salvo no banco com id {chamado_id}")


if __name__ == "__main__":
    criar_tabela()

    abrir_chamado(
        titulo="Impressora não liga",
        descricao="a impressora do 3º andar não acende nenhuma luz, já tentei trocar a tomada",
    )

    abrir_chamado(
        titulo="Sistema travando",
        descricao="o sistema de vendas está fechando sozinho toda vez que eu tento emitir uma nota",
    )