import logging
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import pandas as pd
import threading
import time
from datetime import datetime, timedelta, timezone
import dash_bootstrap_components as dbc
import numpy as np
import traceback
import requests.exceptions

from config.config import DASHBOARD_CONFIG, TRADING_CONFIG
from src.api.upbit_api import UpbitAPI

logger = logging.getLogger(__name__)

# 전역 변수로 트레이딩 엔진 선언 (main.py에서 설정됨)
TRADING_ENGINE = None

# Initialize API client
api = UpbitAPI()

# 테마 정의
THEMES = {
    'DARK': dbc.themes.DARKLY,
    'LIGHT': dbc.themes.FLATLY
}

# 현재 테마 상태 (초기값: 다크모드)
current_theme = 'DARK'

# Initialize app with the current theme
app = dash.Dash(
    __name__, 
    external_stylesheets=[THEMES[current_theme]],
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ]
)
server = app.server
app.title = "업비트 트레이딩 대시보드"

# Cache for data
data_cache = {
    'balances': {},
    'trades': [],
    'market_data': {},
    'performance': {
        'dates': [],
        'pnl': []
    }
}

# Markets to display
markets = TRADING_CONFIG.get('markets', ['KRW-BTC'])

# 마켓 정보 초기화
TRADING_PAIRS = TRADING_CONFIG.get('markets', ['KRW-BTC'])

# Custom styles
COLORS = {
    # 다크 모드
    'dark': {
        'background': '#1E1E1E',
        'card_bg': '#2E2E2E',
        'text': '#FFFFFF',
        'primary': '#375A7F',
        'success': '#00BC8C',
        'danger': '#E74C3C',
        'warning': '#F39C12',
        'buy': '#00FF9C',  # 더 밝은 초록색
        'sell': '#FF5A5A',  # 더 밝은 빨간색
        'grid': '#333333'
    },
    # 라이트 모드
    'light': {
        'background': '#F8F9FA',
        'card_bg': '#FFFFFF',
        'text': '#212529',
        'primary': '#007BFF',
        'success': '#28A745',
        'danger': '#DC3545',
        'warning': '#FFC107',
        'buy': '#00A832',  # 더 진한 초록색
        'sell': '#D50000',  # 더 진한 빨간색
        'grid': '#EAECEF'
    },
    # 공통
    'common': {
        'buy': '#28A745',
        'sell': '#DC3545',
    }
}

# 현재 테마에 따른 스타일 가져오기
def get_current_styles():
    theme_key = 'dark' if current_theme == 'DARK' else 'light'
    colors = COLORS[theme_key]
    
    return {
        'page': {
            'backgroundColor': colors['background'],
            'color': colors['text'],
            'padding': '20px',
            'fontFamily': 'Noto Sans KR, sans-serif',
            'transition': 'all 0.3s ease'
        },
        'header': {
            'backgroundColor': colors['primary'],
            'padding': '15px 20px',
            'marginBottom': '25px',
            'borderRadius': '8px',
            'boxShadow': '0 4px 10px rgba(0, 0, 0, 0.1)',
            'transition': 'all 0.3s ease'
        },
        'card': {
            'backgroundColor': colors['card_bg'],
            'padding': '20px',
            'marginBottom': '25px',
            'borderRadius': '8px',
            'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)',
            'transition': 'all 0.3s ease'
        },
        'dropdown': {
            'backgroundColor': colors['card_bg'],
            'color': colors['text'],
            'borderRadius': '4px',
            'marginBottom': '15px'
        },
        'title': {
            'color': colors['primary'],
            'marginBottom': '15px',
            'fontWeight': '600',
            'fontSize': '1.25rem'
        },
        'button': {
            'borderRadius': '5px',
            'fontWeight': '500',
            'transition': 'all 0.2s ease',
            'marginRight': '8px',
            'boxShadow': '0 2px 5px rgba(0, 0, 0, 0.1)'
        }
    }

def get_available_markets():
    """
    거래 가능한 마켓 목록을 반환합니다.
    """
    return TRADING_PAIRS

def initialize_data():
    """데이터 초기화 함수"""
    global data_cache
    data_cache = {
        'balances': {},
        'trades': [],
        'market_data': {},
        'performance': {
            'dates': [],
            'pnl': []
        }
    }
    
    # 기본 시장 데이터 채우기
    for market in TRADING_PAIRS:
        data_cache['market_data'][market] = {
            'candles': [],
            'signals': []
        }

# 현재 스타일 가져오기
STYLES = get_current_styles()

# Header with title and controls
def create_header():
    return html.Div([
        dbc.Row([
            dbc.Col(html.H1("업비트 트레이딩 대시보드", className="mb-0 text-white"), width=12, lg=4, className="mb-3 mb-lg-0"),
            dbc.Col([
                dbc.ButtonGroup([
                    dbc.Button("트레이딩 시작", id="start-trading-btn", color="success", className="me-2"),
                    dbc.Button("트레이딩 중지", id="stop-trading-btn", color="danger"),
                ], className="d-flex justify-content-center")
            ], width=12, lg=4, className="mb-3 mb-lg-0"),
            dbc.Col([
                dbc.ButtonGroup([
                    dbc.Button("라이트 모드", id="light-mode-btn", color="light", className="me-2"),
                    dbc.Button("다크 모드", id="dark-mode-btn", color="dark"),
                ], className="d-flex justify-content-center")
            ], width=12, lg=4)
        ])
    ], id='header', style=STYLES['header'])

# Trading status
def create_trading_status():
    return dbc.Alert(
        "트레이딩 상태: 중지됨", 
        id="trading-status",
        color="warning",
        className="text-center fw-bold my-4",
        style={"fontSize": "1.1rem"}
    )

# Account balance card
def create_account_card():
    """계좌 정보 카드 생성"""
    return dbc.Card([
        dbc.CardHeader(
            dbc.Row([
                dbc.Col(html.H5("계좌 정보", className="m-0"), width="auto"),
                dbc.Col(
                    dbc.Button(
                        html.I(className="fas fa-sync-alt"),
                        id="refresh-account-btn",
                        color="link",
                        size="sm",
                        className="p-0 float-end"
                    ),
                    width="auto",
                    className="ms-auto"
                )
            ], align="center")
        ),
        dbc.CardBody(html.Div(id='account-balance', className="p-0")),
        dbc.Tooltip("계좌 정보 새로고침", target="refresh-account-btn")
    ], className="mb-4 shadow-sm")

# Market data card with candle chart
def create_market_card():
    """시장 데이터 카드 생성"""
    return dbc.Card([
        dbc.CardHeader(html.H5("시장 데이터", className="m-0")),
        dbc.CardBody([
            dcc.Dropdown(
                id='market-dropdown',
                options=[{'label': market, 'value': market} for market in markets],
                value=markets[0] if markets else None,
                clearable=False,
                className="mb-3"
            ),
            dcc.Graph(id='price-chart', config={'displayModeBar': True, 'scrollZoom': True})
        ], id='market-data'),
        # 비트코인 지표 영역 추가
        dbc.CardFooter(html.Div(id='bitcoin-indicators', className="p-0"))
    ], className="mb-4 shadow-sm")

# Trading signals card
def create_signals_card():
    return dbc.Card([
        dbc.CardHeader(html.H3("트레이딩 신호", className="card-title h5 text-primary fw-bold")),
        dbc.CardBody(
            dcc.Graph(id='signals-chart', config={'displayModeBar': False})
        )
    ], className="mb-4 shadow-sm")

# Recent trades card
def create_trades_card():
    return dbc.Card([
        dbc.CardHeader(html.H3("최근 거래", className="card-title h5 text-primary fw-bold")),
        dbc.CardBody(id="recent-trades", className="px-0")
    ], className="mb-4 shadow-sm")

# Performance card
def create_performance_card():
    return dbc.Card([
        dbc.CardHeader(html.H3("누적 성과", className="card-title h5 text-primary fw-bold")),
        dbc.CardBody(
            dcc.Graph(id='performance-chart', config={'displayModeBar': False})
        )
    ], className="mb-4 shadow-sm")

# 트레이딩 전략 정보 카드
def create_strategy_card():
    """트레이딩 전략 정보 카드 생성"""
    return dbc.Card([
        dbc.CardHeader(
            dbc.Row([
                dbc.Col(html.H5("거래 전략 설정", className="m-0"), width="auto"),
                dbc.Col(
                    dbc.Button(
                        html.I(className="fas fa-sync-alt"),
                        id="refresh-strategy-btn",
                        color="link",
                        size="sm",
                        className="p-0 float-end"
                    ),
                    width="auto",
                    className="ms-auto"
                )
            ], align="center")
        ),
        dbc.CardBody(html.Div(id='strategy-info', className="p-0")),
        dbc.Tooltip("전략 정보 새로고침", target="refresh-strategy-btn")
    ], className="mb-4 shadow-sm")

# Layout with responsive grid
def create_layout():
    return html.Div([
        dcc.Location(id='url', refresh=False),
        
        # 테마 스타일시트 (콜백으로 동적 변경)
        html.Link(
            id='theme-stylesheet',
            rel='stylesheet',
            href=THEMES[current_theme]
        ),
        
        # 주기적 업데이트를 위한 interval 컴포넌트 (5초마다)
        dcc.Interval(
            id='interval-component',
            interval=5 * 1000,  # 5초마다 실행 (밀리초 단위)
            n_intervals=0
        ),
        
        # Google Fonts
        html.Link(
            href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap",
            rel="stylesheet"
        ),
        
        # Main container
        dbc.Container([
            create_header(),
            create_trading_status(),
            
            # Responsive grid layout
            dbc.Row([
                # Left column (account and market data)
                dbc.Col([
                    create_strategy_card(),  # 전략 카드 추가
                    create_account_card(),
                    create_market_card(),
                ], width=12, lg=8),
                
                # Right column (performance)
                dbc.Col([
                    create_performance_card(),
                    create_signals_card(),
                ], width=12, lg=4),
            ]),
            
            # Full width row for trades
            dbc.Row([
                dbc.Col([
                    create_trades_card()
                ], width=12)
            ])
        ], fluid=True, className="py-3", id="main-container")
    ], id="main-content", style=STYLES['page'])

# 에러 메시지 컴포넌트 생성 함수
def create_error_message(message):
    """
    에러 메시지 UI 컴포넌트를 생성합니다.
    """
    return dbc.Alert(
        message,
        color="danger",
        className="m-0",
        dismissable=True
    )

# 계좌 정보 수동 새로고침 콜백 추가
@app.callback(
    Output('account-balance', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('refresh-account-btn', 'n_clicks'),
     Input('theme-stylesheet', 'href')]
)
def update_account_balance(n_intervals, n_clicks, theme_href):
    # 테마에 따른 스타일 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    # 새로고침 버튼 클릭 체크 (callback_context 없이 직접 n_clicks 검사)
    is_refresh_button_clicked = False
    try:
        # n_clicks가 None이 아니고 변경되었을 때 (1 이상일 때) 새로고침 버튼 클릭으로 간주
        if n_clicks is not None and n_clicks > 0:
            is_refresh_button_clicked = True
            # 클릭 이벤트 처리 후 n_clicks 초기화를 위해 
            # dash.no_update 반환 (이 방식은 실제로는 작동하지 않음 - 단순 참고용)
    except Exception as e:
        logger.error(f"새로고침 버튼 클릭 확인 중 오류 발생: {str(e)}")
    
    # API 호출 시도
    try:
        if is_refresh_button_clicked:
            # 수동 새로고침 버튼이 클릭된 경우 계정 정보 강제 갱신
            logger.info("계정 정보 수동 새로고침 요청됨")
            accounts = api.refresh_accounts()
        else:
            # 일반적인 인터벌 업데이트
            accounts = api.get_accounts()
        
        if not accounts:
            return dbc.Alert("계정 정보를 불러올 수 없습니다. API 연결을 확인해주세요.", color="danger", className="m-0")

        # 계좌 정보를 카드로 표시
        account_cards = []
        
        # 모든 화폐 표시로 변경
        all_currencies = set(account['currency'] for account in accounts)
        
        # 항상 표시할 코인 목록
        always_show_currencies = ['KRW', 'BTC']
        
        # 제외할 코인 목록
        excluded_currencies = ['LUNC', 'APENFT', 'LUNA2', 'BRC']
        
        # 계정에 없는 항상 표시할 코인을 위한 더미 계정 생성
        for currency in always_show_currencies:
            if currency not in all_currencies:
                logger.info(f"{currency} 계정을 찾을 수 없어 더미 계정을 생성합니다.")
                accounts.append({
                    'currency': currency,
                    'balance': '0.0',
                    'locked': '0.0',
                    'avg_buy_price': '0',
                    'avg_buy_price_modified': True
                })
        
        for account in accounts:
            try:
                currency = account['currency']
                balance = float(account['balance'])
                
                # 제외할 코인은 건너뛰기
                if currency in excluded_currencies:
                    continue
                
                # 잔액이 0인 경우에도 항상 표시할 코인이 아니면 건너뛰기
                if balance <= 0 and currency not in always_show_currencies:
                    continue
                
                locked = float(account.get('locked', 0))
                avg_buy_price = float(account.get('avg_buy_price', 0))
                
                # 티커 정보 처리
                if currency == 'KRW':
                    current_price = 1
                    total = balance + locked
                    profit_loss = 0
                    icon = "💰"
                else:
                    ticker_info = None
                    try:
                        # 티커 형식 확인 및 자동으로 KRW- 접두사 추가
                        market_id = f"KRW-{currency}" if not currency.startswith("KRW-") else currency
                        ticker = api.get_ticker(market_id)
                        
                        if ticker and len(ticker) > 0:
                            ticker_info = ticker[0]
                            logger.info(f"{currency} 티커 조회 성공: {ticker_info['trade_price']}")
                    except Exception as ticker_err:
                        logger.error(f"티커 조회 오류 ({currency}): {ticker_err}")
                    
                    # 기본 가격 정보 (API 연결 실패 시 사용)
                    default_prices = {
                        'BTC': 127000000,
                        'ETH': 5000000
                    }
                    
                    # 화폐별 아이콘 설정
                    if currency == 'BTC':
                        icon = "₿"
                    elif currency == 'ETH':
                        icon = "Ξ"
                    else:
                        icon = "🪙"
                    
                    # 티커 정보를 가져오지 못한 경우 기본 가격 사용
                    if not ticker_info:
                        if currency in default_prices:
                            logger.info(f"{currency} 티커 정보 사용 불가, 기본 가격 사용: {default_prices[currency]}")
                            current_price = default_prices[currency]
                        else:
                            current_price = avg_buy_price or 0
                            logger.warning(f"{currency} 티커 및 기본 가격 정보 없음, 평균 매수가 사용: {current_price}")
                        
                        total = (balance + locked) * current_price
                        profit_loss = total - ((balance + locked) * avg_buy_price)
                    else:
                        current_price = float(ticker_info['trade_price'])
                        total = (balance + locked) * current_price
                        profit_loss = total - ((balance + locked) * avg_buy_price)
                
                # 손익에 따른 색상 설정
                profit_loss_color = colors['buy'] if profit_loss > 0 else colors['sell'] if profit_loss < 0 else colors['text']
                
                # 카드 생성
                account_card = dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Span(icon, className="me-2 fs-4"),
                            html.Span(currency, className="fs-4 fw-bold")
                        ], className="d-flex align-items-center mb-3"),
                        
                        html.Div([
                            html.P([
                                html.Span("보유량: ", className="text-muted"),
                                html.Span(f"{balance:.8f}", className="fw-bold")
                            ], className="mb-2"),
                            
                            # 보유량+잠금 표시
                            html.P([
                                html.Span("잠금: ", className="text-muted"),
                                html.Span(f"{locked:.8f}", className="fw-bold")
                            ], className="mb-2") if locked > 0 else None,
                            
                            html.P([
                                html.Span("평가금액: ", className="text-muted"),
                                html.Span(f"{total:,.0f} KRW", className="fw-bold")
                            ], className="mb-2"),
                            
                            html.P([
                                html.Span("평균단가: ", className="text-muted"),
                                html.Span(f"{avg_buy_price:,.0f} KRW", 
                                         className="fw-bold" if currency != "KRW" else "")
                            ], className="mb-2"),
                            
                            html.P([
                                html.Span("평가손익: ", className="text-muted"),
                                html.Span(f"{profit_loss:,.0f} KRW", 
                                         className="fw-bold fs-5",
                                         style={
                                             "color": "#FFFFFF",  # 항상 흰색으로 강제 설정
                                             "text-shadow": "0px 0px 2px rgba(0,0,0,0.9)"
                                         })
                            ], className="mb-0")
                        ])
                    ], className="p-3")
                ], className="mb-3 h-100 shadow-sm")
                
                account_cards.append(account_card)
                
            except Exception as e:
                logger.error(f"계정 데이터 처리 중 오류 발생: {str(e)}")
                continue

        if not account_cards:
            return dbc.Alert("처리 가능한 계정 정보가 없습니다.", color="warning", className="m-0")

        # 계좌 정보 그리드 레이아웃
        return dbc.Row([
            dbc.Col(card, width=12, md=6) for card in account_cards
        ], className="g-3")

    except requests.exceptions.Timeout:
        logger.error("계정 정보 조회 중 타임아웃 발생")
        return dbc.Alert("서버 응답 시간이 초과되었습니다. 다시 시도해주세요.", color="danger", className="m-0")
        
    except requests.exceptions.ConnectionError:
        logger.error("계정 정보 조회 중 연결 오류 발생")
        return dbc.Alert("서버 연결에 실패했습니다. 인터넷 연결을 확인해주세요.", color="danger", className="m-0")
        
    except Exception as e:
        logger.error(f"계정 정보 업데이트 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return dbc.Alert(
            f"계정 정보를 불러오는 중 오류가 발생했습니다: {str(e)[:100]}", 
            color="danger",
            className="m-0"
        )

# 거래 내역 업데이트
@app.callback(
    Output('recent-trades', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('theme-stylesheet', 'href')]
)
def update_recent_trades(n, theme_href):
    # 테마에 따른 스타일 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        trades = api.get_order_history(market='KRW-BTC', state='done', count=5)
        
        # 거래 내역이 없는 경우 샘플 데이터 생성
        if not trades:
            logger.info("거래 내역이 없어 샘플 데이터로 표시합니다.")
            # 샘플 거래 데이터 생성
            sample_trades = [
                {
                    'created_at': (datetime.now() - timedelta(hours=i)).isoformat(),
                    'market': 'KRW-BTC',
                    'side': 'bid' if i % 2 == 0 else 'ask',
                    'price': 50000000 * (1 + (i * 0.001)),
                    'volume': 0.0005 * (1 + (i * 0.1)),
                    'trades_price': 50000000 * (1 + (i * 0.002)),
                    'executed_volume': 0.0004 * (1 + (i * 0.05)),
                    'is_sample': True  # 샘플 데이터 표시
                } for i in range(5)
            ]
            trades = sample_trades
        
        # 거래 내역 테이블
        headers = [
            "시간", "마켓", "종류", "체결가격", "체결수량", "체결금액"
        ]
        
        rows = []
        total_profit_loss = 0
        has_sample_data = False
        
        for trade in trades:
            try:
                # 샘플 데이터 표시 여부 확인
                if trade.get('is_sample', False):
                    has_sample_data = True
                
                # 안전하게 데이터 추출
                # 날짜가 없는 경우 현재 시간 사용
                created_at = trade.get('created_at', datetime.now().isoformat())
                try:
                    # 거래 시간 변환 (UTC to KST)
                    trade_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    trade_time = trade_time.astimezone(timezone(timedelta(hours=9)))  # UTC+9 (KST)
                except Exception as e:
                    logger.error(f"날짜 변환 오류: {str(e)}")
                    trade_time = datetime.now()  # 오류 시 현재 시간 사용
                
                # 거래 정보 추출 (기본값 사용)
                market = trade.get('market', 'N/A')
                side = "매수" if trade.get('side', '') == 'bid' else "매도"
                
                # 가격 및 수량 안전하게 추출
                try:
                    # 체결가격 (trades_price가 없는 경우 price 사용, 둘 다 없으면 0)
                    price = float(trade.get('trades_price', trade.get('price', 0)))
                    volume = float(trade.get('executed_volume', trade.get('volume', 0)))
                    total = price * volume
                except (ValueError, TypeError) as e:
                    logger.error(f"가격/수량 변환 오류: {str(e)}")
                    price = 0
                    volume = 0
                    total = 0

                # 거래 종류에 따른 스타일
                side_color = colors['buy'] if side == "매수" else colors['sell']

                # 행 데이터
                row = [
                    trade_time.strftime("%Y-%m-%d %H:%M:%S"),
                    market,
                    html.Span(side, style={"color": side_color, "fontWeight": "bold"}),
                    f"{price:,.0f}",
                    f"{volume:.8f}",
                    html.Span(f"{total:,.0f}", style={"fontWeight": "bold"})
                ]
                rows.append(row)

                # 수익률 계산을 위한 누적
                if side == "매도":
                    total_profit_loss += total
                else:
                    total_profit_loss -= total

            except Exception as e:
                logger.error(f"거래 데이터 처리 중 오류 발생: {str(e)}, 데이터: {trade}")
                continue

        if not rows:
            return dbc.Alert("거래 내역을 처리할 수 없습니다.", color="warning", className="m-0")

        # 거래 내역 테이블 생성
        table = dbc.Table(
            # 헤더
            [html.Thead(html.Tr([html.Th(h) for h in headers], className="table-light"))] +
            # 바디
            [html.Tbody([html.Tr([html.Td(cell) for cell in row]) for row in rows])],
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            className="mb-0"
        )

        # 샘플 데이터 알림
        sample_notice = dbc.Alert(
            "※ 현재 샘플 데이터가 표시되고 있습니다. 실제 거래 내역이 생성되면 자동으로 업데이트됩니다.",
            color="warning",
            className="mt-3 mb-0",
            style={"display": "block" if has_sample_data else "none"}
        )

        # 수익률 요약
        profit_loss_color = "success" if total_profit_loss > 0 else "danger" if total_profit_loss < 0 else "secondary"
        profit_loss_summary = dbc.Alert(
            [
                html.Span("최근 거래 실현 손익: ", className="fw-bold me-2"),
                html.Span(f"{total_profit_loss:,.0f} KRW", className="fs-5")
            ],
            color=profit_loss_color,
            className="mt-3 mb-0 text-center"
        )

        return html.Div([table, profit_loss_summary, sample_notice])

    except Exception as e:
        logger.error(f"거래 내역 업데이트 중 오류 발생: {str(e)}")
        return dbc.Alert(
            f"거래 내역을 불러오는 중 오류가 발생했습니다: {str(e)[:100]}", 
            color="danger",
            className="m-0"
        )

# 시장 데이터 업데이트 및 캔들 차트 생성 콜백
@app.callback(
    Output('price-chart', 'figure'),
    [Input('interval-component', 'n_intervals'),
     Input('market-dropdown', 'value'),
     Input('theme-stylesheet', 'href')]  # 테마 변경에 따른 차트 스타일 업데이트
)
def update_price_chart(n, selected_market, theme_href):
    if not selected_market:
        return create_empty_figure("마켓을 선택해주세요")

    # 테마에 따른 차트 색상 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        # 가격 데이터 가져오기 (1시간 캔들, 최근 100개)
        candles = api.get_candles(selected_market, interval='minutes', count=60, unit=1)
        
        if not candles or len(candles) < 5:
            return create_empty_figure(f"{selected_market} 데이터를 불러올 수 없습니다")
            
        # 데이터 캐시에 저장
        data_cache['market_data'][selected_market] = {
            'candles': candles,
            'last_update': datetime.now()
        }
        
        # 데이터프레임 변환
        df = pd.DataFrame(candles)
        df['candle_date_time_kst'] = pd.to_datetime(df['candle_date_time_kst'])
        
        # OHLC 데이터
        dates = df['candle_date_time_kst']
        opens = df['opening_price']
        highs = df['high_price']
        lows = df['low_price']
        closes = df['trade_price']
        volumes = df['candle_acc_trade_volume']
        
        # 최근 시장 방향에 따른 색상
        is_uptrend = closes.iloc[-1] >= opens.iloc[-1]
        candle_color = colors['buy'] if is_uptrend else colors['sell']
        vol_color = colors['buy'] if is_uptrend else colors['sell']
        
        # 캔들스틱 차트 생성
        fig = go.Figure()
        
        # 캔들스틱 추가
        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=opens,
                high=highs,
                low=lows,
                close=closes,
                name='가격',
                increasing=dict(line=dict(color=colors['buy'])),
                decreasing=dict(line=dict(color=colors['sell']))
            )
        )
        
        # 거래량 바 차트 추가 (subplots 형태)
        fig.add_trace(
            go.Bar(
                x=dates,
                y=volumes,
                name='거래량',
                marker=dict(color=vol_color, opacity=0.5),
                yaxis='y2'
            )
        )
        
        # 레이아웃 설정
        fig.update_layout(
            title=f'{selected_market} 실시간 차트',
            xaxis_title='시간',
            yaxis_title='가격 (KRW)',
            yaxis2=dict(
                title='거래량',
                overlaying='y',
                side='right',
                showgrid=False
            ),
            height=500,
            margin=dict(l=50, r=50, t=50, b=50, pad=4),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode='x unified',
            # 테마별 스타일 설정
            template='plotly_dark' if is_dark_theme else 'plotly_white',
            paper_bgcolor=colors['card_bg'],
            plot_bgcolor=colors['card_bg'],
            font=dict(color=colors['text'])
        )
        
        # X축 레이아웃
        fig.update_xaxes(
            showgrid=True,
            gridcolor=colors['grid'],
            zeroline=False,
            rangeslider=dict(visible=False)
        )
        
        # Y축 레이아웃
        fig.update_yaxes(
            showgrid=True,
            gridcolor=colors['grid'],
            zeroline=False
        )
        
        # 최근 가격 주석 추가
        last_price = closes.iloc[-1]
        last_time = dates.iloc[-1]
        fig.add_annotation(
            x=last_time,
            y=last_price,
            text=f"{last_price:,.0f}원",
            showarrow=True,
            arrowhead=2,
            arrowcolor=candle_color,
            arrowsize=1,
            arrowwidth=2,
            bgcolor=colors['card_bg'],
            bordercolor=candle_color,
            borderwidth=2,
            borderpad=4,
            font=dict(size=14, color=colors['text'])
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"차트 업데이트 중 오류 발생: {str(e)}")
        return create_empty_figure(f"오류: {str(e)[:100]}")

# 트레이딩 신호 차트 업데이트
@app.callback(
    Output('signals-chart', 'figure'),
    [Input('interval-component', 'n_intervals'),
     Input('market-dropdown', 'value'),
     Input('theme-stylesheet', 'href')]
)
def update_signals_chart(n, selected_market, theme_href):
    if not selected_market:
        return create_empty_figure("마켓을 선택해주세요")
    
    # 테마에 따른 차트 색상 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        # 샘플 신호 데이터 생성 (실제로는 트레이딩 엔진에서 가져와야 함)
        # TODO: 실제 트레이딩 엔진에서 신호 데이터 가져오도록 수정
        now = datetime.now()
        signal_times = [now - timedelta(hours=i) for i in range(10, 0, -1)]
        
        # 간단한 샘플 신호 생성 (실제로는 트레이딩 엔진의 신호 사용)
        signals = []
        for i, time in enumerate(signal_times):
            signal_type = "BUY" if i % 3 == 0 else "SELL" if i % 3 == 1 else "HOLD"
            signals.append({
                'time': time,
                'type': signal_type,
                'strategy': 'SMA' if i % 2 == 0 else 'RSI',
                'price': 80000000 + (i * 100000)
            })
        
        fig = go.Figure()
        
        # 시간 축
        times = [s['time'] for s in signals]
        prices = [s['price'] for s in signals]
        
        # 신호 점 표시
        buy_signals = [s for s in signals if s['type'] == 'BUY']
        sell_signals = [s for s in signals if s['type'] == 'SELL']
        
        # 매수 신호
        if buy_signals:
            buy_times = [s['time'] for s in buy_signals]
            buy_prices = [s['price'] for s in buy_signals]
            buy_texts = [f"{s['strategy']} 매수 신호<br>{s['price']:,}원" for s in buy_signals]
            
            fig.add_trace(go.Scatter(
                x=buy_times,
                y=buy_prices,
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=15,
                    color=colors['buy'],
                    line=dict(width=2, color=colors['card_bg'])
                ),
                name='매수 신호',
                text=buy_texts,
                hoverinfo='text'
            ))
        
        # 매도 신호
        if sell_signals:
            sell_times = [s['time'] for s in sell_signals]
            sell_prices = [s['price'] for s in sell_signals]
            sell_texts = [f"{s['strategy']} 매도 신호<br>{s['price']:,}원" for s in sell_signals]
            
            fig.add_trace(go.Scatter(
                x=sell_times,
                y=sell_prices,
                mode='markers',
                marker=dict(
                    symbol='triangle-down',
                    size=15,
                    color=colors['sell'],
                    line=dict(width=2, color=colors['card_bg'])
                ),
                name='매도 신호',
                text=sell_texts,
                hoverinfo='text'
            ))
        
        # 가격 라인
        fig.add_trace(go.Scatter(
            x=times,
            y=prices,
            mode='lines',
            line=dict(width=2, color=colors['primary']),
            name='가격'
        ))
        
        # 레이아웃 설정
        fig.update_layout(
            title="최근 10개 트레이딩 신호",
            xaxis_title="시간",
            yaxis_title="가격 (KRW)",
            height=300,
            margin=dict(l=50, r=50, t=50, b=50, pad=4),
            hovermode='closest',
            # 테마별 스타일 설정
            template='plotly_dark' if is_dark_theme else 'plotly_white',
            paper_bgcolor=colors['card_bg'],
            plot_bgcolor=colors['card_bg'],
            font=dict(color=colors['text']),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # X축 레이아웃
        fig.update_xaxes(
            showgrid=True,
            gridcolor=colors['grid'],
            zeroline=False
        )
        
        # Y축 레이아웃
        fig.update_yaxes(
            showgrid=True,
            gridcolor=colors['grid'],
            zeroline=False
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"신호 차트 업데이트 중 오류 발생: {str(e)}")
        return create_empty_figure(f"오류: {str(e)[:100]}")

# 성능 차트 업데이트
@app.callback(
    Output('performance-chart', 'figure'),
    [Input('interval-component', 'n_intervals'),
     Input('theme-stylesheet', 'href')]
)
def update_performance_chart(n, theme_href):
    # 테마에 따른 차트 색상 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        # 샘플 데이터 생성 (필요한 경우)
        if 'dates' not in data_cache['performance'] or not data_cache['performance'].get('dates'):
            # 데이터 구조 초기화
            data_cache['performance'] = {
                'dates': [],
                'pnl': [],
                'cumulative_pnl': []
            }
            
            # 샘플 데이터 생성 (지난 30일)
            start_date = datetime.now() - timedelta(days=30)
            cumulative_pnl = 0
            
            for i in range(30):
                date = start_date + timedelta(days=i)
                
                # 더 자연스러운 PnL 변동 패턴
                if i == 0:
                    daily_pnl = 0
                else:
                    # 랜덤하면서도 추세가 있는 패턴
                    trend = 0.6 if i % 10 < 6 else -0.4  # 60% 상승, 40% 하락 경향
                    volatility = np.random.normal(trend, 0.5) * 10000
                    daily_pnl = volatility
                
                cumulative_pnl += daily_pnl
                
                data_cache['performance']['dates'].append(date)
                data_cache['performance']['pnl'].append(daily_pnl)
                data_cache['performance']['cumulative_pnl'].append(cumulative_pnl)
        
        # 성능 차트 생성
        fig = go.Figure()
        
        # 누적 수익/손실 라인
        cumulative_pnl = data_cache['performance']['cumulative_pnl']
        dates = data_cache['performance']['dates']
        is_profit = cumulative_pnl[-1] >= 0
        line_color = colors['buy'] if is_profit else colors['sell']
        
        # 메인 라인 차트
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=cumulative_pnl,
                mode='lines',
                name='누적 손익',
                line=dict(width=3, color=line_color),
                fill='tozeroy',
                fillcolor=f'rgba({int(line_color[1:3], 16)}, {int(line_color[3:5], 16)}, {int(line_color[5:7], 16)}, 0.2)'  # 20% 투명도의 rgba 색상
            )
        )
        
        # 일간 수익/손실 바 차트
        daily_pnl = data_cache['performance']['pnl']
        bar_colors = [colors['buy'] if pnl >= 0 else colors['sell'] for pnl in daily_pnl]
        
        # 바 차트 추가 (yaxis2에 표시)
        fig.add_trace(
            go.Bar(
                x=dates,
                y=daily_pnl,
                name='일간 손익',
                marker_color=bar_colors,
                opacity=0.7,
                yaxis='y2'
            )
        )
        
        # 레이아웃 설정
        fig.update_layout(
            title='누적 손익 추이',
            xaxis_title='날짜',
            yaxis=dict(
                title='누적 손익 (KRW)',
                side='left',
                showgrid=True,
                gridcolor=colors['grid']
            ),
            yaxis2=dict(
                title='일간 손익 (KRW)',
                overlaying='y',
                side='right',
                showgrid=False
            ),
            height=350,
            margin=dict(l=50, r=50, t=50, b=50, pad=4),
            hovermode='x unified',
            # 테마별 스타일 설정
            template='plotly_dark' if is_dark_theme else 'plotly_white',
            paper_bgcolor=colors['card_bg'],
            plot_bgcolor=colors['card_bg'],
            font=dict(color=colors['text']),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # X축 레이아웃
        fig.update_xaxes(
            showgrid=True,
            gridcolor=colors['grid'],
            zeroline=False
        )
        
        # 최종 수익/손실 주석 추가
        final_pnl = cumulative_pnl[-1]
        final_date = dates[-1]
        
        fig.add_annotation(
            x=final_date,
            y=final_pnl,
            text=f"현재 누적 손익: {final_pnl:,.0f}원",
            showarrow=True,
            arrowhead=2,
            arrowcolor=line_color,
            arrowsize=1,
            arrowwidth=2,
            bgcolor=colors['card_bg'],
            bordercolor=line_color,
            borderwidth=2,
            borderpad=4,
            font=dict(size=12, color=colors['text'])
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"성능 차트 업데이트 중 오류: {e}")
        return create_empty_figure(f"성능 데이터를 불러올 수 없습니다: {str(e)[:100]}")

# 트레이딩 시작/중지 콜백
@app.callback(
    Output("trading-status", "children"),
    [Input("start-trading-btn", "n_clicks"),
     Input("stop-trading-btn", "n_clicks"),
     Input("interval-component", "n_intervals")]  # 주기적 업데이트 추가
)
def control_trading(start_clicks, stop_clicks, n_intervals):
    # callback_context 관련 오류 방지를 위한 안전한 접근 방식
    triggered_by_start = False
    triggered_by_stop = False
    
    try:
        ctx = dash.callback_context
        if ctx.triggered:
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            triggered_by_start = button_id == "start-trading-btn" and start_clicks and start_clicks > 0
            triggered_by_stop = button_id == "stop-trading-btn" and stop_clicks and stop_clicks > 0
    except Exception as e:
        logger.error(f"콜백 컨텍스트 확인 중 오류 발생: {str(e)}")
        # 콜백 컨텍스트를 사용할 수 없는 경우 직접 n_clicks로 판단
        # 이전 상태를 저장하는 로직이 없으므로 완벽하지는 않음
        if start_clicks and start_clicks > 0:
            triggered_by_start = True
        if stop_clicks and stop_clicks > 0:
            triggered_by_stop = True
    
    # 버튼 클릭 이벤트 처리
    if triggered_by_start:
        if TRADING_ENGINE:
            logger.info("대시보드에서 거래 시작 버튼이 클릭되었습니다.")
            TRADING_ENGINE.start()
            
            # 거래 활성화 상태 확인 및 강제 설정
            if not TRADING_ENGINE.is_trading_enabled:
                TRADING_ENGINE.is_trading_enabled = True
                logger.info("거래 기능이 강제로 활성화되었습니다.")
                
            logger.info(f"거래 엔진 시작 완료. 거래 활성화 상태: {TRADING_ENGINE.is_trading_enabled}")
            return get_trading_status_text()  # 실제 상태 반영
        else:
            logger.warning("거래 엔진이 초기화되지 않았습니다.")
            return "트레이딩 상태: 엔진 미초기화"
    
    elif triggered_by_stop:
        if TRADING_ENGINE:
            logger.info("대시보드에서 거래 중지 버튼이 클릭되었습니다.")
            TRADING_ENGINE.stop()
            logger.info("거래 엔진 중지 완료")
            return get_trading_status_text()  # 실제 상태 반영
        else:
            logger.warning("거래 엔진이 초기화되지 않았습니다.")
            return "트레이딩 상태: 엔진 미초기화"
    
    # 주기적 업데이트 또는 초기 로드인 경우 실제 상태 반영
    return get_trading_status_text()

# 테마 전환 콜백
@app.callback(
    Output("theme-stylesheet", "href"),
    [Input("light-mode-btn", "n_clicks"),
     Input("dark-mode-btn", "n_clicks")]
)
def toggle_theme(light_clicks, dark_clicks):
    global current_theme
    
    ctx = dash.callback_context
    if not ctx.triggered:
        # 초기 로드 시 현재 설정된 테마 사용
        return THEMES[current_theme]
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "light-mode-btn":
        current_theme = 'LIGHT'
    elif button_id == "dark-mode-btn":
        current_theme = 'DARK'
    
    return THEMES[current_theme]

# 테마 변경에 따른 UI 스타일 업데이트
@app.callback(
    Output('main-content', 'style'),
    [Input('theme-stylesheet', 'href')]
)
def update_styles_on_theme_change(theme_href):
    global current_theme
    # 테마 변경에 따른 스타일 업데이트
    current_theme = 'LIGHT' if 'FLATLY' in theme_href else 'DARK'
    STYLES = get_current_styles()
    return STYLES['page']

# 트레이딩 상태 정보를 가져오는 헬퍼 함수 추가
def get_trading_status_text():
    """현재 트레이딩 엔진의 실제 상태를 확인하여 UI에 표시할 텍스트를 반환합니다."""
    if not TRADING_ENGINE:
        return "트레이딩 상태: 엔진 미초기화"
    
    if TRADING_ENGINE.running and TRADING_ENGINE.is_trading_enabled:
        return "트레이딩 상태: 실행 중"
    elif TRADING_ENGINE.running and not TRADING_ENGINE.is_trading_enabled:
        return "트레이딩 상태: 엔진 실행 중 (거래 비활성화)"
    else:
        return "트레이딩 상태: 중지됨"

# 비트코인 시장 지표 업데이트 콜백 추가
@app.callback(
    Output('bitcoin-indicators', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('theme-stylesheet', 'href')]
)
def update_bitcoin_indicators(n, theme_href):
    """비트코인 시장 지표를 업데이트합니다."""
    # 테마에 따른 스타일 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        # 비트코인 티커 정보 조회
        ticker = api.get_ticker('KRW-BTC')
        
        if not ticker or len(ticker) == 0:
            return dbc.Alert("비트코인 시장 지표를 불러올 수 없습니다.", color="warning", className="m-0")
        
        ticker_data = ticker[0]
        
        # 시장 지표 추출
        current_price = ticker_data.get('trade_price', 0)
        prev_closing_price = ticker_data.get('prev_closing_price', 0)
        high_price = ticker_data.get('high_price', 0)
        low_price = ticker_data.get('low_price', 0)
        acc_trade_volume_24h = ticker_data.get('acc_trade_volume_24h', 0)
        acc_trade_price_24h = ticker_data.get('acc_trade_price_24h', 0)
        
        # 가격 변동 계산
        price_change = current_price - prev_closing_price
        price_change_percent = (price_change / prev_closing_price * 100) if prev_closing_price else 0
        
        # 상승/하락에 따른 색상 설정
        price_color = colors['buy'] if price_change >= 0 else colors['sell']
        
        # 지표 표시
        indicators = [
            dbc.Row([
                dbc.Col([
                    html.H5("비트코인 시장 지표", className="mb-3"),
                    
                    # 현재가와 변동률
                    dbc.Row([
                        dbc.Col([
                            html.P("현재가", className="text-muted mb-1"),
                            html.H3([
                                f"{current_price:,.0f} KRW ",
                                html.Small(
                                    f"({price_change_percent:+.2f}%)",
                                    style={"color": price_color}
                                )
                            ], className="mb-3")
                        ], width=12)
                    ]),
                    
                    # 주요 지표 (고가, 저가, 거래량)
                    dbc.Row([
                        dbc.Col([
                            html.P("고가", className="text-muted mb-1"),
                            html.H6(f"{high_price:,.0f} KRW", className="mb-3")
                        ], width=6),
                        dbc.Col([
                            html.P("저가", className="text-muted mb-1"),
                            html.H6(f"{low_price:,.0f} KRW", className="mb-3")
                        ], width=6),
                    ]),
                    
                    dbc.Row([
                        dbc.Col([
                            html.P("24시간 거래량", className="text-muted mb-1"),
                            html.H6(f"{acc_trade_volume_24h:.4f} BTC", className="mb-3")
                        ], width=6),
                        dbc.Col([
                            html.P("24시간 거래대금", className="text-muted mb-1"),
                            html.H6(f"{acc_trade_price_24h/1000000:,.2f} 백만원", className="mb-3")
                        ], width=6),
                    ]),
                ], width=12)
            ])
        ]
        
        return dbc.Card(dbc.CardBody(indicators), className="mt-3")
        
    except requests.exceptions.Timeout:
        logger.error("비트코인 시장 지표 조회 중 타임아웃 발생")
        return dbc.Alert("서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.", color="warning", className="m-0")
        
    except requests.exceptions.ConnectionError:
        logger.error("비트코인 시장 지표 조회 중 연결 오류 발생")
        return dbc.Alert("서버 연결에 실패했습니다. 인터넷 연결을 확인해주세요.", color="warning", className="m-0")
        
    except Exception as e:
        logger.error(f"비트코인 시장 지표 업데이트 중 오류: {str(e)}")
        traceback.print_exc()
        return dbc.Alert(f"비트코인 시장 지표를 업데이트하는 중 오류 발생: {str(e)[:100]}", color="danger", className="m-0")

# 전략 정보 업데이트 콜백 추가
@app.callback(
    Output('strategy-info', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('refresh-strategy-btn', 'n_clicks'),
     Input('theme-stylesheet', 'href')]
)
def update_strategy_info(n_intervals, n_clicks, theme_href):
    """거래 전략 정보를 업데이트합니다."""
    # 테마에 따른 스타일 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        # 전략 정보 생성
        strategies = []
        
        # SMA 전략 정보
        strategies.append({
            'name': 'SMA 교차 전략',
            'description': '단기(5일선)가 장기(20일선)를 상향돌파하면 매수, 하향돌파하면 매도',
            'params': {
                '단기 이동평균': '5일',
                '장기 이동평균': '20일',
                '시그널 체크': '크로스오버 감지'
            }
        })
        
        # RSI 전략 정보
        strategies.append({
            'name': 'RSI 전략',
            'description': 'RSI 지표가 과매도 영역에서 반등 시 매수, 과매수 영역에서 하락 시 매도',
            'params': {
                '기간': '14일', 
                '과매수 기준': '70 이상',
                '과매도 기준': '30 이하'
            }
        })
        
        # 볼린저 밴드 전략 정보
        strategies.append({
            'name': '볼린저 밴드 전략',
            'description': '가격이 하단밴드 아래로 내려가면 매수, 상단밴드 위로 올라가면 매도',
            'params': {
                '이동평균 기간': '20일',
                '표준편차 배수': '2.0',
                '밴드 폭': '밴드폭 기준 거래 없음'
            }
        })
        
        # 리스크 관리 정보
        risk_management = {
            'profit_target': '5%',  # 익절 목표
            'stop_loss': '3%',       # 손절 기준
            'max_position': '계정 잔액의 30%',  # 최대 포지션 크기
            'min_order': '5,000원',  # 최소 주문 금액
            'trading_on': TRADING_ENGINE.is_trading_enabled if TRADING_ENGINE else False
        }
        
        # 전략 카드 생성
        strategy_cards = []
        
        # 리스크 관리 카드 생성
        risk_card = dbc.Card([
            dbc.CardHeader(html.H6("리스크 관리 설정", className="m-0 fw-bold text-primary")),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.P([
                            html.Span("익절 목표: ", className="text-muted"),
                            html.Span(risk_management['profit_target'], className="fw-bold")
                        ], className="mb-2"),
                        html.P([
                            html.Span("손절 기준: ", className="text-muted"),
                            html.Span(risk_management['stop_loss'], className="fw-bold")
                        ], className="mb-2"),
                    ], width=6),
                    dbc.Col([
                        html.P([
                            html.Span("최대 포지션: ", className="text-muted"),
                            html.Span(risk_management['max_position'], className="fw-bold")
                        ], className="mb-2"),
                        html.P([
                            html.Span("최소 주문액: ", className="text-muted"),
                            html.Span(risk_management['min_order'], className="fw-bold")
                        ], className="mb-2"),
                        html.P([
                            html.Span("거래 활성화: ", className="text-muted"),
                            html.Span(
                                "활성화" if risk_management['trading_on'] else "비활성화", 
                                className="fw-bold",
                                style={"color": colors['buy'] if risk_management['trading_on'] else colors['sell']}
                            )
                        ], className="mb-0"),
                    ], width=6),
                ]),
            ])
        ], className="mb-3 shadow-sm")
        
        strategy_cards.append(risk_card)
        
        # 개별 전략 카드 생성
        for i, strategy in enumerate(strategies):
            strategy_card = dbc.Card([
                dbc.CardHeader(html.H6(strategy['name'], className="m-0 fw-bold text-primary")),
                dbc.CardBody([
                    html.P(strategy['description'], className="mb-3 small"),
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Span(key + ": ", className="text-muted small"),
                                html.Span(value, className="fw-bold small")
                            ], width="auto", className="me-3 mb-2")
                            for key, value in strategy['params'].items()
                        ], className="g-0")
                    ])
                ])
            ], className="mb-3 shadow-sm")
            
            strategy_cards.append(strategy_card)
        
        return html.Div(strategy_cards)
        
    except Exception as e:
        logger.error(f"전략 정보 업데이트 중 오류 발생: {str(e)}")
        return dbc.Alert(
            f"전략 정보를 불러오는 중 오류가 발생했습니다: {str(e)[:100]}", 
            color="danger",
            className="m-0"
        )

# 빈 차트 생성 함수
def create_empty_figure(message="데이터가 없습니다"):
    # 현재 테마 확인
    is_dark_theme = current_theme == 'DARK'
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    fig = go.Figure()
    
    # 메시지 추가
    fig.add_annotation(
        x=0.5, y=0.5,
        xref="paper", yref="paper",
        text=message,
        showarrow=False,
        font=dict(size=16, color=colors['text'])
    )
    
    # 레이아웃 설정
    fig.update_layout(
        height=400,
        paper_bgcolor=colors['card_bg'],
        plot_bgcolor=colors['card_bg'],
        font=dict(color=colors['text']),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    )
    
    return fig

# 기존 레이아웃 대체
app.layout = create_layout()

def run_dashboard():
    """대시보드를 실행합니다"""
    initialize_data()  # 데이터 초기화 확실히 실행
    logger.info("Dashboard 데이터 초기화 완료")
    app.run(
        host=DASHBOARD_CONFIG['host'],
        port=DASHBOARD_CONFIG['port'],
        debug=DASHBOARD_CONFIG.get('debug', False)
    )

if __name__ == '__main__':
    run_dashboard()