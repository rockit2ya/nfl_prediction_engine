# 🏈 Super Bowl LX Prediction Engine: Seahawks vs. Patriots

A Python-based sports analytics engine designed to detect betting edges for **Super Bowl LX (February 8, 2026)**. This project utilizes advanced NFL metrics, specifically **Expected Points Added (EPA)**, combined with a sophisticated blending of momentum and stability weights.

## 🚀 Features

* **Blended Momentum Modeling:** Uses a weighted 70/30 approach, combining a 5-game stability window with a 3-game "heat" window to capture team evolution.
* **Automated & Manual Data Retrieval:** Powered by `nflreadpy` for live play-by-play data, with a built-in manual override for injury reporting when server parquets are unavailable.
* **Injury Weighting:** Dynamically penalizes team efficiency (EPA) based on the availability of star players (QB, T, S, LB).
* **Edge Detection UI:** Compares calculated "Fair Lines" against real-time market spreads to identify +EV (Expected Value) opportunities.

---

## 🛠️ Tech Stack

* **Language:** Python 3.14.2
* **Data Processing:** `polars` (ingestion) and `pandas` (analysis)
* **Bridge:** `pyarrow` (facilitating high-speed Arrow-to-NumPy conversion)
* **NFL Data:** `nflreadpy` (The 2026 nflverse standard)

---

## 📦 Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-username/nfl_prediction_engine.git
   cd nfl_prediction_engine

   ```


2. **Set up the Virtual Environment:**
   ```bash
   python3 -m venv nfl_predict

   ```


3. **Install Dependencies:**
   ```bash
   python3 -m pip install -r requirements.txt

   ```


---

## 🎮 How to Use

1. **Activate Environment:**
   ```bash
   source nfl_engine/bin/activate

   ```


2. **Run Engine:**
   ```bash
   python3 engine_ui.py

   ```


3. **Analyze Output:**
   If automated injury data returns a 404, the UI will prompt for manual entries. Use comma-separated names (e.g., Robert Spillane, Nick Emmanwori) to trigger efficiency penalties.


---


### Example Workflow:

1. **Data Sync:** The engine pulls the latest stats for Sam Darnold (SEA) and Drake Maye (NE).
2. **Injury Scan:** It detects if New England's linebackers are "Out" and adjusts their defensive EPA accordingly.
3. **Input:** You enter the current spread (e.g., `Patriots +4.5`).
4. **Result:** The engine outputs the **Predicted Point Differential** and flags if there is a significant betting "Edge."

---

## 📈 Model Methodology

The engine calculates a **Blended Power Rating** for each team to balance long-term stability with short-term momentum. This approach is designed to filter out "one-game wonders" while still respecting a team's current trajectory heading into Super Bowl LX.


### 🧮 The Prediction Formula

The final rating is derived using a weighted calculation of **Expected Points Added (EPA)**:

$$BlendedEPA = (Rolling5gEPA \times 0.70) + (Rolling3gEPA \times 0.30) - (InjuryPenalty)$$


### 🔍 Component Breakdown

* **70% Stability Anchor (5-Game Rolling EPA):** This baseline represents the team's "true identity" over the last month of play. It prevents the model from overreacting to a single explosive playoff game or a defensive fluke.
* **30% Momentum Sensor (3-Game Rolling EPA):** This captures the "heat" of the team. It allows the model to shift toward teams peaking at the right time (e.g., the Seahawks' recent offensive surge or the Patriots' defensive dominance).
* **Injury Penalty:** A flat deduction of **0.06 EPA** is applied for every identified "Star" player confirmed as out. This is manually input via the UI to bypass server 404 errors.
* **Scaling Factor (22.0):** To convert abstract efficiency into a scoreboard projection, a historical constant of **22.0** is applied to the EPA differential.
* *Example:* A  EPA advantage projects to a **2.2-point** lead on the spread.

### 🎯 Betting Edge Logic

The "Edge" is the delta between the model's **Fair Line** and the **Market Spread**:

$$Edge = |ModelSpread - MarketSpread|$$


> **Signal Threshold:** Any detected Edge greater than 2 points is flagged as a high-value opportunity, suggesting the market has mispriced the game based on current efficiency data.


---

## 🧬 Model Validation: The 22.0 Multiplier

To convert abstract efficiency (EPA) into a tangible scoreboard prediction (Points), the engine applies a scaling factor of **22.0**. This constant is derived from historical NFL regression analysis of performance versus margin of victory.

### 📉 Derivation & Theory

The relationship between EPA/play and point differential is the cornerstone of modern NFL analytics. The **22.0** multiplier is validated by the following data points:

* **The Play Volume Constant:** An average NFL game consists of approximately **60 to 65 offensive plays** per team.
* **Predictive Correlation:** Backtesting shows that a team with a **+1.0 EPA/play** advantage is roughly **22 points better** than their opponent on a neutral field.

### 🧮 Conversion Logic

The conversion from efficiency to point spread is expressed as:

$$ProjectedSpread = (BlendedEPA_{SEA} - BlendedEPA_{NE}) \times 22.0$$

### 🧪 Practical Application

By using this multiplier, the engine ensures that typical EPA differentials—which usually fall between  and —result in spreads that align with professional sportsbook logic.

* **Example:** A  EPA advantage projects a **2.2-point** lead.
* **Example:** A  EPA advantage projects a **4.4-point** lead.


---

## 📝 License

This project is for educational and analytical purposes only. **Always bet responsibly.**

---

