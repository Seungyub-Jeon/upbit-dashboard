import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API configuration
API_CONFIG = {
    'base_url': 'https://api.upbit.com/v1',
}

# Trading configuration
TRADING_CONFIG = {
    'interval': 1,  # 분 단위 실행 간격
    'markets': ['KRW-BTC'],  # 거래할 마켓 목록
    'strategies': {
        'sma': {
            'short_window': 5,
            'long_window': 20
        },
        'rsi': {
            'period': 14,
            'overbought': 70,
            'oversold': 30
        },
        'bollinger': {
            'period': 20,
            'std_dev': 2.0
        }
    }
}

# Risk management configuration
RISK_CONFIG = {
    # 위험 관리 비활성화 - 전액 거래
    'position_size_pct': 100,  # 가능한 잔고의 100% 사용
    'max_trade_amount': 1000000000,  # 충분히 큰 값으로 설정 (10억 원)
    'max_daily_trades': 1000,  # 충분히 큰 값으로 설정
    'max_daily_loss': 1000000000,  # 충분히 큰 값으로 설정 (10억 원)
    'stop_loss_pct': 100,  # 실질적으로 스탑로스 비활성화
    'take_profit_pct': 1000  # 실질적으로 이익실현 비활성화
}

# Database configuration
DB_CONFIG = {
    "enabled": True,
    "path": "data/trading.db"
}

# Logging configuration
LOG_CONFIG = {
    'path': 'logs/trading.log',
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

# Dashboard configuration
DASHBOARD_CONFIG = {
    'host': '0.0.0.0',
    'port': 8050,
    'debug': False,
    'refresh_interval': 5  # 초 단위로 대시보드 갱신 간격
}