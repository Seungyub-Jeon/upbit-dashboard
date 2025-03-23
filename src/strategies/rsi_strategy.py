import logging
import pandas as pd
import numpy as np
from src.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class RSIStrategy(BaseStrategy):
    """
    Relative Strength Index (RSI) Strategy
    
    Generates buy signals when RSI is below the oversold threshold,
    and sell signals when RSI is above the overbought threshold.
    """
    def __init__(self, api, market, config=None):
        """
        Initialize the RSI strategy
        
        Args:
            api: UpbitAPI instance
            market: Market symbol (e.g., "KRW-BTC")
            config: Strategy configuration with period, overbought, and oversold levels
        """
        super().__init__(api, market, config)
        
        # Set default values if not provided
        self.period = self.config.get('period', 14)
        self.overbought = self.config.get('overbought', 70)
        self.oversold = self.config.get('oversold', 30)
        
        logger.info(f"RSI Strategy initialized with period={self.period}, "
                    f"overbought={self.overbought}, oversold={self.oversold}")
        
    def calculate_rsi(self):
        """
        Calculate the Relative Strength Index
        
        Formula:
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        if self.df is None or len(self.df) < self.period:
            logger.warning("Not enough data to calculate RSI")
            return False
            
        # Calculate price changes
        delta = self.df['close'].diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gain and loss over the specified period
        avg_gain = gain.rolling(window=self.period).mean()
        avg_loss = loss.rolling(window=self.period).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        self.df['rsi'] = 100 - (100 / (1 + rs))
        
        # Create signals
        self.df['signal'] = 0
        self.df.loc[self.df['rsi'] < self.oversold, 'signal'] = 1  # Buy signal
        self.df.loc[self.df['rsi'] > self.overbought, 'signal'] = -1  # Sell signal
        
        return True
        
    def generate_signal(self):
        """
        Generate trading signal based on RSI values
        
        Returns:
            Signal: 1 for buy, -1 for sell, 0 for hold
        """
        try:
            # Fetch latest data
            self.fetch_data(count=max(200, self.period + 10))
            
            # Calculate RSI
            if not self.calculate_rsi():
                return 0
                
            # Get the latest signal
            if len(self.df) > 0:
                latest_rsi = self.df['rsi'].iloc[-1]
                
                # Check for oversold condition (buy)
                if latest_rsi < self.oversold:
                    logger.info(f"RSI Strategy: BUY signal for {self.market} (RSI: {latest_rsi:.2f})")
                    return 1
                    
                # Check for overbought condition (sell)
                elif latest_rsi > self.overbought:
                    logger.info(f"RSI Strategy: SELL signal for {self.market} (RSI: {latest_rsi:.2f})")
                    return -1
            
            # Hold by default
            return 0
            
        except Exception as e:
            logger.error(f"Error generating RSI signal: {e}")
            return 0