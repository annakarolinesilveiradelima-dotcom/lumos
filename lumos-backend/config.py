"""
Lumos backend — configuração central.
Tudo que é segredo (chaves de API, webhooks) vem de variáveis de ambiente.
NUNCA coloque credenciais direto no código. Veja .env.example.
"""
import os

# --- Anthropic API (análise de sentimento / narrativas) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# Modelo usado na análise. Confirme o identificador atual em:
# https://docs.claude.com/en/docs/about-claude/models
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# --- Título / cobertura ---
TITLE_ID = "hp"
TITLE_LABEL = "Harry Potter (HBO)"
TITLE_TOP = "Harry Potter — Série HBO Max"
MARKET = "mercado brasileiro"

# Termos de busca para a coleta de notícias
QUERIES = [
    "nova série Harry Potter HBO Max",
    "Harry Potter HBO series cast",
    "série Harry Potter estreia",
]

# Feeds RSS de portais BR e internacionais (coleta gratuita, sem API paga).
# Ajuste/complemente conforme o time preferir.
RSS_FEEDS = [
    ("Omelete", "https://www.omelete.com.br/feed/rss"),
    ("Google News BR", "https://news.google.com/rss/search?q=s%C3%A9rie+Harry+Potter+HBO&hl=pt-BR&gl=BR&ceid=BR:pt-419"),
    ("Google News Intl", "https://news.google.com/rss/search?q=Harry+Potter+HBO+series&hl=en-US&gl=US&ceid=US:en"),
]

# --- Camada social (opcional) ---
# TikTok/X/Instagram normalmente exigem ferramenta de social listening licenciada
# (Brandwatch, Meltwater, Stilingue...). Aponte aqui o export/endpoint dela.
# Se ficar vazio, o backend gera o feed só com a camada de notícias + análise.
SOCIAL_EXPORT_PATH = os.environ.get("SOCIAL_EXPORT_PATH", "")  # ex.: caminho de um CSV/JSON exportado

# --- Saída ---
OUTPUT_DATA = os.environ.get("OUTPUT_DATA", "data.json")       # arquivo que o dashboard lê
HISTORY_DIR = os.environ.get("HISTORY_DIR", "history")         # snapshots diários (para calcular "vs. ontem")

# --- Notificação ---
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")    # webhook do canal (recomendado)
NOTIFY_EMAIL_TO = os.environ.get("NOTIFY_EMAIL_TO", "")        # ex.: anna.silveira@wbd.com
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# URL pública do painel (só para incluir o link na notificação)
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
