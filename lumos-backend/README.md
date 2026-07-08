# Lumos — backend de atualização diária

Este pacote faz o painel **atualizar sozinho todo dia às 11h**, publicar num **link de site** e **te notificar** quando o resumo do dia estiver pronto.

Eu não consigo deixar isso no ar a partir daqui (não tenho como hospedar um site nem rodar um servidor agendado em nome da WBD, nem acesso às contas). O que está aqui é o backend **pronto pra rodar**: depois de um setup único do time, ele roda sozinho todos os dias.

---

## O que cada peça faz

| Arquivo | Papel |
|---|---|
| `run_daily.py` | Orquestra tudo (é o que o agendador chama) |
| `sources.py` | Coleta notícias (RSS grátis) e, se houver, dados sociais da ferramenta de listening |
| `analyze.py` | Usa o Claude pra classificar sentimento e extrair narrativas/cobertura |
| `build_data.py` | Monta o `data.json` no formato do painel e calcula o "vs. ontem" |
| `notify.py` | Manda o resumo do dia pro Slack e/ou e-mail |
| `.github/workflows/daily.yml` | Agenda: roda **11h BRT** todo dia e publica |

O painel (`lumos.html`) já lê o `data.json` automaticamente — não precisa mexer nele.

---

## Caminho recomendado: GitHub + Pages + Actions (resolve tudo de uma vez)

Isso dá, ao mesmo tempo: **o link do site**, o **agendamento das 11h** e a **publicação automática**.

**1. Criar o repositório**
Suba, na raiz do repo: `lumos.html` + a pasta `lumos-backend/`.

**2. Ligar o site (o seu link)**
Em *Settings → Pages*, aponte para a branch principal (raiz). O GitHub gera a URL:
```
https://<sua-org>.github.io/<repo>/lumos.html
```
Esse é o link do Lumos. (Alternativa com domínio próprio/mais simples: Netlify ou Vercel, arrastando a mesma pasta — também servem `lumos.html` + `data.json`.)

**3. Cadastrar os segredos**
Em *Settings → Secrets and variables → Actions*, crie:
- `ANTHROPIC_API_KEY` (obrigatório pra análise) — pegue em https://console.anthropic.com
- `SLACK_WEBHOOK_URL` (pra te notificar no Slack) — ou os `SMTP_*` + `NOTIFY_EMAIL_TO` pra e-mail
- `DASHBOARD_URL` = o link do passo 2 (aparece na notificação)
- `SOCIAL_EXPORT_PATH` (opcional) se for plugar a ferramenta de listening

**4. Confirmar o horário**
Já está em `daily.yml` como `cron: "0 14 * * *"` = **11h de Brasília** (o GitHub usa UTC; Brasil = UTC-3). Pra testar antes, use o botão *Run workflow* (rodada manual).

Pronto: todo dia às 11h ele coleta → analisa → gera o `data.json` → publica no site → te avisa.

---

## Rodar na mão (teste local)

```bash
cd lumos-backend
pip install -r requirements.txt
cp .env.example .env      # preencha ANTHROPIC_API_KEY e o canal de notificação
export $(grep -v '^#' .env | xargs)   # carrega as variáveis
python run_daily.py
```
Sem `ANTHROPIC_API_KEY`, ele ainda roda em **modo fallback** (classificação simples por palavra-chave) pra você ver o fluxo funcionando.

---

## Sobre as fontes (o ponto que depende do time)

- **Notícias/imprensa**: já funcionam via RSS (Omelete, Google News BR/Intl) — sem custo, com links reais das matérias.
- **Redes (TikTok, X, Instagram)**: normalmente **não têm API aberta**. O jeito realista é exportar da ferramenta de social listening que a WBD já usa (Brandwatch, Meltwater, Stilingue…) e apontar `SOCIAL_EXPORT_PATH` para esse export (CSV com `platform,mentions,pos,neu,neg`). Enquanto isso não estiver ligado, o feed sai completo na parte de notícias e com estimativas na parte social.

---

## Antes de colocar no ar (WBD)

Como isso vira um **site externo** e usa **dados de terceiros**, vale alinhar com os donos certos antes de publicar: hospedagem/segurança do domínio, licença da ferramenta de listening, e uso de nome/imagem (Legal/Privacy). O código e o agendamento estão prontos; a publicação em si é uma decisão de quem tem essa alçada.

---

## Notificação — como chega pra você

Todo dia, depois de gerar o feed, você recebe (Slack ou e-mail) algo como:

> **Lumos — Harry Potter · 8 jul 2026**
> Menções: 9,7 mil (+22%) · Sentimento: +54/100 · Buzz: 86/100
> Tom do dia: empolgação com as fotos oficiais
> Narrativas em destaque:
>  • HBO Max divulga primeira foto oficial do trio
>  • Debate sobre o elenco ganha tração no X
> Abrir painel: https://…
