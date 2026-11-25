"""Erros de entrada definidos pelo serviço, separados de falhas do SDK."""


class NoCriteriaAvailable(LookupError):
    """Nenhum catálogo de critérios cobre o tema pedido."""
