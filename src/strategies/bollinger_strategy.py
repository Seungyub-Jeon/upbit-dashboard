import logging
import pandas as pd
import numpy as np
from src.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class BollingerStrategy(BaseStrategy):
    """
    Bollinger Bands Strategy
    
    Generates buy signals when price crosses below the lower band,
    and sell signals when price crosses above the upper band.
    """
    def __init__(self, api, market, config=None):
        """
        Initialize the Bollinger Bands strategy
        
        Args:
            api: UpbitAPI instance
            market: Market symbol (e.g., "KRW-BTC")
            config: Strategy configuration with period and std_dev
        """
        super().__init__(api, market, config)
        
        # Set default values if not provided
        self.period = self.config.get('period', 20)
        self.std_dev = self.config.get('std_dev', 2.0)
        
        logger.info(f"Bollinger Bands Strategy initialized with period={self.period}, "
                    f"std_dev={self.std_dev}")
        
    def calculate_bollinger_bands(self):
        """
        Calculate Bollinger Bands
        
        Formula:
        Middle Band = SMA(period)
        Upper Band = Middle Band + (std_dev * Standard Deviation)
        Lower Band = Middle Band - (std_dev * Standard Deviation)
        """
        if self.df is None or len(self.df) < self.period:
            logger.warning("Not enough data to calculate Bollinger Bands")
            return False
            
        # Calculate middle band (SMA)
        self.df['middle_band'] = self.df['close'].rolling(window=self.period).mean()
        
        # Calculate standard deviation
        self.df['std_dev'] = self.df['close'].rolling(window=self.period).std()
        
        # Calculate upper and lower bands
        self.df['upper_band'] = self.df['middle_band'] + (self.std_dev * self.df['std_dev'])
        self.df['lower_band'] = self.df['middle_band'] - (self.std_dev * self.df['std_dev'])
        
        # Calculate Bollinger Band Width (BBW)
        self.df['bbw'] = (self.df['upper_band'] - self.df['lower_band']) / self.df['middle_band']
        
        # Calculate %B (position of price relative to the bands)
        self.df['percent_b'] = (self.df['close'] - self.df['lower_band']) / (self.df['upper_band'] - self.df['lower_band'])
        
        # Create signals based on price crossing the bands
        self.df['signal'] = 0
        
        # Price crossing below lower band (buy)
        self.df.loc[self.df['close'] < self.df['lower_band'], 'signal'] = 1
        
        # Price crossing above upper band (sell)
        self.df.loc[self.df['close'] > self.df['upper_band'], 'signal'] = -1
        
        return True
        
    def generate_signal(self):
        """
        Generate trading signal based on Bollinger Bands
        
        Returns:
            Signal dictionary: {'action': 'BUY'/'SELL'/'HOLD', 'price': current_price, 'strategy': 'Bollinger Bands'}
            or None if no signal
        """
        try:
            # Fetch latest data
            self.fetch_data(count=max(200, self.period + 10))
            
            # Calculate Bollinger Bands
            if not self.calculate_bollinger_bands():
                return None
                
            # Get the latest values
            if len(self.df) > 0:
                latest_close = self.df['close'].iloc[-1]
                latest_lower_band = self.df['lower_band'].iloc[-1]
                latest_upper_band = self.df['upper_band'].iloc[-1]
                
                # Check for buy signal (price below lower band)
                if latest_close < latest_lower_band:
                    logger.info(f"Bollinger Strategy: BUY signal for {self.market} "
                                f"(Price: {latest_close}, Lower Band: {latest_lower_band:.2f})")
                    return {
                        'action': 'BUY',
                        'price': latest_close,
                        'strategy': 'Bollinger Bands'
                    }
                    
                # Check for sell signal (price above upper band)
                elif latest_close > latest_upper_band:
                    logger.info(f"Bollinger Strategy: SELL signal for {self.market} "
                                f"(Price: {latest_close}, Upper Band: {latest_upper_band:.2f})")
                    return {
                        'action': 'SELL',
                        'price': latest_close,
                        'strategy': 'Bollinger Bands'
                    }
            
            # Hold by default
            return None
            
        except Exception as e:
            logger.error(f"Error generating Bollinger Bands signal: {e}")
            return None