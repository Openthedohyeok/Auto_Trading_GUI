import tkinter as tk
from tkinter import ttk, messagebox, simpledialog 
import os
from dotenv import load_dotenv
import pyupbit
import time
import threading
import datetime 
import pandas as pd
import numpy as np 
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.ticker import FuncFormatter 

# 버전 관리 변수 설정
APP_VERSION = "v0d.01.0b" 
LOG_DIR = "../TRADING_LOG" 

# 전역 디버깅/개발 설정
DEBUG_MODE_CANDLE = False 

class AutoTradingGUI:
    """Upbit 자동 트레이딩 GUI 클래스"""

    def __init__(self, master):
        self.master = master
        master.title(f"Auto Trading ({APP_VERSION})")
        master.geometry("2000x900") 
        
        load_dotenv()
        self.access_key = os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = os.getenv("UPBIT_SECRET_KEY")
        
        self.upbit = None
        if self.access_key and self.secret_key:
            try:
                # Upbit API 키를 사용하여 pyupbit 객체 초기화
                self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
                print("Upbit API 키 로드 성공")
            except Exception as e:
                messagebox.showerror("API 오류", f"Upbit 객체 생성 오류: {e}")
        else:
            messagebox.showwarning("API 경고", ".env 파일에서 API 키를 불러올 수 없습니다.")

        self.min_trade_volume = 0 
        self.holdings = {} # 현재 보유 중인 종목 기록 (가상 또는 실제)
        self.target_ticker = "N/A" # 현재 트레이딩 대상 종목
        
        self._create_frames()
        self._create_widgets()
        self._layout_widgets()
        self._setup_chart() 

        self.trading_active = False
        self.status_text.set("시작 대기 중")
        self.trading_thread = None 
        self.log_save_thread = None
        
        self._log_no_source(f"Auto Trading ({APP_VERSION})")
        self._log_no_source(f"디버그 모드 (캔들 로깅): {'활성화' if DEBUG_MODE_CANDLE else '비활성화'}")


    def _create_frames(self):
        """GUI 레이아웃을 위한 프레임 생성 (좌측과 우측 분리)"""
        style = ttk.Style()
        style.configure('TFrame', padding=10, relief='flat', font=('Malgun Gothic', 10))
        style.configure('TLabel', font=('Malgun Gothic', 10))
        style.configure('TCheckbutton', font=('Malgun Gothic', 10))
        style.configure('TButton', font=('Malgun Gothic', 10))
        style.configure('TCombobox', font=('Malgun Gothic', 10))
        style.configure('TEntry', font=('Malgun Gothic', 10))
        
        self.main_frame = ttk.Frame(self.master)
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.left_panel = ttk.Frame(self.main_frame)
        self.right_panel = ttk.Frame(self.main_frame)
        
        self.left_panel.pack(side='left', fill='both', padx=(0, 10))
        self.right_panel.pack(side='left', fill='both', expand=True)

        self.status_frame = ttk.LabelFrame(self.left_panel, text="1. 현재 상태", padding="10")
        self.options_frame = ttk.LabelFrame(self.left_panel, text="2. 트레이딩 옵션", padding="10")
        self.settings_frame = ttk.LabelFrame(self.left_panel, text="3. 전략 상세 설정", padding="10")
        self.etc_frame = ttk.LabelFrame(self.left_panel, text="4. 기타 설정", padding="10")
        self.button_frame = ttk.Frame(self.left_panel)
        
        # 5. 실시간 로그 프레임
        self.log_frame = ttk.LabelFrame(self.left_panel, text="5. 실시간 로그", padding="10")
        
        # 6. 차트 프레임
        self.chart_frame = ttk.LabelFrame(self.right_panel, text="6. 차트", padding="5")


    def _create_widgets(self):
        """GUI 위젯 생성 (프레임에 소속 지정)"""
        
        # 1. 현재 상태 ------------------------------------------
        self.status_text = tk.StringVar()
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_text, 
                                      font=("Malgun Gothic", 12, "bold"), foreground="blue")
        
        self.balance_text = tk.StringVar(value="잔고 정보 (KRW)")
        self.check_balance_button = ttk.Button(self.status_frame, text="현재 잔고 보기", command=self._check_balance)
        self.balance_label = ttk.Label(self.status_frame, textvariable=self.balance_text, 
                                      font=("Malgun Gothic", 10), foreground="green")

        # 2. 트레이딩 옵션 ------------------------------------------
        self.mode_var = tk.StringVar(value='SIMULATION')
        self.mode_label = ttk.Label(self.options_frame, text="모드 선택:")
        self.mode_options = ['SIMULATION', 'TRADING', 'DEVELOPMENT'] 
        self.mode_menu = ttk.Combobox(self.options_frame, textvariable=self.mode_var, values=self.mode_options, state='readonly')
        
        self.strategy_var = tk.StringVar(value='이동평균매매')
        self.strategy_label = ttk.Label(self.options_frame, text="전략 선택:")
        # 전략 옵션
        self.strategy_options = ['이동평균매매', '5분봉_50선_트레이딩']
        self.strategy_menu = ttk.Combobox(self.options_frame, textvariable=self.strategy_var, values=self.strategy_options, state='readonly')
        self.strategy_menu.bind("<<ComboboxSelected>>", self._toggle_ma_options)
        
        self.trade_ratio_var = tk.StringVar(value='100')
        self.trade_ratio_label = ttk.Label(self.options_frame, text="트레이딩 금액 (%):")
        self.trade_ratio_options = [str(i) for i in range(0, 101, 5)]
        self.trade_ratio_menu = ttk.Combobox(self.options_frame, textvariable=self.trade_ratio_var, 
                                             values=self.trade_ratio_options, state='readonly')

        self.ma_timeframe_var = tk.StringVar(value='1분')
        self.ma_timeframe_label = ttk.Label(self.options_frame, text="시간봉:") 
        self.ma_timeframe_options = ['1분', '3분', '5분', '10분', '15분', '30분', '1시간', '4시간', '1일', '1주']
        self.ma_timeframe_menu = ttk.Combobox(self.options_frame, textvariable=self.ma_timeframe_var, 
                                              values=self.ma_timeframe_options, state='readonly')
        
        # 3. 전략 상세 설정 ------------------------------------------
        self.data_load_time_var = tk.StringVar(value='10') 
        self.data_load_time_label = ttk.Label(self.settings_frame, text="데이터 로딩 시간 (초):")
        self.data_load_time_entry = ttk.Entry(self.settings_frame, textvariable=self.data_load_time_var, font=('Malgun Gothic', 10))
        
        self.ticker_input_var = tk.StringVar(value='KRW-BTC, KRW-ETH') 
        self.ticker_input_label = ttk.Label(self.settings_frame, text="매매 희망 종목 (쉼표 구분):")
        self.ticker_input_entry = ttk.Entry(self.settings_frame, textvariable=self.ticker_input_var, font=('Malgun Gothic', 10))
        
        self.auto_select_var = tk.BooleanVar(value=False)
        self.auto_select_check = ttk.Checkbutton(self.settings_frame, text="종목 자동 선택", 
                                                variable=self.auto_select_var, command=self._toggle_ticker_input)
        
        # 4. 기타 설정 ------------------------------------------
        self.log_save_time_var = tk.StringVar(value='24') 
        self.log_save_time_label = ttk.Label(self.etc_frame, text="로그 저장 주기 (시간):")
        self.log_save_time_entry = ttk.Entry(self.etc_frame, textvariable=self.log_save_time_var, font=('Malgun Gothic', 10))
        
        self.start_button = ttk.Button(self.button_frame, text="트레이딩 시작", command=self._handle_start)
        self.stop_button = ttk.Button(self.button_frame, text="트레이딩 종료", command=self._stop_trading, state='disabled')
        
        # 5. 실시간 로그 ------------------------------------------
        self.log_text = tk.Text(self.log_frame, state='disabled', wrap='word', 
                                font=("Malgun Gothic", 9), height=10, 
                                bg='#2b2b2b', fg='white', insertbackground='white')
        self.log_scrollbar = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=self.log_scrollbar.set)

    def _layout_widgets(self):
        """GUI 위젯 배치"""
        
        # Left Panel (종속 프레임 순서대로 pack)
        self.status_frame.pack(padx=5, pady=5, fill="x")
        self.options_frame.pack(padx=5, pady=5, fill="x")
        self.settings_frame.pack(padx=5, pady=5, fill="x")
        self.etc_frame.pack(padx=5, pady=5, fill="x")
        self.log_frame.pack(padx=5, pady=5, fill="both", expand=True) 
        self.button_frame.pack(padx=5, pady=10, fill="x")

        # Right Panel (6. 차트)
        self.right_panel.rowconfigure(0, weight=1)
        self.right_panel.columnconfigure(0, weight=1)
        self.chart_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew") 

        # 1. 현재 상태 (pack) 
        self.status_label.pack(fill="x", pady=(5, 0)) 
        self.check_balance_button.pack(fill="x", pady=5)
        self.balance_label.pack(fill="x", pady=(0, 5))
        
        # 2. 트레이딩 옵션 (grid)
        self.options_frame.columnconfigure(1, weight=1)
        self.mode_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.mode_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.strategy_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.strategy_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        self.trade_ratio_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.trade_ratio_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        self.ma_timeframe_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.ma_timeframe_menu.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # 3. 전략 상세 설정 (grid)
        self.settings_frame.columnconfigure(1, weight=1)
        self.data_load_time_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.data_load_time_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.ticker_input_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.ticker_input_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.auto_select_check.grid(row=2, column=1, padx=5, pady=5, sticky="e")
        
        # 4. 기타 설정 (grid)
        self.etc_frame.columnconfigure(1, weight=1)
        self.log_save_time_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.log_save_time_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # 시작/종료 버튼 (pack)
        self.start_button.pack(side=tk.LEFT, expand=True, fill="x", padx=5)
        self.stop_button.pack(side=tk.RIGHT, expand=True, fill="x", padx=5)
        
        # 5. 실시간 로그 (grid, 좌측 log_frame 내부)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        self.log_scrollbar.grid(row=0, column=1, sticky='ns')

    def _setup_chart(self):
        """Matplotlib Figure를 생성하고 Tkinter에 임베딩"""
        self.fig = Figure(figsize=(12, 4), dpi=100, facecolor='#0d1117')
        self.ax = self.fig.add_subplot(111)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame)
        self.toolbar.update()
        
        self.ax.set_title("")
        self.ax.set_xlabel("")
        self.ax.set_ylabel("")
        
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        
        self.ax.set_facecolor('#161b22') # 플롯 영역 배경색
        
        self.fig.tight_layout()
        self.canvas.draw()
        
    def _draw_chart(self, df, timeframe_label):
        """캔들 가격과 이평선 추세를 시각화 (캔들스틱 차트)"""
        
        self.ax.clear()
        
        # 최근 200개 데이터만 추출 
        plot_df = df.tail(200).copy()
        x_index = np.arange(len(plot_df))
        
        # 1. 캔들 색상 및 높이 계산
        up = plot_df['close'] >= plot_df['open']
        col = np.where(up, '#27A199', '#E74C3C') 
        
        # 캔들 몸통 높이: |종가 - 시가|
        bar_height = abs(plot_df['close'] - plot_df['open'])
        # 캔들 몸통 시작점: min(종가, 시가)
        bar_bottom = np.minimum(plot_df['open'], plot_df['close'])

        # 2. 캔들 꼬리 (Wicks: High and Low) 그리기
        self.ax.vlines(x_index, plot_df['low'], plot_df['high'], 
                       color=col, linewidth=1, alpha=0.7)

        # 3. 캔들 몸통 (Bodies: Open and Close) 그리기
        self.ax.bar(x_index, bar_height, bottom=bar_bottom, 
                    color=col, linewidth=0, width=0.8, align='center')
        
        # 4. 이동평균선 (MA/VWMA) 그리기 
        self.ax.plot(x_index, plot_df['MA50'], label='50-MA', color='#00ff00', 
                     linestyle='-', linewidth=1.5, alpha=0.7)
        self.ax.plot(x_index, plot_df['MA200'], label='200-MA', color='#0000ff', 
                     linestyle='-', linewidth=1.5, alpha=0.7)
        self.ax.plot(x_index, plot_df['VWMA100'], label='100-VWMA', color='#ffffff', 
                     linestyle='-', linewidth=1.5, alpha=0.7) 
        
        # 5. 매수 평단 가격 표시 (추가된 부분)
        if self.target_ticker in self.holdings and 'buy_price' in self.holdings[self.target_ticker]:
            buy_price = self.holdings[self.target_ticker]['buy_price']
            # 최근 200개 데이터에 해당 평단 가격이 표시될 수 있도록 확인 (단순 시각화 목적)
            if plot_df['low'].min() <= buy_price <= plot_df['high'].max():
                 self.ax.axhline(buy_price, color='#FFFF00', linestyle='--', linewidth=1, label=f'Buy @ {buy_price:,.0f}') 
        
        # 6. 차트 제목 및 레이블 설정
        self.ax.set_title(f"{self.target_ticker}", fontsize=12, color='white')
        self.ax.set_xlabel("Timeframe (Candle Index)", fontsize=10, color='white') 
        self.ax.set_ylabel("KRW", fontsize=10, color='white') 
        
        self.ax.tick_params(axis='both', which='major', labelsize=8)
        self.ax.legend(loc='best', fontsize=8, framealpha=0.8, facecolor='#161b22', edgecolor='white', labelcolor='linecolor') 
        
        self.ax.grid(True, linestyle=':', alpha=0.3, color='#444444') 
        
        # y축 포맷을 정수(콤마 표시)로 설정
        formatter = FuncFormatter(lambda x, pos: f'{x:,.0f}')
        self.ax.yaxis.set_major_formatter(formatter)
        
        # X축 눈금을 20개 간격으로 표시
        if len(x_index) > 0:
            step = max(1, len(x_index) // 10)
            self.ax.set_xticks(x_index[::step])
            self.ax.set_xticklabels(x_index[::step], rotation=45, ha='right')
        
        # Dark mode 색상 설정
        self.ax.set_facecolor('#161b22') 
        self.fig.set_facecolor('#0d1117') 
        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')

        self.fig.tight_layout()
        self.canvas.draw()
        
    def _toggle_ticker_input(self):
        """종목 자동 선택 체크박스 상태에 따라 매매 희망 종목 입력 칸 활성화/비활성화"""
        if self.auto_select_var.get():
            self.ticker_input_entry.config(state='disabled')
            self.ticker_input_label.config(state='disabled')
        else:
            self.ticker_input_entry.config(state='normal')
            self.ticker_input_label.config(state='normal')

    def _toggle_ma_options(self, event):
        """전략 선택에 따라 이동평균매매 옵션 활성화/비활성화 및 5분봉 고정"""
        if self.strategy_var.get() == '이동평균매매':
            self.ma_timeframe_label.config(state='normal')
            self.ma_timeframe_menu.config(state='readonly')
        elif self.strategy_var.get() == '5분봉_50선_트레이딩':
            self.ma_timeframe_var.set('5분')
            self.ma_timeframe_label.config(state='normal')
            self.ma_timeframe_menu.config(state='disabled')
        else:
            self.ma_timeframe_label.config(state='disabled')
            self.ma_timeframe_menu.config(state='disabled')
            
    def _check_balance(self):
        """현재 KRW 잔고를 조회하여 GUI에 표시"""
        
        def fetch_balance():
            if not self.upbit:
                self.master.after(0, lambda: self.balance_text.set("API 키 로드 실패"))
                return
            
            self.master.after(0, lambda: self.check_balance_button.config(state='disabled'))
            self.master.after(0, lambda: self.balance_text.set("잔고 조회 중..."))
            self.master.update()
            
            try:
                # Upbit API를 통해 KRW 잔고 조회
                balance = self.upbit.get_balance("KRW") 
                
                if balance is not None:
                    display_text = f"현재 잔고: {balance:,.0f} KRW"
                    self._log(f"잔고 조회 성공: {balance:,.0f} KRW")
                    
                    self.master.after(0, lambda: self.balance_text.set(display_text))
                else:
                    self.master.after(0, lambda: self.balance_text.set("잔고 조회 실패 (응답 없음)"))
                    self._log("잔고 조회 실패 (응답 없음). API 키 또는 권한 확인 필요.")
                    
            except Exception as e:
                error_msg = f"잔고 조회 중 오류 발생: {type(e).__name__}"
                self._log(error_msg)
                self.master.after(0, lambda: self.balance_text.set(f"오류: {type(e).__name__}"))

            self.master.after(0, lambda: self.check_balance_button.config(state='normal'))

        threading.Thread(target=fetch_balance, daemon=True).start()

    def _log_no_source(self, message):
        """실시간 로그를 Text 위젯에 추가 (소스 태그 없음)"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        print(log_entry.strip())
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END) 
        self.log_text.config(state='disabled')

    def _log(self, message):
        """실시간 로그를 Text 위젯에 추가"""
        self._log_no_source(message)

    def _save_log_to_file(self, prefix="TRADING_"): 
        """현재까지의 로그 내용을 파일로 저장 (엑셀 형식)"""
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(LOG_DIR, f"{prefix}LOG_{timestamp}.xlsx")
            
            log_content = self.log_text.get("1.0", tk.END).strip().split('\n')
            
            data = []
            for line in log_content:
                if line.startswith('['):
                    try:
                        time_str = line[1:20] 
                        message = line[22:].strip()
                        data.append({'시간': time_str, '로그 메시지': message})
                    except Exception:
                        data.append({'시간': '', '로그 메시지': line})
            
            if not data:
                self._log("저장할 로그 내용이 없습니다.")
                return

            df = pd.DataFrame(data)
            
            df.to_excel(filename, index=False, engine='openpyxl')
            
            self._log(f"로그가 성공적으로 엑셀 파일로 저장되었습니다: {filename}")
        except Exception as e:
            self._log(f"로그 파일 저장 중 오류 발생 (엑셀 저장): {e}")


    def _handle_start(self):
        """트레이딩 시작 버튼 클릭 핸들러"""
        
        if self.trading_active:
            return

        tickers = [t.strip() for t in self.ticker_input_var.get().upper().split(',') if t.strip()]
        auto_select = self.auto_select_var.get()
        
        if auto_select and self.mode_var.get() != 'DEVELOPMENT':
            dialog_title = "최소 거래 대금 설정"
            
            dialog_prompt = "최소 거래 대금을 입력 후 확인 버튼을 누르세요 (단위: 만원, 예: 100 (100만원))"
            
            initial_value = str(self.min_trade_volume // 10000)
            
            min_volume_manwon_str = simpledialog.askstring(dialog_title, dialog_prompt, 
                                                            parent=self.master, initialvalue=initial_value)
            
            if min_volume_manwon_str is None:
                self._log("최소 거래 대금 입력이 취소되었습니다. 트레이딩을 시작할 수 없습니다.")
                return

            try:
                min_volume_manwon = int(min_volume_manwon_str)
                if min_volume_manwon < 0:
                    raise ValueError
                
                self.min_trade_volume = min_volume_manwon * 10000
                
                self._log(f"최소 거래 대금: {min_volume_manwon:,.0f} 만원 ({self.min_trade_volume:,.0f} 원)으로 설정되었습니다.")
            except ValueError:
                messagebox.showerror("입력 오류", "최소 거래 대금은 0 이상의 정수(만원 단위)로 입력해야 합니다.")
                self._log("최소 거래 대금 입력 오류.")
                return
        
        elif not tickers and not auto_select:
             messagebox.showwarning("종목 설정 오류", "매매 희망 종목을 입력하거나 '종목 자동 선택'을 활성화해야 합니다.")
             return
             
        self._start_trading()

    def _start_trading(self):
        """실제 트레이딩 로직 시작"""
        
        try:
            load_time = int(self.data_load_time_var.get())
            log_save_time_hours = int(self.log_save_time_var.get())
            trade_ratio = int(self.trade_ratio_var.get())
            
            if load_time <= 0 or log_save_time_hours <= 0 or not (0 <= trade_ratio <= 100):
                raise ValueError
        except ValueError:
            messagebox.showerror("입력 오류", "설정값(로딩 시간, 로그 주기, 트레이딩 금액)을 확인해 주세요.")
            return

        self.trading_active = True
        
        mode = self.mode_var.get()
        if mode == 'DEVELOPMENT':
            self.status_text.set("개발 모드 시작됨 (데이터 로깅 중...)")
        else:
            self.status_text.set("트레이딩 시작됨 (종목 탐색 중...)")

        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        self.holdings = {}

        strategy = self.strategy_var.get()
        timeframe_label = self.ma_timeframe_var.get()
        timeframe_map = {'1분': 'minute1', '3분': 'minute3', '5분': 'minute5', '10분': 'minute10', '15분': 'minute15', 
                         '30분': 'minute30', '1시간': 'hour1', '4시간': 'hour4', '1일': 'day', '1주': 'week'}
        
        # 5분봉_50선_트레이딩 전략은 5분봉으로 강제
        if strategy == '5분봉_50선_트레이딩':
            timeframe = 'minute5'
            timeframe_label = '5분'
        else:
            timeframe = timeframe_map.get(timeframe_label, 'minute1')

        tickers = [t.strip() for t in self.ticker_input_var.get().upper().split(',') if t.strip()]
        auto_select = self.auto_select_var.get()
        
        self._log("--- 트레이딩 시작 설정 ---")
        self._log(f"모드: {mode}")
        self._log(f"전략: {strategy} (시간봉: {timeframe_label})") 
        self._log(f"트레이딩 금액: {trade_ratio}%") 
        self._log(f"데이터 로딩 시간: {load_time}초")
        self._log(f"종목 자동 선택: {auto_select}")
        if auto_select and mode != 'DEVELOPMENT':
             self._log(f"  ㄴ 최소 거래 대금: {self.min_trade_volume:,.0f} 원")
             self._log(f"  ㄴ 대상 종목: {'전체 KRW 종목' if not tickers else str(tickers)}")
        else:
             self._log(f"매매 희망 종목: {tickers}")
        self._log(f"로그 저장 주기: {log_save_time_hours} 시간")
        self._log("--------------------------")

        self.trading_thread = threading.Thread(target=self._run_trading_loop, 
                                               args=(load_time, strategy, timeframe, tickers, auto_select, mode))
        self.trading_thread.daemon = True 
        self.trading_thread.start()
        
        self.log_save_thread = threading.Thread(target=self._run_log_save_loop, 
                                                args=(log_save_time_hours,))
        self.log_save_thread.daemon = True
        self.log_save_thread.start()

    def _run_log_save_loop(self, save_interval_hours):
        """설정된 시간마다 로그를 파일로 저장하는 루프"""
        
        save_interval_seconds = save_interval_hours * 3600
        self._log(f"로그 자동 저장 루프 시작. 주기: {save_interval_hours} 시간 ({save_interval_seconds}초)")
        
        while self.trading_active:
            try:
                for _ in range(save_interval_seconds):
                    if not self.trading_active:
                        break
                    time.sleep(1)
                
                if self.trading_active:
                    self.master.after(0, lambda: self._save_log_to_file("AUTO_SAVE")) 
            
            except Exception as e:
                self._log(f"로그 자동 저장 중 치명적인 오류 발생: {e}")
                time.sleep(60) 

        self._log("로그 자동 저장 루프 종료.")

    def _calculate_moving_average(self, df, window):
        """이동평균(Moving Average) 계산 - 전체 캔들 기간에 대한 Series 반환"""
        return df['close'].rolling(window=window, min_periods=window).mean()

    def _calculate_vwma(self, df, window):
        """거래량 가중 이동평균(VWMA) 계산"""
        pv_sum = (df['close'] * df['volume']).rolling(window=window, min_periods=window).sum()
        v_sum = df['volume'].rolling(window=window, min_periods=window).sum()
        return pv_sum / v_sum

    def _execute_buy(self, ticker, current_price):
        """TRADING 모드에서 실제 시장가 매수 주문 실행"""
        if not self.upbit:
            self._log("매수 실패: Upbit 객체 초기화 실패. API 키를 확인해 주세요.")
            return

        try:
            trade_ratio = int(self.trade_ratio_var.get()) / 100.0
            
            # 잔고 조회
            krw_balance = self.upbit.get_balance("KRW") 
            if krw_balance is None:
                self._log("매수 실패: KRW 잔고 조회 실패.")
                return
            
            # 주문 금액 계산 및 최소 주문 금액(5,000 KRW) 체크
            order_amount = krw_balance * trade_ratio
            MIN_ORDER_KRW = 5000
            
            if order_amount >= MIN_ORDER_KRW:
                self._log(f"매수 신호({ticker}). 시장가 매수 주문 시도 (금액: {order_amount:,.0f} KRW, 비율: {trade_ratio*100:.0f}%)")
                
                # 실제 매수 주문 API 호출
                result = self.upbit.buy_market_order(ticker, order_amount)
                
                if result is None or 'error' in result:
                    err_msg = result.get('error', {}).get('message', '알 수 없는 오류') if result else '응답 없음'
                    self._log(f"매수 실패: {err_msg}")
                else:
                    self._log(f"매수 주문 성공 (UUID: {result.get('uuid', 'N/A')}).")
                    # 주문 성공 시 holdings에 기록 (정확한 체결가/수량 확인을 위한 로직 추가 필요)
                    self.holdings[ticker] = {'buy_price': current_price, 'buy_volume': 0.0, 'half_sold': False}
                    
            else:
                self._log(f"매수 금액 ({order_amount:,.0f} KRW)이 최소 주문 금액({MIN_ORDER_KRW:,.0f} KRW) 미만입니다. 주문 생략.")
                
        except Exception as e:
            self._log(f"매수 주문 중 예외 발생: {type(e).__name__} - {e}")

    def _execute_sell(self, ticker, is_half_sell=False):
        """TRADING 모드에서 실제 시장가 매도 주문 실행 (전량 또는 절반)"""
        if not self.upbit:
            self._log("매도 실패: Upbit 객체 초기화 실패. API 키를 확인해 주세요.")
            return
            
        try:
            coin_symbol = ticker.split('-')[1]
            holdings = self.upbit.get_balances() 
            target_coin_balance = [bal for bal in holdings if bal['currency'] == coin_symbol]
            
            if target_coin_balance:
                # Upbit API는 소수점 8자리까지의 정밀도를 요구하므로 float 사용
                total_volume = float(target_coin_balance[0]['balance'])
                
                volume_to_sell = total_volume * 0.5 if is_half_sell else total_volume
                
                if volume_to_sell > 0:
                    self._log(f"매도 신호({ticker}). 시장가 매도 주문 시도 (수량: {volume_to_sell}, {'절반' if is_half_sell else '전량'})")
                    
                    # 실제 매도 주문 API 호출
                    sell_result = self.upbit.sell_market_order(ticker, volume_to_sell)
                    
                    if sell_result is None or 'error' in sell_result:
                        err_msg = sell_result.get('error', {}).get('message', '알 수 없는 오류') if sell_result else '응답 없음'
                        self._log(f"매도 실패: {err_msg}")
                    else:
                        self._log(f"매도 주문 성공 (UUID: {sell_result.get('uuid', 'N/A')}).")
                        
                        if is_half_sell:
                            if ticker in self.holdings:
                                self.holdings[ticker]['half_sold'] = True
                        else:
                            # 보유 기록 삭제 (전량 매도 완료)
                            if ticker in self.holdings:
                                del self.holdings[ticker]
                else:
                    self._log(f"매도 실패: 매도할 수량({coin_symbol})이 0입니다.")
            else:
                self._log(f"매도 실패: 보유 잔고 목록에서 {coin_symbol}을(를) 찾을 수 없습니다.")
                
        except Exception as e:
            self._log(f"매도 주문 중 예외 발생: {type(e).__name__} - {e}")

    def _strategy_5min_ma50(self, ticker, df, mode):
        """5분봉 50선 트레이딩 전략 로직"""
        
        raw_action = "Wait"
        current_price = df.iloc[-1]['close']
        
        # 캔들 데이터가 200개 미만이면 판단 불가
        if len(df) < 200:
            return "Wait", current_price
            
        # 캔들 데이터가 2개 미만이거나 MA50, MA200, VWMA100 값이 NaN이면 판단 불가
        if len(df) < 2 or df['MA50'].iloc[-1] is np.nan or df['MA200'].iloc[-1] is np.nan or df['VWMA100'].iloc[-1] is np.nan:
            return "Wait", current_price

        # 현재와 직전 캔들 데이터
        current_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        # 현재와 직전 지표 값
        ma50_current = current_candle['MA50']
        ma200_current = current_candle['MA200']
        vwma100_current = current_candle['VWMA100']
        
        prev_ma50 = prev_candle['MA50']
        prev_ma200 = prev_candle['MA200']
        prev_vwma100 = prev_candle['VWMA100']

        # ------------------------------------------------
        # 1. 매수 조건 (Buy)
        # ------------------------------------------------
        if ticker not in self.holdings:
            # 1-1. 이평선 정배열 (최근 50개 캔들)
            # 모든 50개 캔들에 대해 200 > 100 > 50 이평선이 유지되어야 함
            ma_trend_ok = (df['MA200'].tail(50) > df['VWMA100'].tail(50)).all() and \
                          (df['VWMA100'].tail(50) > df['MA50'].tail(50)).all()
            
            # 1-2. 50MA 돌파 (직전 캔들이 50MA를 상향 돌파했고, 현재 캔들이 50MA보다 위에 있는 경우)
            is_prev_breakout = (prev_candle['close'] > prev_ma50) and \
                               (prev_candle['open'] <= prev_ma50)
            
            is_current_above_ma50 = (current_candle['open'] > ma50_current) and \
                                    (current_candle['close'] > ma50_current)
            
            is_breakout = is_prev_breakout and is_current_above_ma50

            if ma_trend_ok and is_breakout:
                raw_action = "Buy"
                self._log(f"매수 조건 만족: 정배열({ma_trend_ok}), 50MA 상향 돌파({is_breakout})")
                
                if mode == 'TRADING':
                    self._execute_buy(ticker, current_price) # 실제 매수 주문 실행
                    # 실제 주문 체결을 기다려야 하지만, 여기서는 즉시 holdings에 기록
                    # 정확한 체결 정보를 받기 전까지는 임시 기록
                    self.holdings[ticker] = {'buy_price': current_price, 'buy_volume': 0.0, 'half_sold': False}
                elif mode == 'SIMULATION':
                     # SIMULATION 모드에서만 가상 매수 기록
                     self.holdings[ticker] = {'buy_price': current_price, 'buy_volume': 0.0, 'half_sold': False}
            else:
                # 매수 대기 중 로그 추가
                if not ma_trend_ok:
                    self._log(f"매수 대기: 정배열 조건 미달 (MA200 > VWMA100 > MA50 불만족)")
                elif not is_breakout:
                    self._log(f"매수 대기: 50MA 상향 돌파 조건 미달 (직전캔들 돌파: {is_prev_breakout}, 현재캔들 위: {is_current_above_ma50})")

        # ------------------------------------------------
        # 2. 매도/손절 조건 (Sell/Hold)
        # ------------------------------------------------
        elif ticker in self.holdings:
            raw_action = "Hold" # 일단 보유 상태로 설정
            buy_price = self.holdings[ticker]['buy_price']
            is_half_sold = self.holdings[ticker].get('half_sold', False)
            
            # 2-1. 절반 매도 (200MA에 캔들이 닿으면) - 절반 매도 플래그가 False일 때만
            if not is_half_sold:
                # 캔들의 고가(High)가 200MA보다 같거나 높을 경우
                if current_candle['high'] >= ma200_current:
                    self.holdings[ticker]['half_sold'] = True # 플래그만 변경하고 실제 매도는 다음 루프에서 처리
                    
                    if mode == 'TRADING':
                         self._execute_sell(ticker, is_half_sell=True)
                    else: # SIMULATION 모드에서 절반 매도 처리
                        raw_action = "Sell (Half)" 
                        self._log(f"가상 절반 매도 (이익 실현): 200MA({ma200_current:,.0f}) 도달. 현재가격:{current_price:,.0f}원")
                    
                    # 매도 처리 후 다음 로직 건너뛰기
                    return "Hold", current_price
            
            # 2-2. 나머지 절반 매도 (50MA 하향 돌파 + 1% 이상 수익) - 절반 매도 플래그가 True일 때
            if is_half_sold:
                profit_rate = ((current_price / buy_price) - 1) * 100
                
                # 50MA 하향 돌파 (현재 종가 < 50MA, 직전 종가 >= 50MA)
                is_trailing_sell_signal = (current_candle['close'] < ma50_current) and \
                                          (prev_candle['close'] >= prev_ma50)
                
                # 1% 이상 수익 조건
                is_profitable = profit_rate >= 1.0

                # 50MA 하향 돌파 및 1% 이상 수익일 때
                if is_trailing_sell_signal and is_profitable:
                    raw_action = "Sell" # 전량 매도
                    self._log(f"나머지 절반 매도 조건 만족: 50MA 하향 돌파 및 수익 1% 이상 ({profit_rate:+.2f}%)")
                    
                    if mode == 'TRADING':
                        self._execute_sell(ticker, is_half_sell=False)
                    else: # SIMULATION 모드에서 전량 매도 후 보유 기록 삭제
                        del self.holdings[ticker]
                
                # 50MA 하향 이탈 및 3개 연속 캔들 닿음 조건 (수익률 1% 미만일 때 추가)
                else:
                    # 50MA 보다 캔들 고가(High)가 낮은 캔들이 3개 연속인지 확인
                    is_below_ma50 = df.tail(3).apply(lambda x: x['high'] < x['MA50'], axis=1).all()
                    
                    if not is_profitable and is_below_ma50:
                        raw_action = "Sell" # 전량 매도
                        self._log(f"나머지 절반 매도 조건 만족: 수익 1% 미만({profit_rate:+.2f}%) & 50MA 아래 3개 연속 캔들({is_below_ma50})")
                        
                        if mode == 'TRADING':
                             self._execute_sell(ticker, is_half_sell=False)
                        else: # SIMULATION 모드에서 전량 매도 후 보유 기록 삭제
                             del self.holdings[ticker]
                             
                    else:
                        self._log(f"보유 중: 나머지 절반 매도 대기. 50MA 하향 돌파({is_trailing_sell_signal}), 수익률({profit_rate:+.2f}%)")
            
            # 2-3. 전량 손절 (50MA 하향 돌파) - 절반 매도 플래그가 False일 때
            else:
                 # 50MA 하향 돌파 (캔들 꼬리 포함 닿으면 안됨 -> 캔들 저가(low)가 50MA보다 낮을 경우 손절)
                 # *요청대로 '캔들 전체가 하향 돌파'는 캔들의 low가 50MA보다 낮을 경우로 해석합니다.
                 is_stop_loss_signal = current_candle['low'] < ma50_current
                 
                 if is_stop_loss_signal:
                     raw_action = "Sell" # 전량 매도 (손절)
                     profit_rate = ((current_price / buy_price) - 1) * 100
                     self._log(f"손절 조건 만족: 50MA 하향 돌파 (저가:{current_candle['low']:,.0f}, MA50:{ma50_current:,.0f}). 수익률: {profit_rate:+.2f}%")
                     
                     if mode == 'TRADING':
                         self._execute_sell(ticker, is_half_sell=False)
                     else: # SIMULATION 모드에서 전량 매도 후 보유 기록 삭제
                         del self.holdings[ticker]
                 else:
                    profit_rate = ((current_price / buy_price) - 1) * 100
                    self._log(f"보유 중: 손절 대기. 50MA 하향 돌파({is_stop_loss_signal}), 수익률({profit_rate:+.2f}%)")

        return raw_action, current_price


    def _run_trading_loop(self, load_time, strategy, timeframe, tickers, auto_select, mode):
        """실제 트레이딩 로직 (별도 스레드에서 실행)"""
        
        action_map = {"Buy": "매수 대기 중", "Hold": "보유 중", "Sell": "매도 대기 중", "Wait": "탐색 중", "Sell (Half)": "절반 매도"} 
        is_development_mode = (mode == 'DEVELOPMENT')
        
        timeframe_map = {'1분': 'minute1', '3분': 'minute3', '5분': 'minute5', '10분': 'minute10', '15분': 'minute15', 
                         '30분': 'minute30', '1시간': 'hour1', '4시간': 'hour4', '1일': 'day', '1주': 'week'}
        
        while self.trading_active:
            try:
                
                current_tickers = []
                if tickers:
                    current_tickers = tickers
                elif is_development_mode:
                    current_tickers = ['KRW-BTC'] # 개발 모드 기본값
                    self.master.after(0, lambda: self.status_text.set(f"개발 모드 / 종목 미입력: KRW-BTC 로딩 중"))
                
                
                if not current_tickers:
                    status_msg = f"종목 탐색 중 / 대상 종목 없음"
                    self.master.after(0, lambda: self.status_text.set(status_msg))
                    time.sleep(load_time)
                    continue

                target_ticker = current_tickers[0] 
                self.target_ticker = target_ticker 
                
                
                if target_ticker in pyupbit.get_tickers(fiat="KRW"):
                    
                    selected_timeframe_label = self.ma_timeframe_var.get()
                    
                    # 5분봉_50선_트레이딩 전략은 5분봉으로 고정
                    if strategy == '5분봉_50선_트레이딩':
                         selected_interval = 'minute5'
                         selected_timeframe_label = '5분'
                    else:
                         selected_interval = timeframe_map.get(selected_timeframe_label, 'day')
                    
                    # 캔들 데이터 로드
                    df = pyupbit.get_ohlcv(target_ticker, interval=selected_interval, count=400) 
                    
                    current_price = None
                    raw_action = "Wait"
                    
                    if df is not None and len(df) >= 200:
                        
                        # 지표 계산
                        df['MA50'] = self._calculate_moving_average(df, 50)
                        df['MA200'] = self._calculate_moving_average(df, 200)
                        df['VWMA100'] = self._calculate_vwma(df, 100) 

                        current_price = df.iloc[-1]['close'] 
                        
                        # 차트 업데이트
                        self.master.after(0, lambda: self._draw_chart(df, selected_timeframe_label))
                    
                    # DEVELOPMENT Mode Specific Logging
                    if is_development_mode and df is not None and len(df) >= 200:
                        
                        ma50_current = df['MA50'].iloc[-1]
                        ma200_current = df['MA200'].iloc[-1]
                        vwma100_current = df['VWMA100'].iloc[-1]
                        
                        # 상태창 업데이트
                        status_msg = f"개발 모드 ({target_ticker}) @ {current_price:,.0f} 원 ({selected_timeframe_label} 로드 완료)"
                        self.master.after(0, lambda: self.status_text.set(status_msg))
                        
                        # 로그에 상세 정보 출력
                        self._log(f"--- 개발 모드 데이터 로깅: {target_ticker} ({selected_timeframe_label}) ---")
                        self._log(f"현재 가격: {current_price:,.0f} 원")
                        self._log(f"MA50: {ma50_current:,.0f} 원 / MA200: {ma200_current:,.0f} 원 / VWMA100: {vwma100_current:,.0f} 원")
                        
                        if DEBUG_MODE_CANDLE:
                            recent_trend_df = df.tail(200).copy()
                            self._log(f"캔들 및 이평선 추세 데이터 (최근 {len(recent_trend_df)}개): \n{recent_trend_df[['close', 'MA50', 'MA200', 'VWMA100']].to_string()}")
                    
                    # SIMULATION/TRADING Mode Specific Logic
                    elif not is_development_mode:
                        
                        # 현재 가격 재조회 (캔들 데이터가 부족하거나 없을 경우)
                        if current_price is None:
                            current_price = pyupbit.get_current_price(target_ticker)

                        if current_price:
                            
                            if strategy == '5분봉_50선_트레이딩':
                                raw_action, current_price = self._strategy_5min_ma50(target_ticker, df, mode)
                            # elif strategy == '이동평균매매':
                            #     raw_action = self._strategy_moving_average(target_ticker, df, mode)
                            else:
                                raw_action = "Wait"
                            
                            
                            # ------------------------------------------------
                            # 2. [SIMULATION vs TRADING] 주문 실행 또는 가상 기록 (strategy_5min_ma50에서 이미 처리)
                            # ------------------------------------------------
                            # strategy_5min_ma50에서 직접 SIMULATION/TRADING 모드에 따른 holdings/execute_buy/sell 처리를 하므로,
                            # 여기서는 상태 업데이트 및 로깅만 수행

                            
                            # ------------------------------------------------
                            # 3. 상태 업데이트 및 로깅
                            # ------------------------------------------------
                            korean_status = action_map.get(raw_action, "알 수 없음") 
                            
                            profit_rate_str = ""
                            if target_ticker in self.holdings:
                                buy_price = self.holdings[target_ticker]['buy_price']
                                profit_rate = ((current_price / buy_price) - 1) * 100
                                profit_rate_str = f" (수익률: {profit_rate:+.2f}%, {'매도 대기 중' if self.holdings[target_ticker].get('half_sold') else '절반 대기 중'})"

                            
                            # 상태창 업데이트
                            new_status = f"{target_ticker} ({korean_status}) @ {current_price:,.0f} 원{profit_rate_str}"
                            self.master.after(0, lambda: self.status_text.set(new_status))
                            
                            log_message = f"현재 상태: ({target_ticker}) {korean_status} (현재 가격: {current_price:,.0f} 원{profit_rate_str})"
                            self._log(log_message)
                        else:
                            self.master.after(0, lambda: self.status_text.set(f"{target_ticker} 데이터 로드 실패"))
                            self._log(f"{target_ticker} 현재가 데이터를 불러오지 못했습니다.")
                            
                    else:
                        # 데이터 로드 실패 또는 데이터 불충분
                        self.master.after(0, lambda: self.status_text.set(f"{target_ticker} 데이터 로드 실패/불충분"))
                        self._log(f"데이터 로드 실패: {target_ticker} 캔들 데이터를 불러오지 못했거나 200개 미만입니다.")


                else:
                    self.master.after(0, lambda: self.status_text.set(f"{target_ticker} (잘못된 종목명)"))


                time.sleep(load_time)

            except Exception as e:
                error_msg = f"트레이딩 루프 오류 발생: {type(e).__name__} - {e}"
                self._log(error_msg) 
                self.master.after(0, lambda: self.status_text.set(f"오류 발생: {type(e).__name__}"))
                time.sleep(5) 
        
        self.master.after(0, lambda: self.status_text.set("트레이딩 종료 완료"))


    def _stop_trading(self):
        """트레이딩 종료 버튼 클릭 핸들러"""
        
        if not self.trading_active:
            return
            
        self.trading_active = False
        self.status_text.set("종료 요청 중...")
        
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        
        self._log("트레이딩 종료 요청됨. 로그 저장 중...")
        
        self._save_log_to_file("MANUAL_STOP")

        if self.trading_thread and self.trading_thread.is_alive():
            for _ in range(30):
                if not self.trading_thread.is_alive():
                    break
                time.sleep(0.1)

        self.status_text.set("트레이딩 종료 완료")

if __name__ == "__main__":
    try:
        import pandas as pd
        import openpyxl
        import numpy as np
        import matplotlib.pyplot 
        print("필수 라이브러리(Pandas, openpyxl, numpy, Matplotlib) 로드 확인 완료.")
    except ImportError as e:
        print(f"경고: 필요한 라이브러리 중 일부가 설치되지 않았습니다. ({e.name})")
        print("시각화 기능 사용을 위해 'pip install matplotlib openpyxl'을 실행하세요.")
    
    try:
        if not (os.getenv("UPBIT_ACCESS_KEY") and os.getenv("UPBIT_SECRET_KEY")):
             print("경고: .env 파일에 UPBIT_ACCESS_KEY 또는 UPBIT_SECRET_KEY가 설정되지 않았습니다.")
    except Exception:
        pass 

    root = tk.Tk()
    app = AutoTradingGUI(root)
    # 윈도우 닫기 이벤트 시 트레이딩 종료 로직 실행
    root.protocol("WM_DELETE_WINDOW", lambda: [app._stop_trading() if app.trading_thread else None, root.destroy()])
    root.mainloop()