from datetime import datetime, time
from flask import Flask, jsonify
import yfinance as yf
import json
import os
from pathlib import Path
import threading
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

TICKERS = {
    "SEME": "SEME.MI",
    "VUAA": "VUAA.MI",
    "IWDA": "IWDA.AS",
    "BTC":  "BTC-USD",
    "PEPE": "PEPE24478-USD"
}

HOLDINGS = {
    "SEME": 33.68,
    "VUAA": 2.89,
    "IWDA": 5.81,
    "BTC":  0.00490532 + 0.00094041,
    "PEPE": 17172087.6904
}

# File to store historical data
DATA_FILE = Path("portfolio_history.json")

def get_last_close(symbol: str) -> float:
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1d")
    if data.empty:
        raise RuntimeError(f"Geen data voor {symbol}")
    return float(data["Close"].iloc[0])

def load_history():
    """Load historical portfolio data from JSON file"""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history(history):
    """Save historical portfolio data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def calculate_portfolio_total(prices):
    """Calculate total portfolio value"""
    total = 0
    
    if prices.get("SEME") is not None:
        total += prices["SEME"] * HOLDINGS["SEME"]
    if prices.get("VUAA") is not None:
        total += prices["VUAA"] * HOLDINGS["VUAA"]
    if prices.get("IWDA") is not None:
        total += prices["IWDA"] * HOLDINGS["IWDA"]
    if prices.get("BTC") is not None:
        total += prices["BTC"] * HOLDINGS["BTC"]
    if prices.get("PEPE") is not None:
        total += prices["PEPE"] * HOLDINGS["PEPE"]
    if prices.get("Fondsen") is not None:
        total += prices["Fondsen"]
    
    return total

def save_daily_snapshot():
    """Save portfolio snapshot at midnight"""
    print(f"[{datetime.now()}] Saving daily snapshot...")
    
    try:
        # Get current prices
        prices = {}
        for name, symbol in TICKERS.items():
            try:
                prices[name] = get_last_close(symbol)
            except Exception as e:
                print(f"Error fetching {name}: {e}")
                prices[name] = None
        
        # Add fondsen
        prices["Fondsen"] = 3552
        
        # Calculate total
        total = calculate_portfolio_total(prices)
        
        # Load existing history
        history = load_history()
        
        # Add new entry
        snapshot = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": round(total, 2),
            "prices": prices
        }
        
        # Avoid duplicate entries for the same date
        history = [h for h in history if h.get("date") != snapshot["date"]]
        history.append(snapshot)
        
        # Save to file
        save_history(history)
        print(f"Snapshot saved: €{total:.2f}")
        
    except Exception as e:
        print(f"Error saving snapshot: {e}")

@app.route("/")
def index():
    html = """<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <title>Tracker</title>

  <!-- Roboto Mono alleen voor cijfers -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link
    href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap"
    rel="stylesheet"
  >

  <!-- Chart.js voor de grafiek -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <style>
    body {
      margin: 20px;
      font-size: 16px;
    }

    /* Cijfers: Roboto Mono, kleiner en niet vet */
    .value {
      font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, Monaco,
                   Consolas, "Liberation Mono", "Courier New", monospace;
      font-weight: normal;
      font-size: 0.875rem;
    }

    /* Euroteken: expliciet géén Roboto Mono, terug naar default stack */
    .currency-symbol {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
                   sans-serif;
      font-weight: normal;
      font-size: 1rem;
    }

    .row {
      display: flex;
      justify-content: space-between;
      max-width: 320px;
    }
    .name {
      flex: 1;
    }
    .amount {
      width: 120px;
      text-align: right;
    }
    hr {
      max-width: 320px;
      margin-left: 0;
    }

    .pl-positive {
      color: #16a34a;
      font-weight: 500;
    }
    .pl-negative {
      color: #dc2626;
      font-weight: 500;
    }
    .pl-neutral {
      color: #6b7280;
    }

    /* Flash animations - only text color changes */
    @keyframes flash-green {
      0% { color: inherit; }
      50% { color: #16a34a; font-weight: 600; }
      100% { color: inherit; }
    }
    
    @keyframes flash-red {
      0% { color: inherit; }
      50% { color: #dc2626; font-weight: 600; }
      100% { color: inherit; }
    }

    .flash-up {
      animation: flash-green 1s ease-in-out;
    }

    .flash-down {
      animation: flash-red 1s ease-in-out;
    }

    #chart-container {
      max-width: 800px;
      margin-top: 30px;
      padding: 20px;
      background: #ffffff;
      border: 2px solid #000000;
    }

    canvas {
      max-height: 400px;
    }
  </style>
</head>
<body>
  <h1>Tracker</h1>
  <p>Laatst bijgewerkt: <span id="timestamp">-</span></p>
  <p>Volgende update over: <span id="next-update">-</span> seconden</p>

  <div class="row">
    <span class="name">MSCI Global Semiconductors</span>
    <span id="seme-total" class="amount">-</span>
  </div>
  <div class="row">
    <span class="name">S&amp;P500 ETF</span>
    <span id="vuaa-total" class="amount">-</span>
  </div>
  <div class="row">
    <span class="name">MSWI World ETF</span>
    <span id="iwda-total" class="amount">-</span>
  </div>
  <div class="row">
    <span class="name">Fondsen</span>
    <span id="fondsen-total" class="amount">-</span>
  </div>
  <div class="row">
    <span class="name">Bitcoin (BTC)</span>
    <span id="btc-total" class="amount">-</span>
  </div>
  <div class="row">
    <span class="name">PEPE</span>
    <span id="pepe-total" class="amount">-</span>
  </div>

  <hr>

  <div class="row">
    <span class="name">Totaal</span>
    <span id="total-portfolio" class="amount">-</span>
  </div>

  <div class="row" style="margin-top: 10px;">
    <span class="name">P/L vandaag</span>
    <span id="pl-today" class="amount pl-neutral">-</span>
  </div>

  <button id="snapshot-btn" style="margin-top: 20px; padding: 10px 20px; background: #3b82f6; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px;">
    📸 Maak Snapshot (Test)
  </button>
  <span id="snapshot-status" style="margin-left: 10px; color: #16a34a;"></span>

  <div id="chart-container">
    <h2>Portfolio Geschiedenis</h2>
    <canvas id="portfolioChart"></canvas>
  </div>

  <script>
    // Vul hier jouw aantallen in
    const HOLDINGS = {
      SEME: 33.68,
      VUAA: 2.89,
      IWDA: 5.81,
      BTC:  0.00490532 + 0.00094041,
      PEPE: 17172087.6904
    };

    let chart = null;
    
    // Track previous values for flash animations
    let previousValues = {
      seme: null,
      vuaa: null,
      iwda: null,
      fondsen: null,
      btc: null,
      pepe: null,
      total: null
    };

    // volgende hele minuut (seconde 0)
    function getNextMinuteSlot() {
      const now = new Date();
      const next = new Date(now.getTime());
      next.setSeconds(0, 0);
      if (next <= now) {
        next.setMinutes(next.getMinutes() + 1);
      }
      return next;
    }

    let nextUpdateTimeMs = getNextMinuteSlot().getTime();

    function formatEuro(value) {
      return (
        '<span class="value">' + value.toFixed(2) + '</span>' +
        '<span class="currency-symbol"> €</span>'
      );
    }

    function formatPL(amount, percentage) {
      const sign = amount >= 0 ? '+' : '';
      const className = amount > 0 ? 'pl-positive' : (amount < 0 ? 'pl-negative' : 'pl-neutral');
      
      return (
        '<span class="' + className + '">' +
        '<span class="value">' + sign + amount.toFixed(2) + '</span>' +
        '<span class="currency-symbol"> € </span>' +
        '<span class="value">(' + sign + percentage.toFixed(2) + '%)</span>' +
        '</span>'
      );
    }

    function flashElement(elementId, newValue, oldValue) {
      if (oldValue === null) return; // Skip on first load
      
      const element = document.getElementById(elementId);
      
      // Remove existing animation classes
      element.classList.remove('flash-up', 'flash-down');
      
      // Add new animation based on change
      if (newValue > oldValue) {
        element.classList.add('flash-up');
      } else if (newValue < oldValue) {
        element.classList.add('flash-down');
      }
      
      // Remove class after animation completes
      setTimeout(() => {
        element.classList.remove('flash-up', 'flash-down');
      }, 1000);
    }

    async function fetchPrices() {
      try {
        const response = await fetch("/api/prices");
        const data = await response.json();

        document.getElementById("timestamp").textContent = data.timestamp || "-";

        const prices = data.prices || {};

        const semePrice   = prices.SEME    ?? null;
        const vuaaPrice   = prices.VUAA    ?? null;
        const iwdaPrice   = prices.IWDA    ?? null;
        const btcPrice    = prices.BTC     ?? null;
        const pepePrice   = prices.PEPE    ?? null;
        const fondsenVal  = prices.Fondsen ?? null;

        let semeTotal    = null;
        let vuaaTotal    = null;
        let iwdaTotal    = null;
        let btcTotal     = null;
        let pepeTotal    = null;
        let fondsenTotal = null;

        if (semePrice != null) {
          semeTotal = semePrice * HOLDINGS.SEME;
          flashElement('seme-total', semeTotal, previousValues.seme);
          document.getElementById("seme-total").innerHTML = formatEuro(semeTotal);
          previousValues.seme = semeTotal;
        } else {
          document.getElementById("seme-total").textContent = "-";
        }

        if (vuaaPrice != null) {
          vuaaTotal = vuaaPrice * HOLDINGS.VUAA;
          flashElement('vuaa-total', vuaaTotal, previousValues.vuaa);
          document.getElementById("vuaa-total").innerHTML = formatEuro(vuaaTotal);
          previousValues.vuaa = vuaaTotal;
        } else {
          document.getElementById("vuaa-total").textContent = "-";
        }

        if (iwdaPrice != null) {
          iwdaTotal = iwdaPrice * HOLDINGS.IWDA;
          flashElement('iwda-total', iwdaTotal, previousValues.iwda);
          document.getElementById("iwda-total").innerHTML = formatEuro(iwdaTotal);
          previousValues.iwda = iwdaTotal;
        } else {
          document.getElementById("iwda-total").textContent = "-";
        }

        if (btcPrice != null) {
          btcTotal = btcPrice * HOLDINGS.BTC;
          flashElement('btc-total', btcTotal, previousValues.btc);
          document.getElementById("btc-total").innerHTML = formatEuro(btcTotal);
          previousValues.btc = btcTotal;
        } else {
          document.getElementById("btc-total").textContent = "-";
        }

        if (pepePrice != null) {
          pepeTotal = pepePrice * HOLDINGS.PEPE;
          flashElement('pepe-total', pepeTotal, previousValues.pepe);
          document.getElementById("pepe-total").innerHTML = formatEuro(pepeTotal);
          previousValues.pepe = pepeTotal;
        } else {
          document.getElementById("pepe-total").textContent = "-";
        }

        if (fondsenVal != null) {
          fondsenTotal = fondsenVal;
          flashElement('fondsen-total', fondsenTotal, previousValues.fondsen);
          document.getElementById("fondsen-total").innerHTML = formatEuro(fondsenTotal);
          previousValues.fondsen = fondsenTotal;
        } else {
          document.getElementById("fondsen-total").textContent = "-";
        }

        const totals = [
          semeTotal,
          vuaaTotal,
          iwdaTotal,
          btcTotal,
          pepeTotal,
          fondsenTotal
        ].filter(v => v != null);

        if (totals.length > 0) {
          const portfolioTotal = totals.reduce((a, b) => a + b, 0);
          flashElement('total-portfolio', portfolioTotal, previousValues.total);
          document.getElementById("total-portfolio").innerHTML = formatEuro(portfolioTotal);
          previousValues.total = portfolioTotal;
        } else {
          document.getElementById("total-portfolio").textContent = "-";
        }

        // Update P/L display
        if (data.pl_amount !== null && data.pl_amount !== undefined) {
          document.getElementById("pl-today").innerHTML = 
            formatPL(data.pl_amount, data.pl_percentage);
        } else {
          document.getElementById("pl-today").innerHTML = 
            '<span class="pl-neutral">-</span>';
        }

        nextUpdateTimeMs = getNextMinuteSlot().getTime();
      } catch (err) {
        console.error("Fout bij ophalen prijzen:", err);
      }
    }

    async function fetchHistory() {
      try {
        const response = await fetch("/api/history");
        const history = await response.json();

        if (history.length === 0) {
          return;
        }

        const labels = history.map(h => h.date);
        const values = history.map(h => h.total);

        if (chart) {
          chart.destroy();
        }

        const ctx = document.getElementById('portfolioChart').getContext('2d');
        chart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [{
              label: 'Portfolio Waarde (€)',
              data: values,
              borderColor: '#000000',
              backgroundColor: 'transparent',
              borderWidth: 2,
              tension: 0,
              fill: false,
              pointRadius: 4,
              pointBackgroundColor: '#000000',
              pointBorderColor: '#000000',
              pointHoverRadius: 6,
              pointHoverBackgroundColor: '#000000',
              pointHoverBorderColor: '#000000'
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
              legend: {
                display: true,
                position: 'top',
                labels: {
                  color: '#000000',
                  font: {
                    family: 'monospace',
                    size: 12
                  },
                  boxWidth: 15,
                  boxHeight: 2
                }
              },
              tooltip: {
                backgroundColor: '#000000',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                borderColor: '#000000',
                borderWidth: 1,
                displayColors: false,
                callbacks: {
                  label: function(context) {
                    return '€' + context.parsed.y.toFixed(2);
                  }
                }
              }
            },
            scales: {
              x: {
                grid: {
                  color: '#e5e5e5',
                  drawBorder: true,
                  borderColor: '#000000',
                  borderWidth: 2
                },
                ticks: {
                  color: '#000000',
                  font: {
                    family: 'monospace',
                    size: 11
                  }
                }
              },
              y: {
                beginAtZero: false,
                grid: {
                  color: '#e5e5e5',
                  drawBorder: true,
                  borderColor: '#000000',
                  borderWidth: 2
                },
                ticks: {
                  color: '#000000',
                  font: {
                    family: 'monospace',
                    size: 11
                  },
                  callback: function(value) {
                    return '€' + value.toFixed(0);
                  }
                }
              }
            }
          }
        });
      } catch (err) {
        console.error("Fout bij ophalen geschiedenis:", err);
      }
    }

    function updateCountdown() {
      const el = document.getElementById("next-update");
      const now = Date.now();
      let diffMs = nextUpdateTimeMs - now;

      if (diffMs <= 0) {
        el.textContent = 0;
        fetchPrices();
        nextUpdateTimeMs = getNextMinuteSlot().getTime();
        return;
      }

      const diffSec = Math.floor(diffMs / 1000);
      el.textContent = diffSec;
    }

    function startLoop() {
      fetchPrices();
      fetchHistory();
      setInterval(updateCountdown, 1000);
      // Refresh history every 5 minutes
      setInterval(fetchHistory, 5 * 60 * 1000);
    }

    // Snapshot button handler
    document.getElementById('snapshot-btn').addEventListener('click', async function() {
      const btn = this;
      const status = document.getElementById('snapshot-status');
      
      btn.disabled = true;
      btn.textContent = 'Bezig...';
      status.textContent = '';
      
      try {
        const response = await fetch('/api/snapshot', { method: 'POST' });
        const data = await response.json();
        
        status.textContent = '✓ Snapshot opgeslagen!';
        btn.textContent = '📸 Maak Snapshot (Test)';
        
        // Refresh data
        setTimeout(() => {
          fetchPrices();
          fetchHistory();
          status.textContent = '';
        }, 1000);
        
      } catch (err) {
        status.textContent = '✗ Fout opgetreden';
        status.style.color = '#dc2626';
        btn.textContent = '📸 Maak Snapshot (Test)';
        console.error(err);
      }
      
      btn.disabled = false;
    });

    startLoop();
  </script>
</body>
</html>"""
    return html

@app.route("/api/prices")
def api_prices():
    now = datetime.now()

    prices = {}
    for name, symbol in TICKERS.items():
        try:
            prices[name] = get_last_close(symbol)
        except Exception:
            prices[name] = None

    # Add fondsen
    prices["Fondsen"] = 3552
    
    # Calculate current total
    current_total = calculate_portfolio_total(prices)
    
    # Load history to get previous day's total
    history = load_history()
    previous_total = None
    pl_amount = None
    pl_percentage = None
    
    if history:
        # Get the most recent snapshot
        previous = history[-1]
        previous_total = previous.get("total")
        
        if previous_total is not None:
            pl_amount = current_total - previous_total
            pl_percentage = (pl_amount / previous_total) * 100 if previous_total > 0 else 0

    return jsonify({
        "timestamp": now.strftime("%H:%M:%S %d/%m/%y"),
        "prices": prices,
        "current_total": round(current_total, 2),
        "previous_total": round(previous_total, 2) if previous_total is not None else None,
        "pl_amount": round(pl_amount, 2) if pl_amount is not None else None,
        "pl_percentage": round(pl_percentage, 2) if pl_percentage is not None else None
    })

@app.route("/api/history")
def api_history():
    """Return historical portfolio data for graphing"""
    history = load_history()
    return jsonify(history)

@app.route("/api/snapshot", methods=["POST"])
def manual_snapshot():
    """Manually trigger a snapshot (for testing)"""
    save_daily_snapshot()
    return jsonify({"status": "success", "message": "Snapshot saved!"})

def start_scheduler():
    """Start the background scheduler for daily snapshots"""
    scheduler = BackgroundScheduler()
    
    # Schedule daily snapshot at midnight
    scheduler.add_job(
        save_daily_snapshot,
        'cron',
        hour=0,
        minute=0,
        id='daily_snapshot'
    )
    
    scheduler.start()
    print("Scheduler started - daily snapshots will be saved at midnight")

if __name__ == "__main__":
    # Start the scheduler
    start_scheduler()
    
    # Run the Flask app
    app.run(debug=True, use_reloader=False)