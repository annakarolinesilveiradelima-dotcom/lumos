"""
Lumos — rotina diária.

Executa a cadeia completa:
  coleta  ->  análise  ->  montagem  ->  grava data.json  ->  histórico  ->  notifica

É este arquivo que o agendador (GitHub Actions / cron) chama todo dia às 11h.
Uso local:  python run_daily.py
"""
import sources
import analyze
import build_data
import notify


def main():
    print("=== Lumos daily run ===")
    collected = sources.collect_all()
    analysis = analyze.analyze(collected)
    day = build_data.build_day(collected, analysis)
    build_data.save_history(day)
    feed = build_data.build_feed(day)
    build_data.write_feed(feed)
    notify.notify(day)
    print("=== concluído ===")


if __name__ == "__main__":
    main()
