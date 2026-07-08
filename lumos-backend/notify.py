"""
Notificação — avisa que o feed do dia foi atualizado.

Suporta Slack (webhook, recomendado) e e-mail (SMTP). Ambos opcionais,
ligados por variáveis de ambiente. Se nenhum estiver configurado, só imprime no log.
"""
import smtplib
from email.mime.text import MIMEText

import requests

import config


def _summary_lines(day):
    k = day["kpi"]
    lines = [
        f"*Lumos — Harry Potter · {day['label']}*",
        f"Menções: {k['mentions']['v']} ({_sign(k['mentions']['d'])}) · "
        f"Sentimento: {k['sentiment']['v']}{k['sentiment'].get('suf','')} · "
        f"Buzz: {k['buzz']['v']}{k['buzz'].get('suf','')}",
        f"Tom do dia: {day['senti']['tone']}",
    ]
    narr = day.get("narratives", [])[:3]
    if narr:
        lines.append("Narrativas em destaque:")
        lines += [f"  • {n['t']}" for n in narr]
    if config.DASHBOARD_URL:
        lines.append(f"Abrir painel: {config.DASHBOARD_URL}")
    return "\n".join(lines)


def _sign(d):
    return ("+" if d >= 0 else "") + str(d) + "%"


def _slack_blocks(day):
    """Mensagem rica (Block Kit) pro Slack: título, KPIs, narrativas e botão."""
    k = day["kpi"]
    kpi_line = (
        f"*Menções:* {k['mentions']['v']} ({_sign(k['mentions']['d'])})   "
        f"*Sentimento:* {k['sentiment']['v']}{k['sentiment'].get('suf','')}   "
        f"*Buzz:* {k['buzz']['v']}{k['buzz'].get('suf','')}"
    )
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"Lumos · Harry Potter — {day['label']}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": kpi_line}},
        {"type": "context",
         "elements": [{"type": "mrkdwn", "text": f"_Tom do dia:_ {day['senti'].get('tone','—')}"}]},
    ]
    narr = day.get("narratives", [])[:3]
    if narr:
        txt = "*Narrativas em destaque:*\n" + "\n".join(f"• {n['t']}" for n in narr)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": txt}})
    if config.DASHBOARD_URL:
        blocks.append({"type": "actions", "elements": [{
            "type": "button", "style": "primary",
            "text": {"type": "plain_text", "text": "Abrir painel", "emoji": True},
            "url": config.DASHBOARD_URL,
        }]})
    return blocks


def notify(day):
    text = _summary_lines(day)  # fallback em texto puro (notificação/preview)
    sent = False
    if config.SLACK_WEBHOOK_URL:
        try:
            payload = {"text": text, "blocks": _slack_blocks(day)}
            r = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=15)
            r.raise_for_status()
            print("[notify] Slack enviado.")
            sent = True
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] falha no Slack: {exc}")
    if config.NOTIFY_EMAIL_TO and config.SMTP_HOST:
        try:
            _send_email("Lumos — resumo diário Harry Potter", text)
            print("[notify] e-mail enviado.")
            sent = True
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] falha no e-mail: {exc}")
    if not sent:
        print("[notify] nenhum canal configurado — resumo:\n" + text)


def _send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = config.NOTIFY_EMAIL_TO
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as s:
        s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASS)
        s.sendmail(config.SMTP_USER, [config.NOTIFY_EMAIL_TO], msg.as_string())
