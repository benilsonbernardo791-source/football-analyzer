import os
import math
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_HOST = "v3.football.api-sports.io"

def api_get(path, params):
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY não configurada.")
    r = requests.get(
        f"https://{API_HOST}/{path}",
        headers={"x-apisports-key": API_KEY},
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()

def poisson_pmf(lam, k):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def predict(home_avg, away_avg):
    # Modelo simples: médias recentes de gols. Não é garantia de resultado.
    home_lambda = max(0.15, home_avg)
    away_lambda = max(0.15, away_avg)

    home_win = draw = away_win = 0.0
    scores = []

    for h in range(0, 7):
        for a in range(0, 7):
            p = poisson_pmf(home_lambda, h) * poisson_pmf(away_lambda, a)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
            scores.append((p, h, a))

    scores.sort(reverse=True)
    return home_win, draw, away_win, scores[:5]

def recent_goal_average(team_id, last=5):
    data = api_get("fixtures", {"team": team_id, "last": last, "status": "FT"})
    matches = data.get("response", [])
    if not matches:
        return 1.0
    total_for = total_against = 0
    count = 0
    for m in matches:
        home = m["teams"]["home"]
        away = m["teams"]["away"]
        gh = m["goals"]["home"]
        ga = m["goals"]["away"]
        if gh is None or ga is None:
            continue
        if home["id"] == team_id:
            total_for += gh
            total_against += ga
        else:
            total_for += ga
            total_against += gh
        count += 1
    if count == 0:
        return 1.0
    return total_for / count

def find_team(name):
    data = api_get("teams", {"search": name})
    results = data.get("response", [])
    if not results:
        return None
    return results[0]["team"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Football Analyzer\n\n"
        "Use /palpite Nome do mandante | Nome do visitante\n"
        "Exemplo:\n/palpite Arsenal | Chelsea\n\n"
        "O bot usa dados recentes para gerar uma estimativa estatística."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def palpite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if "|" not in text:
        await update.message.reply_text(
            "Formato correto:\n/palpite Arsenal | Chelsea"
        )
        return

    home_name, away_name = [x.strip() for x in text.split("|", 1)]
    await update.message.reply_text("🔎 A analisar os dados recentes...")

    try:
        home = find_team(home_name)
        away = find_team(away_name)

        if not home or not away:
            await update.message.reply_text(
                "Não encontrei uma das equipas. Tente escrever os nomes oficiais."
            )
            return

        home_avg = recent_goal_average(home["id"])
        away_avg = recent_goal_average(away["id"])

        hw, dr, aw, top_scores = predict(home_avg, away_avg)
        probs = {"🏠 Casa": hw, "🤝 Empate": dr, "🚩 Fora": aw}
        best = max(probs, key=probs.get)

        score_lines = "\n".join(
            f"• {h}-{a} — {p*100:.1f}%"
            for p, h, a in top_scores[:3]
        )

        msg = (
            f"⚽ {home['name']} x {away['name']}\n\n"
            f"📊 Estimativa 1X2:\n"
            f"🏠 Casa: {hw*100:.1f}%\n"
            f"🤝 Empate: {dr*100:.1f}%\n"
            f"🚩 Fora: {aw*100:.1f}%\n\n"
            f"🎯 Tendência principal: {best}\n\n"
            f"🔢 Placares mais prováveis:\n{score_lines}\n\n"
            f"ℹ️ Médias recentes de gols:\n"
            f"{home['name']}: {home_avg:.2f}\n"
            f"{away['name']}: {away_avg:.2f}\n\n"
            "⚠️ São estimativas estatísticas, não garantias."
        )
        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(
            "❌ Não foi possível concluir a análise agora. "
            "Verifique as chaves/API e tente novamente."
        )
        print("ERROR:", repr(e))

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN não configurado.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("palpite", palpite))
    print("Football Analyzer iniciado.")
    app.run_polling()

if __name__ == "__main__":
    main()
