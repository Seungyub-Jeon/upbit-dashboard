import os
import jwt
import uuid
import hashlib
import requests
import time
import logging
from urllib.parse import urlencode, unquote
from config.config import API_CONFIG

logger = logging.getLogger(__name__)

class UpbitAPI:
    """
    Wrapper class for Upbit Exchange API
    """
    def __init__(self):
        self.access_key = os.getenv('UPBIT_ACCESS_KEY')
        self.secret_key = os.getenv('UPBIT_SECRET_KEY')
        self.base_url = 'https://api.upbit.com/v1'
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)
        
        if not self.access_key or not self.secret_key:
            self.logger.error("API 키가 설정되지 않았습니다.")
            raise ValueError("API 키가 설정되지 않았습니다.")
        
        logger.info("Upbit API client initialized")
        
    def _get_token(self, params):
        """
        Create JWT authentication token
        """
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': self._hash_query(params) if params else None,
            'query_hash_alg': 'SHA512',
        }
        
        jwt_token = jwt.encode(payload, self.secret_key)
        return jwt_token
    
    def _hash_query(self, params):
        query_string = urlencode(params, doseq=True)
        m = hashlib.sha512()
        m.update(query_string.encode())
        return m.hexdigest()
    
    def _request(self, method, endpoint, params=None, data=None):
        """
        Make a request to the Upbit API
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        if method != 'POST':
            headers['Authorization'] = f"Bearer {self._get_token(params)}"
        else:
            headers['Authorization'] = f"Bearer {self._get_token()}"
        
        try:
            response = requests.request(method, url, params=params, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {e}")
            if response.text:
                logger.error(f"Response: {response.text}")
            raise
    
    # Account endpoints
    def get_accounts(self):
        """
        계정 정보 조회
        """
        try:
            jwt_token = self._get_token({})
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            response = self.session.get(f"{self.base_url}/accounts", headers=headers)
            response.raise_for_status()
            accounts = response.json()
            
            self.logger.debug(f"계정 정보: {accounts}")
            return accounts
        except Exception as e:
            self.logger.error(f"계정 정보 조회 중 오류 발생: {str(e)}")
            return None
    
    def get_account(self, currency):
        """
        Get specific currency account
        """
        accounts = self.get_accounts()
        for account in accounts:
            if account['currency'] == currency:
                return account
        return None
    
    def get_balance(self, currency):
        """
        Get balance for specific currency
        """
        account = self.get_account(currency)
        if account:
            return float(account['balance'])
        return 0.0
    
    # Market endpoints
    def get_markets(self):
        """
        Get available markets
        """
        return self._request('GET', '/market/all')
    
    def get_ticker(self, market):
        """
        Get current ticker information for a market
        """
        try:
            if market != 'KRW-BTC':
                return None
                
            url = f"{self.base_url}/ticker"
            params = {'markets': market}
            response = self.session.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"현재가 조회 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"현재가 조회 중 에러 발생: {str(e)}")
            return None
    
    def get_orderbook(self, markets):
        """
        Get order book
        """
        if isinstance(markets, list):
            markets = ','.join(markets)
        params = {'markets': markets}
        return self._request('GET', '/orderbook', params=params)
    
    def get_candles(self, market, interval='minutes', count=100, unit=1):
        """
        Get candle data for a market
        """
        try:
            if market != 'KRW-BTC':
                return None
                
            url = f"{self.base_url}/candles/{interval}/{unit}"
            params = {
                'market': market,
                'count': count
            }
            response = self.session.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"캔들 데이터 조회 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"캔들 데이터 조회 중 에러 발생: {str(e)}")
            return None
    
    # Order endpoints
    def place_order(self, market, side, volume, price=None, ord_type='limit'):
        """
        Place a new order
        """
        try:
            url = f"{self.base_url}/orders"
            data = {
                'market': market,
                'side': side,
                'ord_type': ord_type
            }

            if ord_type == 'limit':
                data['volume'] = str(volume)
                data['price'] = str(price)
            elif ord_type == 'market':
                if side == 'bid':
                    data['price'] = str(price)
                else:
                    data['volume'] = str(volume)

            headers = {"Authorization": f"Bearer {self._get_token(data)}"}
            response = self.session.post(url, json=data, headers=headers)
            
            if response.status_code == 400:
                error_msg = response.json().get('error', {}).get('message', '알 수 없는 에러')
                logger.warning(f"주문 실패: {error_msg}")
                return None
                
            if response.status_code != 201:
                logger.error(f"주문 실행 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"주문 실행 중 에러 발생: {str(e)}")
            return None
    
    def get_order(self, uuid):
        """
        Get order information
        """
        try:
            url = f"{self.base_url}/order"
            params = {'uuid': uuid}
            headers = {"Authorization": f"Bearer {self._get_token(params)}"}
            
            response = self.session.get(url, params=params, headers=headers)
            
            if response.status_code == 404:
                logger.warning(f"주문을 찾을 수 없음: {uuid}")
                return None
                
            if response.status_code != 200:
                logger.error(f"주문 조회 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"주문 조회 중 에러 발생: {str(e)}")
            return None
    
    def cancel_order(self, uuid):
        """
        Cancel an existing order
        """
        try:
            url = f"{self.base_url}/order"
            data = {'uuid': uuid}
            headers = {"Authorization": f"Bearer {self._get_token(data)}"}
            
            response = self.session.delete(url, json=data, headers=headers)
            
            if response.status_code == 404:
                logger.warning(f"취소할 주문을 찾을 수 없음: {uuid}")
                return None
                
            if response.status_code != 200:
                logger.error(f"주문 취소 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"주문 취소 중 에러 발생: {str(e)}")
            return None
    
    def get_orders(self, market, state='wait', page=1, limit=100):
        """
        Get list of orders
        state: wait, done, cancel
        """
        try:
            params = {
                'market': market,
                'state': state,
                'page': page,
                'limit': limit
            }
            
            url = f"{self.base_url}/orders"
            headers = {"Authorization": f"Bearer {self._get_token(params)}"}
            
            response = self.session.get(url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"주문 목록 조회 실패: {response.status_code}")
                logger.error(f"에러 메시지: {response.text}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"주문 목록 조회 중 에러 발생: {str(e)}")
            return None

    def get_order_history(self, market=None, state='done', count=20):
        """
        주문 내역을 조회합니다.
        :param market: 마켓 ID (예: KRW-BTC)
        :param state: 주문 상태 (wait, watch, done, cancel)
        :param count: 조회할 주문 개수
        :return: 주문 내역 리스트
        """
        try:
            # 주문 내역 조회
            query = {}
            if state:
                query['state'] = state
            if market:
                query['market'] = market
            if count:
                query['limit'] = count

            # JWT 토큰 생성
            payload = {
                'access_key': self.access_key,
                'nonce': str(uuid.uuid4()),
            }
            
            if query:
                query_string = urlencode(query)
                m = hashlib.sha512()
                m.update(query_string.encode())
                payload['query_hash'] = m.hexdigest()
                payload['query_hash_alg'] = 'SHA512'
            
            jwt_token = jwt.encode(payload, self.secret_key)
            headers = {'Authorization': f'Bearer {jwt_token}'}
            
            # 주문 내역 조회 요청
            response = self.session.get(
                f"{self.base_url}/orders", 
                params=query, 
                headers=headers
            )
            response.raise_for_status()
            
            orders = response.json()
            logger.debug(f"주문 내역 조회 응답: {orders}")
            
            # 더미 데이터 추가 (테스트용)
            if not orders:
                logger.warning("주문 내역이 없어 더미 데이터로 대체합니다.")
                return []
            
            # 각 주문에 대해 체결 내역 조회 (지연 추가)
            for order in orders:
                try:
                    if order['state'] == 'done':
                        # 기본값 설정 (API 실패 시에도 작동하도록)
                        order['trades_price'] = float(order.get('price', 0))
                        order['executed_volume'] = float(order.get('volume', 0))
                        
                        # 체결된 주문의 상세 정보 조회를 위한 새로운 JWT 토큰 생성
                        order_query = {'uuid': order['uuid']}
                        order_payload = {
                            'access_key': self.access_key,
                            'nonce': str(uuid.uuid4()),
                            'query_hash': self._hash_query(order_query),
                            'query_hash_alg': 'SHA512'
                        }
                        
                        order_jwt_token = jwt.encode(order_payload, self.secret_key)
                        order_headers = {'Authorization': f'Bearer {order_jwt_token}'}
                        
                        # 주문 상세 정보 요청
                        trades_response = self.session.get(
                            f"{self.base_url}/order",
                            params=order_query,
                            headers=order_headers
                        )
                        
                        if trades_response.status_code == 200:
                            trade_info = trades_response.json()
                            
                            # 체결 정보 설정
                            order['trades_price'] = float(trade_info.get('trades_avg_price', trade_info.get('price', order['trades_price'])))
                            order['executed_volume'] = float(trade_info.get('executed_volume', trade_info.get('volume', order['executed_volume'])))
                            
                            logger.debug(f"주문 상세 정보: {trade_info}")
                        else:
                            logger.warning(f"주문 상세 정보 조회 실패: {trades_response.status_code}, {trades_response.text}")
                        
                        # 요청 간에 약간의 지연 추가 (0.2초)
                        time.sleep(0.2)
                except Exception as e:
                    logger.error(f"주문 상세 정보 조회 중 오류 발생: {str(e)}")
                    # 오류가 발생해도 계속 진행
                    continue
            
            return orders

        except Exception as e:
            logger.error(f"주문 내역 조회 중 오류 발생: {str(e)}")
            return []