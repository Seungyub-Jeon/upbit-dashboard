import logging
import datetime
from config.config import RISK_CONFIG

logger = logging.getLogger(__name__)

class RiskManager:
    """
    위험 관리 클래스 - 거래량 및 위험 노출 제한 없이 설정됨
    """
    def __init__(self, api, config=None):
        """
        리스크 매니저 초기화
        
        Args:
            api: UpbitAPI 인스턴스
            config: 위험 관리 설정
        """
        self.api = api
        self.config = config or RISK_CONFIG
        
        # 일일 트래킹
        self.daily_trades = []
        self.daily_pnl = 0
        self.reset_date = datetime.date.today()
        
        # 포지션 트래커 초기화
        self.positions = {}  # market -> position dict
        
        logger.info("Risk Manager initialized - 전액 거래 모드 활성화")
        
    def reset_daily_metrics(self):
        """
        새로운 날이 시작되면 일일 지표 재설정
        """
        today = datetime.date.today()
        if today > self.reset_date:
            logger.info("Resetting daily risk metrics")
            self.daily_trades = []
            self.daily_pnl = 0
            self.reset_date = today
    
    def calculate_position_size(self, market, price):
        """
        전액 매수 모드 - 가능한 최대 수량 계산
        
        Args:
            market: 마켓 심볼 (예: "KRW-BTC")
            price: 자산의 현재 가격
            
        Returns:
            float: 구매 가능한 수량
        """
        try:
            # KRW 잔고 가져오기
            krw_balance = self.api.get_balance('KRW')
            
            if not krw_balance or krw_balance <= 0:
                logger.warning("No KRW balance available")
                return 0
            
            # 수수료 고려하여 0.5% 정도 여유 둠
            available_amount = krw_balance * 0.995
            
            # 수량 계산
            quantity = available_amount / price
            
            logger.info(f"Calculated position size for {market}: {quantity} units at {price} KRW (using full balance: {available_amount} KRW)")
            return quantity
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    def check_max_daily_loss(self):
        """
        항상 거래 허용 (제한 없음)
        
        Returns:
            bool: 항상 True 반환
        """
        return True
    
    def apply_stop_loss_take_profit(self, market, entry_price, current_price, position_type):
        """
        스탑로스/이익실현 적용하지 않음 (항상 0 반환)
        
        Args:
            market: 마켓 심볼
            entry_price: 진입 가격
            current_price: 현재 가격
            position_type: 포지션 유형 ('long' 또는 'short')
            
        Returns:
            int: 항상 0 반환 (신호 없음)
        """
        return 0
    
    def update_position(self, market, quantity, price, position_type):
        """
        포지션 정보 업데이트 (트래킹용)
        
        Args:
            market: 마켓 심볼
            quantity: 매수/매도 수량
            price: 거래 가격
            position_type: 포지션 유형 ('long' 또는 'short')
        """
        self.positions[market] = {
            'quantity': quantity,
            'entry_price': price,
            'position_type': position_type,
            'timestamp': datetime.datetime.now()
        }
        logger.info(f"Updated position for {market}: {quantity} units at {price} ({position_type})")
    
    def close_position(self, market):
        """
        포지션 종료 (트래킹용)
        
        Args:
            market: 마켓 심볼
            
        Returns:
            dict: 종료된 포지션 정보
        """
        if market in self.positions:
            position = self.positions[market]
            del self.positions[market]
            logger.info(f"Closed position for {market}")
            return position
        return None
    
    def record_trade_pnl(self, market, entry_price, exit_price, quantity, position_type):
        """
        거래 손익 기록 (트래킹용)
        
        Args:
            market: 마켓 심볼
            entry_price: 진입 가격
            exit_price: 종료 가격
            quantity: 거래 수량
            position_type: 포지션 유형 ('long' 또는 'short')
        """
        # PnL 계산
        if position_type == 'long':
            pnl = (exit_price - entry_price) * quantity
        else:  # short
            pnl = (entry_price - exit_price) * quantity
            
        # 거래 기록
        self.daily_trades.append({
            'market': market,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': quantity,
            'position_type': position_type,
            'pnl': pnl,
            'timestamp': datetime.datetime.now()
        })
        
        # 일일 PnL 업데이트
        self.daily_pnl += pnl
        
        logger.info(f"Recorded trade for {market}: PnL = {pnl}")
        
        # 일일 지표 확인
        self.reset_daily_metrics()