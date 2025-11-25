import pyupbit
import pandas as pd
import numpy as np
import datetime
import os
import time
import sys

APP_VERSION = "v0s.00.00" 

# --- 설정 변수 ---
TARGET_STRATEGY = '5분봉_50선_트레이딩'
TIMEFRAME = 'minute5'
# 초기자본 100만원 설정
SIMULATION_INITIAL_BALANCE = 1000000 
# 최소 거래 가능 금액 설정 (Upbit 최소 주문 금액 기준)
MIN_TRADE_KRW = 5000
# SIMULATION_STOP_LOSS_RATE = 0.007 # 0.7% (코드 로직 기반)
SIMULATION_STOP_LOSS_RATE = 0.005 # 0.5% (0.5로 변경)

# 거래 수수료율 (Upbit API 표준 0.05% 적용)
FEE_RATE = 0.0005 
# -----------------

class Backtester:
    """
    Upbit 5분봉 50선 트레이딩 전략 백테스팅 시뮬레이터
    """
    def __init__(self, ticker, period_label):
        self.ticker = ticker
        self.period_label = period_label
        self.transactions = []
        self.holdings = {}
        # 초기 잔고 설정
        self.initial_balance = SIMULATION_INITIAL_BALANCE 
        self.current_balance = SIMULATION_INITIAL_BALANCE # 가용 현금 추적
        self.buy_candle_time = {}
        
    def _calculate_moving_average(self, df, window):
        """이동평균(Moving Average) 계산"""
        return df['close'].rolling(window=window, min_periods=window).mean()

    def _calculate_vwma(self, df, window):
        """거래량 가중 이동평균(VWMA) 계산"""
        pv_sum = (df['close'] * df['volume']).rolling(window=window, min_periods=window).sum()
        v_sum = df['volume'].rolling(window=window, min_periods=window).sum()
        return pv_sum / v_sum

    def _get_start_time(self):
        """기간 설정에 따른 데이터 시작 시간 계산"""
        now = datetime.datetime.now()
        if self.period_label == '1일':
            return now - datetime.timedelta(days=1)
        elif self.period_label == '1주일':
            return now - datetime.timedelta(weeks=1)
        elif self.period_label == '1개월':
            return now - datetime.timedelta(days=30)
        elif self.period_label == '3개월':
            return now - datetime.timedelta(days=90)
        elif self.period_label == '6개월':
            return now - datetime.timedelta(days=180) 
        elif self.period_label == '1년':
            return now - datetime.timedelta(days=365) # 1년 데이터 로드 설정
        else:
            raise ValueError("유효하지 않은 기간 설정입니다.")

    def _load_data(self):
        """Upbit에서 OHLCV 데이터 로드 및 지표 계산 (진행률 표시 포함)"""
        
        start_time_dt = self._get_start_time()
        
        # 5분봉 캔들 1개의 초 = 300초
        num_candles_for_period = int( (datetime.datetime.now() - start_time_dt).total_seconds() / 300 )
        
        # 지표 계산 안전 마진을 500개로 설정
        required_load_count = num_candles_for_period + 500 
        
        # 💡 수정된 부분: 최대 로드 캔들 수를 120,000개로 상향 조정
        MAX_CANDLE_LOAD = 120000 
        max_load_count = min(required_load_count, MAX_CANDLE_LOAD) 
        
        print(f"\n[{self.ticker}] {self.period_label} 데이터 로드 중 (목표 캔들 수: {max_load_count}개) ...")
        
        all_df = []
        to_time = datetime.datetime.now()
        last_progress_time = time.time()
        
        current_total_count = 0
        while current_total_count < max_load_count:
            try:
                # 5분봉 로드 (200개씩 청크 로드)
                df_chunk = pyupbit.get_ohlcv(self.ticker, interval=TIMEFRAME, to=to_time, count=200)
            except Exception as e:
                print(f"\n⚠️ 데이터 로드 중 오류 발생: {e}. 잠시 후 재시도합니다.")
                time.sleep(1)
                continue
            
            if df_chunk is None or df_chunk.empty:
                break
            
            all_df.append(df_chunk)
            to_time = df_chunk.index[0] 

            current_total_count = sum(len(df) for df in all_df) 
            
            # 15초에 한번씩 진행률 표시
            if time.time() - last_progress_time > 15:
                print(f"  > 로드된 캔들: {current_total_count} / 목표치: {max_load_count} ({current_total_count/max_load_count*100:.2f}%)")
                last_progress_time = time.time()
            
            if len(df_chunk) < 200: 
                break
                
            time.sleep(0.1) # API 요청 딜레이 유지 (안전성 확보)

        if not all_df:
            print("데이터 로드 실패: 데이터를 가져올 수 없습니다.")
            return pd.DataFrame()

        df = pd.concat(all_df).drop_duplicates().sort_index()
        
        # 500개 캔들 전부터 데이터를 유지합니다.
        df = df[df.index >= start_time_dt - datetime.timedelta(minutes=5 * 500)]
        
        print(f"\n총 {len(df)}개 캔들 로드 완료. (시작: {df.index.min()}, 종료: {df.index.max()})")

        # 지표 계산
        df['MA50'] = self._calculate_moving_average(df, 50)
        df['MA200'] = self._calculate_moving_average(df, 200)
        df['VWMA100'] = self._calculate_vwma(df, 100)
        
        df = df.dropna()
        
        # 실제로 백테스팅에 사용할 데이터는 지정된 기간의 시작 시점 이후부터입니다.
        df_filtered = df[df.index >= start_time_dt]

        print(f"지표 계산 후 백테스팅 시작 캔들 수: {len(df_filtered)}개. (시작: {df_filtered.index.min()}, 종료: {df_filtered.index.max()})")
        
        return df_filtered

    def _get_execution_price_from_1m(self, current_candle_time, condition_type, ma50_prev, ma50_current):
        """
        신호가 발생한 5분봉 내부의 1분봉을 분석하여 실제 체결 가격을 추적합니다.
        """
        
        to_time = current_candle_time + datetime.timedelta(minutes=5)
        
        try:
            df_1m = pyupbit.get_ohlcv(self.ticker, interval='minute1', to=to_time, count=5)
        except Exception:
            print("⚠️ 1분봉 데이터 로드 실패. 5분봉 종가로 체결 가격 대체.")
            return 0 

        if df_1m is None or df_1m.empty:
            return 0
            
        df_1m = df_1m[df_1m.index >= current_candle_time]
        
        if condition_type == 'BUY':
            for i in range(1, len(df_1m)): 
                current_1m = df_1m.iloc[i]
                prev_1m = df_1m.iloc[i-1]
                
                if prev_1m['close'] <= ma50_prev and current_1m['close'] > ma50_current:
                    print(f"✅ 1분봉 정밀 추적: 매수 신호 포착. 체결가: {current_1m['close']:,.0f}")
                    return current_1m['close']
        
        elif condition_type == 'SELL':
            for i in range(1, len(df_1m)):
                current_1m = df_1m.iloc[i]
                prev_1m = df_1m.iloc[i-1]
                
                if prev_1m['close'] >= ma50_prev and current_1m['close'] < ma50_current:
                    print(f"✅ 1분봉 정밀 추적: 매도 신호 포착. 체결가: {current_1m['close']:,.0f}")
                    return current_1m['close']
            
        return df_1m.iloc[-1]['close'] if not df_1m.empty else 0


    def _execute_buy_simulation(self, current_price, candle_time):
        """가상 매수 실행 (수수료 적용)"""
        
        if self.ticker in self.holdings:
            return 
        
        trade_krw = self.current_balance 
        
        if trade_krw < MIN_TRADE_KRW:
            print(f"⚠️ 매수 실패: 가용 잔고 부족 ({self.current_balance:,.0f} KRW). 최소 거래 금액({MIN_TRADE_KRW:,.0f} KRW) 미만.")
            return

        buy_price = current_price
        
        buy_fee = trade_krw * FEE_RATE 
        krw_for_volume = trade_krw - buy_fee
        
        buy_volume = krw_for_volume / buy_price
        
        self.current_balance -= trade_krw
        
        self.holdings[self.ticker] = {
            'buy_price': buy_price,
            'buy_volume': buy_volume,
            'half_sold': False,
            'initial_krw': trade_krw 
        }
        self.buy_candle_time[self.ticker] = candle_time
        
        cumulative_return = (self.current_balance / self.initial_balance - 1) * 100
        
        self.transactions.append({
            '시간': candle_time,
            '구분': '매수',
            '가격': buy_price,
            '수량': buy_volume,
            '금액': trade_krw, 
            '사유': '전략 매수 조건 만족',
            '손익률': 0.0, 
            '누적수익률': cumulative_return
        })

    def _execute_sell_simulation(self, current_price, volume_to_sell, reason, candle_time):
        """가상 매도 실행 (수수료 적용)"""
        
        if self.ticker not in self.holdings:
            return
            
        holding = self.holdings[self.ticker]
        buy_price = holding['buy_price']
        
        realized_proceeds_gross = volume_to_sell * current_price
        
        sell_fee = realized_proceeds_gross * FEE_RATE
        realized_proceeds_net = realized_proceeds_gross - sell_fee 
        
        self.current_balance += realized_proceeds_net 

        profit_rate = ((current_price / buy_price) - 1) * 100
        
        if volume_to_sell == holding['buy_volume']:
            del self.holdings[self.ticker]
            if self.ticker in self.buy_candle_time:
                del self.buy_candle_time[self.ticker]
            
        elif volume_to_sell == holding['buy_volume'] / 2:
            holding['buy_volume'] -= volume_to_sell
            holding['half_sold'] = True
            
        cumulative_return = (self.current_balance / self.initial_balance - 1) * 100

        self.transactions.append({
            '시간': candle_time,
            '구분': '매도',
            '가격': current_price,
            '수량': volume_to_sell,
            '금액': realized_proceeds_net,
            '사유': reason,
            '손익률': profit_rate,
            '누적수익률': cumulative_return
        })
    
    def _strategy_5min_ma50_backtest(self, df):
        """
        5분봉 50선 트레이딩 전략 로직 (백테스팅 루프)
        """
        
        if len(df) < 250:
             print("경고: 필터링 후 캔들 수가 250개 미만이므로 전략 적용이 불안정할 수 있습니다.")
             return

        for i in range(len(df)): 
            
            if i < 1:
                continue
            
            current_df = df.iloc[:i+1]
            current_candle = current_df.iloc[-1]
            prev_candle = current_df.iloc[-2]
            
            candle_time = current_candle.name
            current_price = current_candle['close']
            
            ma50_current = current_candle['MA50']
            ma200_current = current_candle['MA200']
            
            prev_ma50 = prev_candle['MA50']
            prev_ma200 = prev_candle['MA200']
            
            is_ma50_below_10_candles = (current_df['close'].tail(10) < current_df['MA50'].tail(10)).all()
            
            
            # --- 1. 매수 로직 ---
            if self.ticker not in self.holdings:
                
                if i < 12:
                    continue
                    
                ma_trend_ok = (current_df['MA200'].tail(12) > current_df['VWMA100'].tail(12)).all() and \
                              (current_df['VWMA100'].tail(12) > current_df['MA50'].tail(12)).all()
                
                is_prev_breakout = (prev_candle['close'] > prev_ma50) and \
                                   (prev_candle['open'] <= prev_ma50)
                
                is_current_above_ma50 = (current_candle['open'] > ma50_current) and \
                                        (current_candle['close'] > ma50_current)
                
                is_breakout = is_prev_breakout and is_current_above_ma50
                
                is_near_ma200 = abs(prev_candle['close'] - prev_ma200) < (prev_candle['close'] * 0.005)
                
                if ma_trend_ok and is_breakout and (not is_near_ma200):
                    buy_price_precise = self._get_execution_price_from_1m(
                        candle_time, 'BUY', prev_ma50, ma50_current
                    )
                    if buy_price_precise > 0:
                        self._execute_buy_simulation(buy_price_precise, candle_time)
                
            
            # --- 2. 매도 로직 (보유 중일 때) ---
            elif self.ticker in self.holdings:
                
                holding = self.holdings[self.ticker]
                buy_price = holding['buy_price']
                is_half_sold = holding.get('half_sold', False)
                
                is_after_buy_candle = candle_time > self.buy_candle_time.get(self.ticker, pd.Timestamp('1970-01-01'))

                if not is_after_buy_candle:
                     continue
                
                # --- 2.1. 절반 매도 (익절 목표 달성: 200MA 도달) ---
                if not is_half_sold:
                    if current_candle['high'] >= ma200_current:
                        reason = '200MA 도달 (익절 목표 달성)'
                        if is_ma50_below_10_candles:
                             reason += ' (경고: 10개 캔들 50MA 아래이나 시뮬레이션 진행)'
                        
                        self._execute_sell_simulation(current_price, holding['buy_volume'] / 2, reason, candle_time)
                        continue
                        
                # --- 2.2. 나머지 절반 매도 (트레일링 익절/손절) ---
                
                is_trailing_sell_signal = (current_candle['close'] < ma50_current) and \
                                          (prev_candle['close'] >= prev_ma50)
                
                if is_half_sold:
                    profit_rate = ((current_price / buy_price) - 1) * 100
                    is_profitable = profit_rate >= 1.0

                    if is_trailing_sell_signal and is_profitable:
                        reason = f'50MA 하향 돌파 및 수익 1% 이상 ({profit_rate:+.2f}%)'
                        if is_ma50_below_10_candles:
                             reason += ' (경고: 10개 캔들 50MA 아래이나 시뮬레이션 진행)'
                        
                        sell_price_precise = self._get_execution_price_from_1m(
                             candle_time, 'SELL', prev_ma50, ma50_current
                        )
                        if sell_price_precise > 0:
                            self._execute_sell_simulation(sell_price_precise, holding['buy_volume'], reason, candle_time)
                        continue
                        
                    if i >= 2: 
                        is_below_ma50 = df.iloc[i-2:i+1].apply(lambda x: x['high'] < x['MA50'], axis=1).all()
                    else:
                        is_below_ma50 = False
                    
                    if not is_profitable and is_below_ma50:
                        reason = f'수익 1% 미만 ({profit_rate:+.2f}%) & 50MA 아래 3개 연속 캔들'
                        if is_ma50_below_10_candles:
                             reason += ' (경고: 10개 캔들 50MA 아래이나 시뮬레이션 진행)'
                        
                        self._execute_sell_simulation(current_price, holding['buy_volume'], reason, candle_time)
                        continue
                        
                # --- 2.3. 전량 매도 (손절: 매수 후 절반 매도 전) ---
                elif not is_half_sold:
                    
                    stop_loss_level = ma50_current * (1 - SIMULATION_STOP_LOSS_RATE)
                    is_stop_loss_signal_1 = current_candle['low'] < stop_loss_level
                    
                    is_stop_loss_signal_2 = (prev_candle['open'] < prev_ma50) and \
                                            (prev_candle['close'] < prev_ma50) and \
                                            (current_candle['close'] < current_candle['open'])
                    
                    is_stop_loss_signal = is_stop_loss_signal_1 or is_stop_loss_signal_2
                    
                    if is_stop_loss_signal:
                        profit_rate = ((current_price / buy_price) - 1) * 100
                        reason = f'손절: 50MA {SIMULATION_STOP_LOSS_RATE*100}% 하향 돌파 또는 두 캔들 연속 하향 추세. 수익률: {profit_rate:+.2f}%'
                        if is_ma50_below_10_candles:
                             reason += ' (경고: 10개 캔들 50MA 아래이나 시뮬레이션 진행)'
                             
                        self._execute_sell_simulation(current_price, holding['buy_volume'], reason, candle_time)
                        continue
                        
    def run_backtest(self):
        """백테스팅 실행 메인 함수"""
        df = self._load_data()
        
        if df.empty or len(df) < 200:
            print("백테스팅을 수행할 데이터가 부족합니다. (지표 계산 후 최소 200개 캔들 필요)")
            return None

        self._strategy_5min_ma50_backtest(df)
        
        # 잔여 포지션 강제 종료 (시뮬레이션 종료 시점)
        if self.ticker in self.holdings:
            print(f"\n시뮬레이션 종료 시점에 {self.ticker} 잔여 포지션 강제 청산...")
            final_price = df.iloc[-1]['close']
            holding = self.holdings[self.ticker]
            self._execute_sell_simulation(final_price, holding['buy_volume'], '시뮬레이션 종료 시점 강제 청산', df.index[-1])
        
        return self.transactions

# --- 로그 저장 함수 ---
def save_log(df_trans, ticker, period_label, parent_dir):
    """시뮬레이션 결과를 상위 폴더의 SIMULATION_LOG 폴더에 저장"""
    
    log_dir = os.path.join(parent_dir, '../SIMULATION_LOG')
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        print(f"\n📁 로그 폴더 생성: {log_dir}")
        
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f"SIMULATION_{ticker.replace('KRW-', '')}_{period_label}_{timestamp}.xlsx"
    file_path = os.path.join(log_dir, file_name)
    
    try:
        df_trans['손익률'] = df_trans['손익률'].map('{:,.2f}%'.format)
        df_trans['누적수익률'] = df_trans['누적수익률'].map('{:,.2f}%'.format)
        
        df_trans.to_excel(file_path, index=False)
        print(f"✅ 시뮬레이션 로그 저장 완료: {file_path}")
    except Exception as e:
        print(f"❌ 로그 저장 실패: {e}")

# --- 결과 출력 함수 ---

def analyze_results(transactions, ticker, period_label, initial_balance, final_balance, save_to_log=False, script_path="."):
    """트랜잭션 결과를 분석하고 출력"""
    
    if not transactions:
        print(f"\n--- [{ticker}] {period_label} 백테스팅 결과 ---")
        print("거래 내역이 없습니다 (매수 조건 불만족).")
        return

    df_trans = pd.DataFrame(transactions)
    df_sell = df_trans[df_trans['구분'].str.contains('매도')]
    
    total_trades = len(df_sell)
    
    df_profit = df_sell[df_sell['손익률'] >= 0]
    num_profit = len(df_profit)
    avg_profit_rate = df_profit['손익률'].mean() if num_profit > 0 else 0.0
    
    df_loss = df_sell[df_sell['손익률'] < 0]
    num_loss = len(df_loss)
    avg_loss_rate = df_loss['손익률'].mean() if num_loss > 0 else 0.0
    
    final_cumulative_return = df_trans['누적수익률'].iloc[-1] if not df_trans.empty else 0.0
    
    profit_reasons = df_profit['사유'].value_counts()
    loss_reasons = df_loss['사유'].value_counts()
    
    # 출력
    print(f"\n\n=======================================================")
    print(f"📊 [{ticker}] {period_label} 5분봉 50선 트레이딩 전략 백테스팅 결과")
    print(f"=======================================================")
    print(f"⭐ 총 거래 횟수: {total_trades}회")
    print(f"-------------------------------------------------------")
    
    print(f"💰 익절 횟수 (손익률 >= 0%): {num_profit}회")
    print(f"📉 손절 횟수 (손익률 < 0%): {num_loss}회")
    print(f"✅ 승률: {num_profit / total_trades * 100:.2f}%" if total_trades > 0 else "✅ 승률: 0.00%")

    print(f"-------------------------------------------------------")
    print(f"📈 평균 익절률: {avg_profit_rate:+.2f}%")
    print(f"💔 평균 손절률: {avg_loss_rate:+.2f}%")
    print(f"-------------------------------------------------------")
    print(f"🚀 **최종 누적 수익률**: {final_cumulative_return:+.2f}% (초기자본: {initial_balance:,.0f} KRW)")
    print(f"💰 **최종 자본금**: {final_balance:,.0f} KRW") 
    print(f"=======================================================")
    
    print("\n### 📝 익절 사유 상세 (사유별 횟수)")
    if not profit_reasons.empty:
        for reason, count in profit_reasons.items():
            print(f"- {reason}: {count}회")
    else:
        print("- 익절 거래가 없습니다.")

    print("\n### 💔 손절/약익절 사유 상세 (사유별 횟수)")
    if not loss_reasons.empty:
        for reason, count in loss_reasons.items():
            print(f"- {reason}: {count}회")
    else:
        print("- 손절 거래가 없습니다.")

    print("\n### 📜 전체 거래 내역 (최대 30개)")
    print(df_trans.tail(30).to_string())

    if save_to_log:
        parent_dir = os.path.dirname(os.path.abspath(script_path))
        save_log(df_trans, ticker, period_label, parent_dir)


# --- 사용자 입력 및 실행 ---

if __name__ == "__main__":
    
    print("Upbit 5분봉 50선 트레이딩 전략 백테스팅 시뮬레이터")
    print("💡 정밀도 개선: 5분봉 지표 기반, 1분봉 데이터로 체결 시점/가격 추적")
    print(f"**초기 자본: {SIMULATION_INITIAL_BALANCE:,.0f} KRW**")
    print(f"**수수료율 (매수/매도 각각): {FEE_RATE * 100}% 적용**")
    print("--------------------------------------------------")
    
    TICKER = input("테스트할 종목명(예: KRW-BTC): ").upper()
    if TICKER not in pyupbit.get_tickers(fiat="KRW"):
        print("오류: 유효한 KRW 마켓 종목명을 입력하세요.")
        exit()

    PERIODS = ['1일', '1주일', '1개월', '3개월', '6개월', '1년']
    print(f"사용 가능한 기간: {', '.join(PERIODS)}")
    
    while True:
        # 공백 제거 (.strip() 적용)
        PERIOD_LABEL = input("테스트할 기간을 입력하세요 (예: 1개월): ").strip() 
        if PERIOD_LABEL in PERIODS:
            break
        print("오류: 유효한 기간을 입력하세요.")
    
    SAVE_LOG = input("시뮬레이션 결과를 로그로 저장하시겠습니까? (y/n): ").lower() == 'y'
    
    try:
        script_path = os.path.abspath(__file__)
    except NameError:
        script_path = os.path.abspath(sys.argv[0]) if sys.argv else "."
    
    backtester = Backtester(TICKER, PERIOD_LABEL)
    results = backtester.run_backtest()
    
    if results is not None:
        analyze_results(
            results, 
            TICKER, 
            PERIOD_LABEL, 
            SIMULATION_INITIAL_BALANCE,
            final_balance=backtester.current_balance,
            save_to_log=SAVE_LOG,
            script_path=script_path
        )