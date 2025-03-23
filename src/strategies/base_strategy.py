import logging
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """
    Base class for all trading strategies
    """
    def __init__(self, api, market, config=None):
        """
        Initialize the strategy
        
        Args:
            api: UpbitAPI instance
            market: Market symbol (e.g., "KRW-BTC")
            config: Strategy configuration
        """
        self.api = api
        self.market = market
        self.config = config or {}
        self.df = None
        logger.info(f"Initialized {self.__class__.__name__} for {market}")
    
    def fetch_data(self, interval='minutes', count=200, unit=1):
        """
        Fetch candle data from the API and convert to DataFrame
        """
        try:
            candles = self.api.get_candles(self.market, interval, count, unit)
            
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            
            # Rename columns
            df = df.rename(columns={
                'opening_price': 'open',
                'high_price': 'high',
                'low_price': 'low',
                'trade_price': 'close',
                'candle_acc_trade_volume': 'volume',
                'candle_date_time_kst': 'date'
            })
            
            # Set date as index
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            # Sort by date (ascending)
            df = df.sort_index()
            
            # Convert to numeric
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
                
            self.df = df
            return df
            
        except Exception as e:
            logger.error(f"Error fetching candle data: {e}")
            return None
    
    @abstractmethod
    def generate_signal(self):
        """
        Generate trading signal based on strategy
        
        Returns:
            Signal: 1 for buy, -1 for sell, 0 for hold
        """
        pass
    
    def get_current_price(self):
        """
        Get current price for the market
        """
        ticker = self.api.get_ticker(self.market)
        if ticker and isinstance(ticker, list) and len(ticker) > 0:
            return float(ticker[0]['trade_price'])
        return None