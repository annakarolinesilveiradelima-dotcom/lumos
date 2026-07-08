"""
Análise — usa o Claude (Anthropic API) para transformar os itens coletados
em: tom geral, split de sentimento, narrativas do dia e cobertura classificada.

Retorna um dicionário pronto para o build_data montar o contrato do Lumos.
Se a API não estiver disponível, cai num fallback heurístico simples para o
pipeline não quebrar (o feed sai marcado como parcial).

Docs da API: https://docs.claude.com/en/api/overview
"""
import json
import re

import config

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


SYSTEM = (
    "Você é um analista sênior de social listening e PR intelligence de "
    "entretenimento, com foco no mercado brasileiro. Analise os itens de "
    "notícia/menções fornecidos sobre a nova série de Harry Potter da HBO Max "
    "(estreia dez/2026). Responda APENAS com JSON válido, sem markdown."
)

SCHEMA_HINT = """
Formato exato da resposta (sem crases, sem texto fora do JSON):
{
  "tone": "<tom dominante em 4-8 palavras>",
  "sentiment_index": <0-100, onde 100 = muito positivo>,
  "pos": <0-100>, "neu": <0-100>, "neg": <0-100>,
  "narratives": [
    {"t":"<conversa>","senti":"pos|neg|neu|div|iro","pf":"TikTok|X/Twitter|Instagram|YouTube|Reddit",
     "trend":"up|down|flat","growth":"<leitura curta>","q":"<frase representativa do tom>","pct":<0-100>,
     "src":[{"o":"<veículo>","u":"<url>"}]}
  ],
  "coverage": [
    {"o":"<veículo>","u":"<url>","title":"<manchete>","cat":"pos|neg|neu|esp|nos","time":"<hh:mm ou data>","scope":"Portal BR|Internacional|Opinião"}
  ],
  "risks": [{"t":"<risco>","sev":"low|mid|high","d":"<descrição>","rec":"<recomendação>"}]
}
Regras: pos+neu+neg somam 100. Máx 6 narrativas, 8 coberturas, 3 riscos. pt-BR.
"""


def analyze(collected):
    news = collected.get("news", [])
    if Anthropic is None or not config.ANTHROPIC_API_KEY:
        print("[análise] SDK/API indisponível — usando fallback heurístico.")
        return _fallback(news)

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    corpus = "\n".join(
        f"- [{n.get('outlet','?')}] {n.get('title','')} :: {n.get('url','')}"
        for n in news[:60]
    ) or "(sem itens de notícia coletados)"

    try:
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": f"{SCHEMA_HINT}\n\n=== ITENS COLETADOS ===\n{corpus}",
            }],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        data = _extract_json(text)
        data["_analysis"] = "claude"
        return data
    except Exception as exc:  # noqa: BLE001
        print(f"[análise] erro na API ({exc}) — fallback heurístico.")
        return _fallback(news)


def _extract_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b >= 0:
        text = text[a:b + 1]
    return json.loads(text)


def _fallback(news):
    """Heurística simples: classifica cobertura por palavras-chave."""
    pos_kw = ("elogi", "acerto", "fiel", "ansios", "empolg", "aprova")
    neg_kw = ("crític", "decepç", "polêmic", "reboot desnecess", "medo", "rejeit")
    nos_kw = ("nostalg", "filmes", "cresci", "trilha")
    esp_kw = ("rumor", "especula", "vaza", "pode", "possível")
    coverage = []
    p = g = n = 0
    for it in news[:12]:
        t = (it.get("title", "") + " " + it.get("summary", "")).lower()
        cat = "neu"
        if any(k in t for k in pos_kw): cat, p = "pos", p + 1
        elif any(k in t for k in neg_kw): cat, n = "neg", n + 1
        elif any(k in t for k in nos_kw): cat = "nos"
        elif any(k in t for k in esp_kw): cat = "esp"
        else: g += 1
        coverage.append({
            "o": it.get("outlet", "Imprensa"), "u": it.get("url", "#"),
            "title": it.get("title", "—"), "cat": cat, "time": "hoje",
            "scope": "Portal BR",
        })
    total = max(p + g + n, 1)
    return {
        "tone": "Leitura heurística (sem análise semântica)",
        "sentiment_index": 50 + round((p - n) / total * 30),
        "pos": round(p / total * 100) if total else 55,
        "neu": round(g / total * 100) if total else 30,
        "neg": round(n / total * 100) if total else 15,
        "narratives": [{
            "t": c["title"], "senti": {"pos": "pos", "neg": "neg"}.get(c["cat"], "neu"),
            "pf": "X/Twitter", "trend": "flat", "growth": "coletado via RSS",
            "q": "", "pct": 50, "src": [{"o": c["o"], "u": c["u"]}],
        } for c in coverage[:5]],
        "coverage": coverage,
        "risks": [],
        "_analysis": "fallback",
    }
