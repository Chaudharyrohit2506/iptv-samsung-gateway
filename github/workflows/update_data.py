import requests
import json
import time
from bs4 import BeautifulSoup

URL_HOME = "https://chartink.com/screener"
URL_PROCESS = "https://chartink.com/screener/process"

# Chartink scan condition (replaces scan logic for Dashboard 346557)
DEFAULT_SCAN_CLAUSE = "( {cash} ( close > 50 and volume > 50000 ) )"

def run():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Referer": URL_HOME
    }

    res_home = session.get(URL_HOME, headers=headers)
    soup = BeautifulSoup(res_home.text, "html.parser")
    csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]

    headers["X-CSRF-TOKEN"] = csrf_token
    payload = {"scan_clause": DEFAULT_SCAN_CLAUSE}

    res = session.post(URL_PROCESS, data=payload, headers=headers)
    res_data = res.json().get("data", [])

    total = len(res_data)
    if total == 0:
        return

    advances = sum(1 for x in res_data if float(x.get("per_chg", 0)) > 0)
    declines = sum(1 for x in res_data if float(x.get("per_chg", 0)) < 0)
    unchanged = total - (advances + declines)

    stocks = []
    for s in res_data:
        stocks.append({
            "s": s.get("nsecode") or s.get("name"),
            "p": float(s.get("close", 0)),
            "c": float(s.get("per_chg", 0)),
            "v": f"{int(s.get('volume', 0)):,}"
        })

    stocks.sort(key=lambda x: x["c"], reverse=True)

    output = {
        "time": time.strftime("%d %b, %I:%M %p IST"),
        "breadth": {
            "adv": advances,
            "dec": declines,
            "unc": unchanged,
            "tot": total,
            "ratio": round(advances / declines, 2) if declines > 0 else advances,
            "pct_adv": round((advances / total) * 100, 1),
            "status": "Bullish" if advances > declines else "Bearish"
        },
        "stocks": stocks
    }

    with open("data.json", "w") as f:
        json.dump(output, f)

if __name__ == "__main__":
    run()
