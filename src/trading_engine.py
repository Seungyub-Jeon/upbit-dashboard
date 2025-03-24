import logging
import time
import threading
import schedule
import numpy as np
from datetime import datetime
from collections import defaultdict

from config.config import TRADING_CONFIG, API_CONFIG
from src.api.upbit_api import UpbitAPI
from src.strategies.sma_strategy import SMAStrategy
from src.strategies.rsi_strategy import RSIStrategy
from src.strategies.bollinger_strategy import BollingerStrategy
from src.risk_management.risk_manager import RiskManager

logger = logging.getLogger(__name__)

def calculate_volatility(prices):
    """
    주어진 가격 리스트의 변동성(표준편차/평균)을 계산합니다.
    """
    if not prices or len(prices) < 2:
        return 0
    prices = np.array(prices)
    return np.std(prices) / np.mean(prices) * 100  # 백분율로 표현

class TradingEngine:
    """
    Main trading engine that coordinates strategies and executes trades
    """
    def __init__(self, markets, api_client, risk_manager, interval_minutes=3):
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
        # 가격 기록 저장용 딕셔너리
        self.price_history = {}
        # 매수 가격 기록
        self.buy_prices = {}
        
        logger.info(f"Trading Engine initialized with markets: {markets}, interval: {interval_minutes} minutes")
        
    def register_strategy(self, strategy):
        """
        Register a strategy
        :param strategy: Strategy instance
        """
        market = strategy.market
        self.strategies[market].append(strategy)
        logger.info(f"Initialized {strategy.__class__.__name__} for {market}")
    
    def _in_position(self, market):
        """
        현재 포지션 보유 여부 확인
        """
        currency = market.split('-')[1]
        balance = self.api.get_balance(currency)
        return balance > 0
    
    def _adjust_strategies_for_volatility(self, market, volatility):
        """
        변동성에 따른 전략 파라미터 조정
        """
        if market not in self.strategies:
            return
            
        logger.info(f"{market} 변동성: {volatility:.2f}%")
        
        # 변동성이 높은 경우 (3% 이상)
        if volatility > 3.0:
            logger.info(f"{market} 변동성이 높음: 보수적 전략으로 전환")
            for strategy in self.strategies[market]:
                if isinstance(strategy, RSIStrategy):
                    # RSI 과매수/과매도 기준 더 극단적으로 조정
                    strategy.overbought = 80  # 기본 70에서 상향
                    strategy.oversold = 20    # 기본 30에서 하향
                elif isinstance(strategy, BollingerStrategy):
                    # 볼린저 밴드 표준편차 증가
                    strategy.std_dev = 2.5    # 기본 2.0에서 상향
        # 변동성이 낮은 경우 (1% 미만)
        elif volatility < 1.0:
            logger.info(f"{market} 변동성이 낮음: 공격적 전략으로 전환")
            for strategy in self.strategies[market]:
                if isinstance(strategy, RSIStrategy):
                    # RSI 과매수/과매도 기준 덜 극단적으로 조정
                    strategy.overbought = 65  # 기본 70에서 하향
                    strategy.oversold = 35    # 기본 30에서 상향
                elif isinstance(strategy, BollingerStrategy):
                    # 볼린저 밴드 표준편차 감소
                    strategy.std_dev = 1.8    # 기본 2.0에서 하향
        # 보통 변동성 (1%~3%)
        else:
            # 기본 설정 복원
            for strategy in self.strategies[market]:
                if isinstance(strategy, RSIStrategy):
                    strategy.overbought = 70
                    strategy.oversold = 30
                elif isinstance(strategy, BollingerStrategy):
                    strategy.std_dev = 2.0
    
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
            
        # 신호 강도 평가 (2개 이상의 전략에서 같은 신호가 오면 더 높은 신뢰도)
        buy_signals = sum(1 for signal in signals if signal.get('action') == 'BUY')
        sell_signals = sum(1 for signal in signals if signal.get('action') == 'SELL')
        
        # 강한 신호일 경우 (2개 이상 전략에서 동일 신호)
        if buy_signals >= 2 and not self._in_position(market):
            logger.info(f"강한 매수 신호: {buy_signals}개 전략 일치")
            self.execute_trade(market, 'BUY', "COMBINED", current_price)
        elif sell_signals >= 2 and self._in_position(market):
            logger.info(f"강한 매도 신호: {sell_signals}개 전략 일치")
            self.execute_trade(market, 'SELL', "COMBINED", current_price)
        # 약한 신호일 경우 (1개 전략에서만 신호)
        elif signals:
            for signal in signals:
                if not signal or not isinstance(signal, dict):
                    continue  # 잘못된 형식의 신호는 무시
                    
                action = signal.get('action')
                price = signal.get('price', current_price)
                strategy_name = signal.get('strategy', 'Unknown')
                
                if action == 'BUY' and not self._in_position(market):
                    logger.info(f"Processing {action} signal for {market} from {strategy_name} at price {price}")
                    self.execute_trade(market, action, strategy_name, price)
                elif action == 'SELL' and self._in_position(market):
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
                    
                    # 현재 가격 조회
                    current_price = self.api.get_current_price(market)
                    if not current_price:
                        logger.error(f"Failed to get current price for {market}")
                        continue
                        
                    # 가격 기록 업데이트
                    if market not in self.price_history:
                        self.price_history[market] = []
                    
                    self.price_history[market].append(current_price)
                    # 최대 30개 기록만 유지
                    if len(self.price_history[market]) > 30:
                        self.price_history[market].pop(0)
                    
                    # 변동성 계산 (최근 10개 가격 데이터)
                    if len(self.price_history[market]) >= 10:
                        recent_prices = self.price_history[market][-10:]
                        volatility = calculate_volatility(recent_prices)
                        # 변동성에 따른 전략 조정
                        self._adjust_strategies_for_volatility(market, volatility)
                    
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
            
        # 최대 재시도 횟수
        max_retries = 3
        
        for attempt in range(max_retries):
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
                            # 매수 가격 기록
                            self.buy_prices[market] = price
                            return True
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
                            # 매수 가격 기록
                            self.buy_prices[market] = price
                            return True
                    
                elif action == 'SELL':
                    # 보유 수량 전체 매도
                    currency = market.split('-')[1]
                    balance = self.api.get_balance(currency)
                    
                    if balance <= 0:
                        logger.warning(f"Cannot SELL {market}: No balance")
                        return
                    
                    # 매수 가격 확인 (매수 평균가 가져오기)
                    avg_buy_price = self.api.get_avg_buy_price(currency)
                    if not avg_buy_price:
                        logger.warning(f"Cannot get average buy price for {currency}")
                        # 기록된 매수 가격 사용 시도
                        avg_buy_price = self.buy_prices.get(market, 0)
                        
                    # 최소 마진률 계산 (1%)
                    MIN_PROFIT_MARGIN = 1.0  # 1% 수익률
                    
                    if avg_buy_price > 0:
                        current_margin = ((price - avg_buy_price) / avg_buy_price) * 100
                        
                        if current_margin < MIN_PROFIT_MARGIN:
                            logger.info(f"현재 마진률({current_margin:.2f}%)이 최소 마진률({MIN_PROFIT_MARGIN}%)보다 낮아 매도하지 않습니다: {market}")
                            return
                            
                        logger.info(f"전액 매도: {market} - {balance} 수량, 마진률: {current_margin:.2f}%")
                    else:
                        logger.info(f"매수 가격 정보가 없어 마진률 계산 없이 매도: {market} - {balance} 수량")
                    
                    # 주문 실행
                    order = self.api.place_order(market, 'ask', balance, price, 'limit')
                    if order:
                        logger.info(f"매도 주문 완료: {order['uuid']}")
                        # 해당 마켓의 매수 가격 기록 삭제
                        if market in self.buy_prices:
                            del self.buy_prices[market]
                        return True
                
                # 주문 성공 시 루프 종료
                break
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"주문 실패, 재시도 중... ({attempt+1}/{max_retries}): {str(e)}")
                    time.sleep(1)  # 잠시 대기 후 재시도
                else:
                    logger.error(f"최대 재시도 횟수 초과, 주문 실패: {str(e)}")
        
        return False