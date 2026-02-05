# 🏈 Super Bowl LX Prediction Engine: Seahawks vs. Patriots

A Python-based sports analytics engine designed to detect betting edges for **Super Bowl LX (February 8, 2026)**. This project utilizes advanced NFL metrics, specifically **Expected Points Added (EPA)**, combined with a sophisticated blending of momentum and stability weights.

<video src="https://github.com/user-attachments/assets/dd3eee6d-319b-4315-981a-bcf7dcfd71dd" controls="controls" poster="https://github.com/user-attachments/assets/2f29ab8b-bd31-4619-86f5-c350e4648316" style="max-width: 100%; border-radius: 10px;">
Your browser does not support the video tag.
</video>

*The 41-second session above demonstrates the 70/30 Blended Model logic and final edge detection.*


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
   source nfl_predict/bin/activate

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


> **Signal Threshold:** Any detected Edge `> 2.0 points` is flagged as a high-value opportunity, suggesting the market has mispriced the game based on current efficiency data.


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

By using this multiplier, the engine ensures that typical EPA differentials—which usually fall between `-0.20` and `+0.20`—result in spreads that align with professional sportsbook logic.

* **Example:** A `+0.1` EPA advantage projects a **2.2-point** lead.
* **Example:** A `+0.2` EPA advantage projects a **4.4-point** lead.


---


# 🏆 Final Verdict: Super Bowl LX Prediction

This is the high-level summary of the engine's output for **Super Bowl LX (February 8, 2026)** at Levi's Stadium. The following data points represent the final synthesis of our **70/30 Blended Model**.

## 📊 The Numerical Signal

| Metric | Value |
| --- | --- |
| **Market Spread** | Seahawks -4.5 |
| **Model "Fair Line"** | Seahawks -1.38 |
| **Calculated Edge** | **3.12 Points** |
| **Moneyline +EV** | **+12.0% (Patriots +195)** |

### 🧮 Edge Calculation

The engine identified this signal by calculating the absolute variance between the market and our projected spread:

$$Edge = \lvert ModelSpread - MarketSpread \rvert$$

$$\lvert -1.38 - (-4.5) \rvert = 3.12$$

> **Signal Status:** 🟢 **STRONG BUY** (Edge `> 2.0` points)

---

## 🧠 Logic & Synthesis

The verdict is driven by three critical factors identified during the data ingestion process:

### 1. The Stability Anchor (70%)

The 5-game rolling average favors the **New England Patriots'** defensive consistency. Their ability to limit explosive plays (Bottom 5 in EPA allowed on 20+ yard attempts) provides a high floor against the Seahawks' vertical passing game.

### 2. Momentum Spike (30%)

While the **Seattle Seahawks** showed a significant offensive surge in the Divisional and Championship rounds, their 3-game "heat" window was not enough to overcome the structural defensive advantages of the Patriots in our blended weighting.

### 3. Injury Penalties

The manual override was triggered for two specific key absences, which narrowed the efficiency gap significantly:

* **Charles Cross (SEA - LT):** Absence resulted in a -0.06 EPA penalty to Seattle's pass protection efficiency.
* **Secondary Depth:** Impact of the **Nick Emmanwori** and **Robert Spillane** status was normalized across the 3-game window.


### 4. The Result ###
The model projects a much tighter game than the current market consensus. With a 3.12-point Edge (surpassing our >2.0 signal threshold), the engine flags the Patriots +4.5 as a high-value opportunity.

---

## ⚠️ Disclaimer

This verdict is based on data available as of **February 5, 2026**. If active roster designations change prior to kickoff, the engine must be re-run to update the `InjuryPenalty` variable.

---

## 📝 License

This project is for educational and analytical purposes only. **Always bet responsibly.**

---

