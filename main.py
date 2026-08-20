from ia_engine import classificar_chamado
from database import salvar_chamado, criar_tabela_usuarios, criar_tabela_chamados


def abrir_chamado(titulo, descricao):
    print(f"\n>>> Novo chamado: '{titulo}'")

    resultado = classificar_chamado(titulo, descricao)

    # A classificação devolve uma versão refinada de título/descrição;
    # usamos ela quando disponível, com o texto original como reserva.
    titulo_final = resultado.get("titulo_resumido") or titulo
    descricao_final = resultado.get("descricao_padronizada") or descricao

    print(f"Categoria sugerida: {resultado.get('categoria', 'N/A')}")
    print(f"Urgência sugerida: {resultado.get('urgencia', 'N/A')}")
    print(f"SLA resposta: {resultado.get('tempo_sla_resposta', 'N/A')} | SLA resolução: {resultado.get('tempo_sla_resolucao', 'N/A')}")
    print(f"Equipe destino: {resultado.get('equipe_destino', 'N/A')}")
    print(f"Título final (IA): {titulo_final}")
    print(f"Descrição final (IA): {descricao_final}")
    print(f"Confiabilidade (autoavaliação da IA): {resultado.get('confiabilidade', 'N/A')}")
    print(f"Arquivos consultados (RAG): {resultado.get('arquivos_consultados', [])}")

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
    print(f"Chamado salvo no banco com id {chamado_id}")


if __name__ == "__main__":
    criar_tabela_usuarios()
    criar_tabela_chamados()

    abrir_chamado(
        titulo="Impressora não liga",
        descricao="a impressora do 3º andar não acende nenhuma luz, já tentei trocar a tomada",
    )

    abrir_chamado(
        titulo="Sistema travando",
        descricao="o sistema de vendas está fechando sozinho toda vez que eu tento emitir uma nota",
    )