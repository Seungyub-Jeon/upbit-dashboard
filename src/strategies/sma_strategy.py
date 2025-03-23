import logging
import pandas as pd
import numpy as np
from src.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class SMAStrategy(BaseStrategy):
    """
    Simple Moving Average (SMA) Crossover Strategy
    
    Generates buy signals when short SMA crosses above long SMA,
    and sell signals when short SMA crosses below long SMA.
    """
    def __init__(self, api, market, config=None):
        """
        Initialize the SMA strategy
        
        Args:
            api: UpbitAPI instance
            market: Market symbol (e.g., "KRW-BTC")
            config: Strategy configuration with short_window and long_window
        """
        super().__init__(api, market, config)
        
        # Set default values if not provided
        self.short_window = self.config.get('short_window', 20)
        self.long_window = self.config.get('long_window', 50)
        
        if self.short_window >= self.long_window:
            logger.warning("Short window should be less than long window")
            self.short_window = 20
            self.long_window = 50
            
        logger.info(f"SMA Strategy initialized with windows {self.short_window}/{self.long_window}")
        
    def calculate_indicators(self):
        """
        Calculate the SMA indicators
        """
        if self.df is None or len(self.df) < self.long_window:
            logger.warning("Not enough data to calculate indicators")
            return False
            
        # Calculate short and long SMAs
        self.df['short_sma'] = self.df['close'].rolling(window=self.short_window).mean()
        self.df['long_sma'] = self.df['close'].rolling(window=self.long_window).mean()
        
        # Calculate the position signal
        self.df['signal'] = 0
        self.df['signal'][self.short_window:] = np.where(
            self.df['short_sma'][self.short_window:] > self.df['long_sma'][self.short_window:], 1, 0
        )
        
        # Calculate the actual trading signals (1 for buy, -1 for sell, 0 for hold)
        self.df['position'] = self.df['signal'].diff()
        
        return True
        
    def generate_signal(self):
        """
        Generate trading signal based on SMA crossover
        
        Returns:
            dict: Dictionary containing action, price, and strategy name, or None for hold
        """
        try:
            # Fetch latest data
            self.fetch_data(count=max(200, self.long_window + 10))
            
            # Calculate indicators
            if not self.calculate_indicators():
                return None
                
            # Get the latest signal
            if len(self.df) > 0:
                latest_position = self.df['position'].iloc[-1]
                latest_price = self.df['close'].iloc[-1]
                
                # Check for buy signal
                if latest_position == 1:
                    logger.info(f"SMA Strategy: BUY signal for {self.market}")
                    return {
                        'action': 'BUY',
                        'price': latest_price,
                        'strategy': 'SMA Crossover'
                    }
                    
                # Check for sell signal
                elif latest_position == -1:
                    logger.info(f"SMA Strategy: SELL signal for {self.market}")
                    return {
                        'action': 'SELL',
                        'price': latest_price,
                        'strategy': 'SMA Crossover'
                    }
            
            # Hold by default
            return None
            
        except Exception as e:
            logger.error(f"Error generating SMA signal: {e}")
            return None