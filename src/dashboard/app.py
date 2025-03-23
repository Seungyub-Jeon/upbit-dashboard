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
        'buy': '#00BC8C',
        'sell': '#E74C3C',
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
        'buy': '#28A745',
        'sell': '#DC3545',
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
    return dbc.Card([
        dbc.CardHeader(html.H3("계좌 잔액", className="card-title h5 text-primary fw-bold")),
        dbc.CardBody(id="account-balance", className="px-0")
    ], className="mb-4 shadow-sm")

# Market data card with candle chart
def create_market_card():
    return dbc.Card([
        dbc.CardHeader(html.H3("시장 데이터", className="card-title h5 text-primary fw-bold")),
        dbc.CardBody([
            dcc.Dropdown(
                id='market-dropdown',
                options=[{'label': market, 'value': market} for market in markets],
                value=markets[0] if markets else None,
                clearable=False,
                className="mb-3"
            ),
            dcc.Graph(id='price-chart', config={'displayModeBar': True, 'scrollZoom': True})
        ])
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

# Layout with responsive grid
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    
    # 테마 스타일시트 (콜백으로 동적 변경)
    dcc.Link(
        rel='stylesheet',
        href=THEMES[current_theme],
        id='theme-stylesheet'
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

# 계좌 정보 업데이트
@app.callback(
    Output('account-balance', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('theme-stylesheet', 'href')]
)
def update_account_balance(n, theme_href):
    # 테마에 따른 스타일 결정
    is_dark_theme = 'DARKLY' in theme_href if theme_href else True
    color_theme = 'dark' if is_dark_theme else 'light'
    colors = COLORS[color_theme]
    
    try:
        accounts = api.get_accounts()
        
        if not accounts:
            return dbc.Alert("계정 정보를 불러올 수 없습니다.", color="danger", className="m-0")

        # 계좌 정보를 카드로 표시
        account_cards = []
        
        # BTC와 KRW만 표시
        allowed_currencies = ['BTC', 'KRW']
        
        for account in accounts:
            try:
                currency = account['currency']
                if currency not in allowed_currencies:
                    continue

                balance = float(account['balance'])
                avg_buy_price = float(account.get('avg_buy_price', 0))
                
                if currency == 'KRW':
                    current_price = 1
                    total = balance
                    profit_loss = 0
                    icon = "💰"
                else:
                    ticker = api.get_ticker(f"KRW-{currency}")
                    if ticker:
                        current_price = float(ticker[0]['trade_price'])
                        total = balance * current_price
                        profit_loss = total - (balance * avg_buy_price)
                    else:
                        current_price = avg_buy_price
                        total = balance * current_price
                        profit_loss = 0
                    icon = "₿"

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
                                         className="fw-bold",
                                         style={"color": profit_loss_color})
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

    except Exception as e:
        logger.error(f"계정 정보 업데이트 중 오류 발생: {str(e)}")
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
    ctx = dash.callback_context
    
    # 콜백이 어떤 입력에 의해 트리거되었는지 확인
    if not ctx.triggered:
        # 초기 로드 시 실제 엔진 상태 반영
        return get_trading_status_text()
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 버튼 클릭 이벤트 처리
    if button_id == "start-trading-btn":
        if TRADING_ENGINE:
            logger.info("대시보드에서 거래 시작 버튼이 클릭되었습니다.")
            TRADING_ENGINE.start()
            logger.info("거래 엔진 시작 완료")
            return get_trading_status_text()  # 실제 상태 반영
        else:
            logger.warning("거래 엔진이 초기화되지 않았습니다.")
            return "트레이딩 상태: 엔진 미초기화"
    
    elif button_id == "stop-trading-btn":
        if TRADING_ENGINE:
            logger.info("대시보드에서 거래 중지 버튼이 클릭되었습니다.")
            TRADING_ENGINE.stop()
            logger.info("거래 엔진 중지 완료")
            return get_trading_status_text()  # 실제 상태 반영
        else:
            logger.warning("거래 엔진이 초기화되지 않았습니다.")
            return "트레이딩 상태: 엔진 미초기화"
    
    # 주기적 업데이트인 경우 (interval-component)
    elif button_id == "interval-component":
        # 항상 최신 상태 반영
        return get_trading_status_text()
    
    # 다른 경우 (예상치 못한 트리거)
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