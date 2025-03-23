# Upbit Cryptocurrency Trading Bot

An automated cryptocurrency trading bot for the Upbit exchange with secure API integration, multiple trading strategies, risk management, and a monitoring dashboard.

## Features

- **Secure API Integration**: JWT-based authentication with the Upbit API
- **Multiple Trading Strategies**:
  - Simple Moving Average (SMA) Crossover
  - Relative Strength Index (RSI)
  - Bollinger Bands
- **Risk Management**:
  - Position sizing
  - Stop-loss and take-profit mechanisms
  - Maximum daily loss limits
  - Trade tracking and performance monitoring
- **Dashboard**:
  - Real-time account balance monitoring
  - Market data visualization
  - Strategy indicators
  - Trade history
  - Performance tracking

## Project Structure

```
upbit.dashboard/
├── config/
│   └── config.py         # Configuration settings
├── logs/                 # Log files
├── src/
│   ├── api/
│   │   └── upbit_api.py  # Upbit API client
│   ├── strategies/
│   │   ├── base_strategy.py
│   │   ├── sma_strategy.py
│   │   ├── rsi_strategy.py
│   │   └── bollinger_strategy.py
│   ├── risk_management/
│   │   └── risk_manager.py
│   ├── dashboard/
│   │   └── app.py        # Dash dashboard application
│   ├── trading_engine.py # Main trading logic
│   └── main.py           # Application entry point
├── tests/                # Test files
├── .env.example          # Example environment variables
├── requirements.txt      # Dependencies
└── README.md             # This file
```

## Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd upbit.dashboard
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API credentials**:
   - Copy `.env.example` to `.env`
   - Add your Upbit API keys:
     ```
     UPBIT_ACCESS_KEY=your_access_key_here
     UPBIT_SECRET_KEY=your_secret_key_here
     ```

5. **Configure trading parameters**:
   - Edit `config/config.py` to adjust trading pairs, strategy parameters, risk settings, etc.

## Usage

### Running the Full Application

Run both the trading engine and dashboard:

```bash
python src/main.py
```

### Dashboard Only

Run just the dashboard without the trading engine:

```bash
python src/main.py --dashboard-only
```

### Trading Engine Only

Run just the trading engine without the dashboard:

```bash
python src/main.py --trading-only
```

### Quick Commands Setup

For easier control of the bot, you can set up quick commands:

1. **Set up aliases**:
   ```bash
   ./scripts/setup_aliases.sh
   ```

2. **Apply the changes**:
   ```bash
   source ~/.zshrc
   ```

3. **Using quick commands**:
   - Start the bot: `play`
   - Stop the bot: `stop`

## Dashboard

The dashboard is accessible at `http://localhost:8050` (or the host/port configured in `config.py`).

It provides:
- Real-time account balance information
- Market data and price charts
- Technical indicators (SMA, RSI, Bollinger Bands)
- Trade history
- Performance metrics

## Risk Management

The bot includes several risk management features:
- Position sizing based on account balance percentage
- Stop-loss to limit losses on individual trades
- Take-profit to secure gains
- Daily loss limits to prevent excessive losses
- Performance tracking

## Customization

### Adding New Strategies

1. Create a new strategy class in the `src/strategies` directory
2. Inherit from `BaseStrategy` and implement the `generate_signal` method
3. Add the strategy to the configuration in `config/config.py`
4. Update the `TradingEngine.initialize_strategies` method to include your new strategy

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading involves significant risk of loss. Use this software at your own risk.

## License

[MIT License](LICENSE)