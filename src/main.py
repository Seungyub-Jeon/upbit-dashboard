import argparse
import logging
import os
import sys
import time
import threading
import signal
import datetime
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import TRADING_CONFIG, API_CONFIG, DASHBOARD_CONFIG
from src.api.upbit_api import UpbitAPI
from src.risk_management.risk_manager import RiskManager
from src.trading_engine import TradingEngine
from src.strategies.sma_strategy import SMAStrategy
from src.strategies.rsi_strategy import RSIStrategy
from src.strategies.bollinger_strategy import BollingerStrategy
from src.dashboard.app import run_dashboard, TRADING_ENGINE

# 전략 파라미터 설정
STRATEGY_PARAMS = {
    'sma': {
        'short_window': 2,    # 3일에서 2일로 단축
        'long_window': 5,     # 7일에서 5일로 단축
        'volume_threshold': 1.2
    },
    'rsi': {
        'period': 5,          # 7일에서 5일로 단축
        'overbought': 75,     # 80에서 75로 하향
        'oversold': 25,       # 20에서 25로 상향
        'volume_threshold': 1.2
    },
    'bollinger': {
        'period': 5,          # 7일에서 5일로 단축
        'std_dev': 2.0,       # 2.5에서 2.0으로 감소
        'volume_threshold': 1.2
    }
}

# 리스크 관리 파라미터
RISK_PARAMS = {
    'max_position_size': 0.3,  # 최대 포지션 크기 (계좌의 30%)
    'min_order_amount': 5000,  # 최소 주문 금액
    'stop_loss': {
        'default': 1.5,      # -1.0%에서 -1.5%로 하향
        'strong_sell': 1.0,  # -0.7%에서 -1.0%로 하향
        'extreme_sell': 0.8  # -0.5%에서 -0.8%로 하향
    },
    'take_profit': {
        'default': 3.0,      # 2.0%에서 3.0%로 상향
        'strong_sell': 2.5,  # 1.5%에서 2.5%로 상향
        'extreme_sell': 2.0  # 1.2%에서 2.0%로 상향
    }
}

# 로깅 설정
def setup_logging():
    # 로그 디렉토리 생성
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 로그 파일 경로
    log_file = log_dir / "trading.log"
    
    # 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷 설정
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def main():
    # 로깅 설정
    logger = setup_logging()
    logger.info("Logging setup complete")
    
    # API 클라이언트 초기화
    api_client = UpbitAPI()
    
    # 리스크 매니저 초기화
    risk_manager = RiskManager(api_client)
    
    # 거래 엔진 초기화 (3분 간격으로 변경)
    trading_engine = TradingEngine(
        TRADING_CONFIG.get('markets', ['KRW-BTC']),
        api_client,
        risk_manager,
        TRADING_CONFIG.get('interval_minutes', 3)  # 5분에서 3분으로 변경
    )
    
    # 대시보드 모듈에 트레이딩 엔진 연결
    global TRADING_ENGINE
    import src.dashboard.app as dashboard
    dashboard.TRADING_ENGINE = trading_engine
    
    # 전략 등록
    for market in TRADING_CONFIG.get('markets', ['KRW-BTC']):
        # SMA 전략 초기화 및 등록 (더 민감하게 조정)
        sma_config = STRATEGY_PARAMS['sma']
        sma_strategy = SMAStrategy(api_client, market, sma_config)
        trading_engine.register_strategy(sma_strategy)
        
        # RSI 전략 초기화 및 등록 (기준치 조정)
        rsi_config = STRATEGY_PARAMS['rsi']
        rsi_strategy = RSIStrategy(api_client, market, rsi_config)
        trading_engine.register_strategy(rsi_strategy)
        
        # 볼린저 밴드 전략 초기화 및 등록 (기간 및 표준편차 조정)
        bollinger_config = STRATEGY_PARAMS['bollinger']
        bollinger_strategy = BollingerStrategy(api_client, market, bollinger_config)
        trading_engine.register_strategy(bollinger_strategy)
    
    # 거래 엔진 시작
    trading_engine.start_engine()
    
    # 거래 기능 자동 활성화
    trading_engine.is_trading_enabled = True
    logger.info("거래 기능이 자동으로 활성화되었습니다. 거래 가능 상태: 활성화")
    
    # 대시보드 초기화 및 실행
    logger.info("Starting dashboard")
    try:
        run_dashboard()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected, shutting down...")
    except Exception as e:
        logger.error(f"Error running dashboard: {e}")
        
    # 종료 시 거래 엔진 중지
    logger.info("Stopping trading engine")
    trading_engine.stop_engine()
    logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()