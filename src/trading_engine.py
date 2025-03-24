import logging
import time
import threading
import schedule
from datetime import datetime
from collections import defaultdict

from config.config import TRADING_CONFIG, API_CONFIG
from src.api.upbit_api import UpbitAPI
from src.strategies.sma_strategy import SMAStrategy
from src.strategies.rsi_strategy import RSIStrategy
from src.strategies.bollinger_strategy import BollingerStrategy
from src.risk_management.risk_manager import RiskManager

logger = logging.getLogger(__name__)

class TradingEngine:
    """
    Main trading engine that coordinates strategies and executes trades
    """
    def __init__(self, markets, api_client, risk_manager, interval_minutes=5):
        """
        Initialize the trading engine
        :param markets: List of market IDs to trade (e.g., ['KRW-BTC', 'KRW-ETH'])
        :param api_client: API client instance
        :param risk_manager: Risk manager instance
        :param interval_minutes: Strategy execution interval (minutes)
        """
        self.markets = markets
        self.api = api_client
        self.risk_manager = risk_manager
        self.interval = interval_minutes * 60  # Convert to seconds
        self.strategies = defaultdict(list)
        self.running = False
        self.thread = None
        self.is_trading_enabled = False
        # 전액 거래 모드
        self.full_amount_mode = True
        
        logger.info(f"Trading Engine initialized with markets: {markets}")
        
    def register_strategy(self, strategy):
        """
        Register a strategy
        :param strategy: Strategy instance
        """
        market = strategy.market
        self.strategies[market].append(strategy)
        logger.info(f"Initialized {strategy.__class__.__name__} for {market}")
    
    def process_signals(self, market, signals):
        """
        Process signals from strategies
        :param market: Market symbol (e.g., 'KRW-BTC')
        :param signals: List of signals from strategies
        """
        # Skip if trading is disabled
        if not self.is_trading_enabled:
            logger.info(f"Trading is disabled. Ignoring signals for {market}")
            return
            
        current_price = self.api.get_current_price(market)
        if not current_price:
            logger.error(f"Failed to get current price for {market}")
            return
            
        for signal in signals:
            if not signal or not isinstance(signal, dict):
                continue  # 잘못된 형식의 신호는 무시
                
            action = signal.get('action')
            price = signal.get('price', current_price)
            strategy_name = signal.get('strategy', 'Unknown')
            
            if action in ['BUY', 'SELL']:
                logger.info(f"Processing {action} signal for {market} from {strategy_name} at price {price}")
                self.execute_trade(market, action, strategy_name, price)
    
    def start(self):
        """
        트레이딩을 시작합니다.
        """
        # 거래 기능 항상 활성화
        self.is_trading_enabled = True
        
        if not self.running:
            self.full_amount_mode = True
            logger.info("트레이딩 시작: 전액 거래 모드로 실행, 거래 허용=True")
            self.start_engine()
        else:
            logger.info(f"트레이딩 신호 처리 활성화: 엔진 상태={self.running}, 거래 허용=True")
        
        # 상태 로그 추가
        logger.info(f"거래 엔진 상태: running={self.running}, is_trading_enabled={self.is_trading_enabled}")
    
    def stop(self):
        """
        트레이딩을 중지합니다.
        """
        if self.running:
            self.is_trading_enabled = False
            logger.info("트레이딩 중지: 새로운 트레이딩 신호가 무시됩니다.")
        else:
            logger.info("트레이딩이 이미 중지되었습니다.")
            
    def get_trading_status(self):
        """
        현재 트레이딩 상태를 반환합니다.
        """
        return self.is_trading_enabled
    
    def run(self):
        """
        Trading engine execution loop
        """
        logger.info("Starting trading engine")
        
        while self.running:
            try:
                now = datetime.now()
                logger.info(f"Running trading iteration at {now}")
                
                # Execute strategies for each market
                for market in self.markets:
                    logger.info(f"Processing market: {market}")
                    
                    # Skip if no strategies are registered for this market
                    if market not in self.strategies:
                        continue
                    
                    # Collect signals from all strategies
                    all_signals = []
                    for strategy in self.strategies[market]:
                        signal = strategy.generate_signal()
                        if signal:
                            all_signals.append(signal)
                    
                    # Process signals
                    if all_signals:
                        self.process_signals(market, all_signals)
                
                # Wait for next execution
                time.sleep(self.interval)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {str(e)}")
                # Wait before retrying if an error occurs
                time.sleep(10)
    
    def start_engine(self):
        """
        Start the trading engine (runs in a separate thread)
        """
        if self.running:
            logger.warning("Trading engine already running")
            return
            
        logger.info(f"Trading engine started with interval: {self.interval//60} minutes")
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True  # Exit with main thread
        self.thread.start()
    
    def stop_engine(self):
        """
        Stop the trading engine
        """
        logger.info("Stopping trading engine")
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Trading engine stopped")

    def execute_trade(self, market, action, strategy_name, price=None):
        """
        Execute a trade based on a signal
        :param market: Market to trade (e.g., 'KRW-BTC')
        :param action: 'BUY' or 'SELL'
        :param strategy_name: Name of the strategy that generated the signal
        :param price: Price at which to place the order (optional, uses market price if not provided)
        """
        # 트레이딩이 비활성화되어 있으면 신호 무시
        if not self.is_trading_enabled:
            logger.info(f"Trading is disabled. Ignoring {action} signal for {market} from {strategy_name}")
            return
            
        try:
            # Get current price if not provided
            if not price:
                price = self.api.get_current_price(market)
                if not price:
                    logger.error(f"Could not fetch current price for {market}")
                    return
            
            if action == 'BUY':
                # 전액 거래 모드
                if self.full_amount_mode:
                    # 전체 KRW 잔고의 99.95%를 사용 (수수료 고려)
                    balance_krw = self.api.get_balance('KRW')
                    
                    # 최소 거래 금액 확인 (5,000원)
                    MIN_ORDER_AMOUNT = 5000
                    
                    if balance_krw < MIN_ORDER_AMOUNT:
                        logger.warning(f"Cannot BUY {market}: 잔액({balance_krw}원)이 최소 거래 금액({MIN_ORDER_AMOUNT}원)보다 적습니다.")
                        return
                    
                    if balance_krw <= 0:
                        logger.warning(f"Cannot BUY {market}: Insufficient KRW balance")
                        return
                    
                    # 단기 트레이딩: 잔액의 100% 사용
                    trade_ratio = 1.0
                    
                    # 최소 금액 확인: 거래금액이 5000원 이상이어야 함
                    amount = min(balance_krw * trade_ratio, balance_krw * 0.9995)  # 수수료 고려
                    
                    if amount < MIN_ORDER_AMOUNT:
                        amount = MIN_ORDER_AMOUNT  # 최소 5,000원
                    
                    # 주문 수량 계산
                    volume = amount / price
                    
                    # 소수점 8자리까지만 사용 (업비트 제한)
                    volume = round(volume, 8)
                    
                    logger.info(f"단기 트레이딩 모드: {market} 매수 - {amount}원 (수량: {volume}, 잔액: {balance_krw}원)")
                    
                    # 주문 실행
                    order = self.api.place_order(market, 'bid', volume, price, 'limit')
                    if order:
                        logger.info(f"매수 주문 완료: {order['uuid']}")
                else:
                    # 기존 로직 (리스크 관리 적용)
                    position_size = self.risk_manager.calculate_position_size(market, price)
                    if position_size <= 0:
                        logger.warning(f"Calculated position size for {market} is zero")
                        return
                    
                    # 최소 거래 금액 확인 (5,000원)
                    MIN_ORDER_AMOUNT = 5000
                    
                    # Calculate volume from position size
                    balance_krw = self.api.get_balance('KRW')
                    
                    if balance_krw < MIN_ORDER_AMOUNT:
                        logger.warning(f"Cannot BUY {market}: 잔액({balance_krw}원)이 최소 거래 금액({MIN_ORDER_AMOUNT}원)보다 적습니다.")
                        return
                    
                    # 단기 트레이딩: 계산된 포지션의 100% 사용
                    position_size = min(position_size * 1.0, position_size)
                    
                    amount = min(position_size, balance_krw * 0.9995)
                    
                    # 최소 금액 확인
                    if amount < MIN_ORDER_AMOUNT:
                        amount = MIN_ORDER_AMOUNT
                    
                    volume = amount / price
                    
                    # 소수점 8자리까지만 사용 (업비트 제한)
                    volume = round(volume, 8)
                    
                    logger.info(f"Placing BUY order for {market}: {volume} at {price} (Signal from {strategy_name})")
                    order = self.api.place_order(market, 'bid', volume, price, 'limit')
                    if order:
                        logger.info(f"Buy order placed: {order['uuid']}")
                
            elif action == 'SELL':
                # 보유 수량 전체 매도
                currency = market.split('-')[1]
                balance = self.api.get_balance(currency)
                
                if balance <= 0:
                    logger.warning(f"Cannot SELL {market}: No balance")
                    return
                
                logger.info(f"전액 매도: {market} - {balance} 수량")
                
                # 주문 실행
                order = self.api.place_order(market, 'ask', balance, price, 'limit')
                if order:
                    logger.info(f"매도 주문 완료: {order['uuid']}")
                    
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")