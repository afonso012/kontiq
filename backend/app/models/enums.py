"""Valores permitidos nos campos de estado e tipo.

Guardamos como texto com CHECK na base de dados (e não como ENUM nativo do
PostgreSQL) porque é muito mais simples acrescentar valores numa migração.
"""

PLANOS = ("arranque", "gabinete", "pro")
ESTADOS_GABINETE = ("ativo", "suspenso", "cancelado")
PAPEIS_GABINETE = ("dono", "admin", "colaborador")
PAPEIS_PORTAL = ("gestor", "colaborador")

PERIODICIDADE_IVA = ("mensal", "trimestral", "nao_aplicavel")
REGIME_IVA = ("normal", "isencao_art53", "isento_art9", "pequenos_retalhistas", "outro")

CANAIS_DOCUMENTO = ("upload", "portal", "email", "api")

# Códigos de tipo de documento da AT (campo D do código QR) + estrangeira/outro.
TIPOS_DOCUMENTO = ("FT", "FS", "FR", "NC", "ND", "VD", "EST", "OUTRO")
METODOS_LEITURA = ("qr", "ia", "manual")
ESTADOS_FATURA = ("por_conferir", "conferida", "exportada", "rejeitada")

TRATAMENTOS_IVA = (
    "dedutivel",
    "dedutivel_50",
    "nao_dedutivel",
    "isento",
    "autoliquidacao",
    "por_definir",
)
ORIGENS_CLASSIFICACAO = ("regra", "sugestao", "manual")

# Espaço fiscal do QR: I = continente, J = Açores, K = Madeira.
ESPACOS_FISCAIS = ("PT", "PT-AC", "PT-MA")
TIPOS_TAXA = ("isenta", "reduzida", "intermedia", "normal", "nao_sujeita")

NIVEIS_PROBLEMA = ("erro", "aviso")
ESTADOS_PERIODO = ("aberto", "em_revisao", "fechado")
CANAIS_PEDIDO = ("email", "sms", "whatsapp", "portal")
ESTADOS_PEDIDO = ("rascunho", "enviado", "respondido")
FORMATOS_EXPORTACAO = ("csv", "xlsx", "zip", "toconline", "primavera", "phc", "sage")
ESTADOS_SUBSCRICAO = ("teste", "ativa", "em_atraso", "cancelada")

# Autenticação
PROGRAMAS_CONTABILIDADE = ("toconline", "primavera", "phc", "sage", "outro")
DIMENSOES_GABINETE = ("ate_20", "21_50", "51_150", "mais_150")
TIPOS_SESSAO = ("gabinete", "portal")
FINALIDADES_CODIGO = ("confirmar_email", "repor_password", "entrar_portal")
CANAIS_CODIGO = ("email", "sms")
