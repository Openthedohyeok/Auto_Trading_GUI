import tkinter as tk
from tkinter import ttk, messagebox, simpledialog 
import os
from dotenv import load_dotenv
import pyupbit
import time
import threading
import datetime 
import pandas as pd # 🚨 추가: 엑셀 파일 저장을 위해 pandas import

# 📌 버전 관리 변수 설정
APP_VERSION = "v00.00.01" # 🚨 수정: 버전 v00.00.01로 업데이트
LOG_DIR = "TRADING_LOG" # 로그 저장 폴더명

class AutoTradingGUI:
    """Upbit 자동 트레이딩 GUI 클래스"""

    def __init__(self, master):
        self.master = master
        master.title(f"Auto Trading ({APP_VERSION})")
        master.geometry("1200x550") 
        
        # .env 파일 로드 및 API 키 불러오기 (기존 로직 유지)
        load_dotenv()
        self.access_key = os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = os.getenv("UPBIT_SECRET_KEY")
        
        # pyupbit 인스턴스 초기화 (기존 로직 유지)
        self.upbit = None
        if self.access_key and self.secret_key:
            try:
                self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
                print("Upbit API 키 로드 성공")
            except Exception as e:
                messagebox.showerror("API 오류", f"Upbit 객체 생성 오류: {e}")
        else:
            messagebox.showwarning("API 경고", ".env 파일에서 API 키를 불러올 수 없습니다.")

        # ⚙️ 트레이딩 설정 변수
        self.min_trade_volume = 0 # 최소 거래 대금 저장 변수 (원화 기준)
        # 🚨 현재 보유 종목 및 매수 정보를 저장할 딕셔너리
        self.holdings = {} 
        
        # ⚙️ GUI 구성 요소 초기화
        self._create_frames()
        self._create_widgets()
        self._layout_widgets()

        # 🔄 트레이딩 상태 변수
        self.trading_active = False
        self.status_text.set("시작 대기 중")
        self.trading_thread = None 
        self.log_save_thread = None
        
        # 로그 초기화
        self._log_no_source(f"Auto Trading ({APP_VERSION})")


    def _create_frames(self):
        """GUI 레이아웃을 위한 프레임 생성 (좌측과 우측 분리)"""
        style = ttk.Style()
        # 🚨 기본 폰트를 '맑은 고딕'으로 설정
        style.configure('TFrame', padding=10, relief='flat', font=('Malgun Gothic', 10))
        style.configure('TLabel', font=('Malgun Gothic', 10))
        style.configure('TCheckbutton', font=('Malgun Gothic', 10))
        style.configure('TButton', font=('Malgun Gothic', 10))
        style.configure('TCombobox', font=('Malgun Gothic', 10))
        style.configure('TEntry', font=('Malgun Gothic', 10))
        
        # 메인 컨테이너 프레임 (좌/우 분할)
        self.main_frame = ttk.Frame(self.master)
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.left_panel = ttk.Frame(self.main_frame)
        self.right_panel = ttk.Frame(self.main_frame)
        
        self.left_panel.pack(side='left', fill='y', padx=(0, 10))
        self.right_panel.pack(side='left', fill='both', expand=True)

        # 좌측 패널의 하위 프레임
        self.status_frame = ttk.LabelFrame(self.left_panel, text="1. 현재 상태", padding="10")
        self.options_frame = ttk.LabelFrame(self.left_panel, text="2. 트레이딩 옵션", padding="10")
        self.settings_frame = ttk.LabelFrame(self.left_panel, text="3. 전략 상세 설정", padding="10")
        self.etc_frame = ttk.LabelFrame(self.left_panel, text="4. 기타 설정", padding="10")
        self.button_frame = ttk.Frame(self.left_panel)
        
        # 5. 실시간 로그 프레임
        self.log_frame = ttk.LabelFrame(self.right_panel, text="5. 실시간 로그", padding="10")


    def _create_widgets(self):
        """GUI 위젯 생성 (프레임에 소속 지정)"""
        
        # 1. 현재 상태 ------------------------------------------
        self.status_text = tk.StringVar()
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_text, 
                                      font=("Malgun Gothic", 12, "bold"), foreground="blue")
        
        # 🚨 추가: 잔고 표시 변수
        self.balance_text = tk.StringVar(value="잔고 정보 (KRW)")
        
        # 🚨 추가: 잔고 확인 버튼
        self.check_balance_button = ttk.Button(self.status_frame, text="현재 잔고 보기", command=self._check_balance)
        
        # 🚨 추가: 잔고 표시 레이블
        self.balance_label = ttk.Label(self.status_frame, textvariable=self.balance_text, 
                                      font=("Malgun Gothic", 10), foreground="green")

        # 2. 트레이딩 옵션 ------------------------------------------
        self.mode_var = tk.StringVar(value='SIMULATION')
        self.mode_label = ttk.Label(self.options_frame, text="모드 선택:")
        self.mode_options = ['SIMULATION', 'TRADING']
        self.mode_menu = ttk.Combobox(self.options_frame, textvariable=self.mode_var, values=self.mode_options, state='readonly')
        
        self.strategy_var = tk.StringVar(value='이동평균매매')
        self.strategy_label = ttk.Label(self.options_frame, text="전략 선택:")
        self.strategy_options = ['이동평균매매', '불장단타왕_1']
        self.strategy_menu = ttk.Combobox(self.options_frame, textvariable=self.strategy_var, values=self.strategy_options, state='readonly')
        self.strategy_menu.bind("<<ComboboxSelected>>", self._toggle_ma_options)
        
        # 🚨 트레이딩 금액 (%) 설정
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
                                                variable=self.auto_select_var)
        
        # 4. 기타 설정 ------------------------------------------
        self.log_save_time_var = tk.StringVar(value='24') # 기본값 24시간
        self.log_save_time_label = ttk.Label(self.etc_frame, text="로그 저장 주기 (시간):")
        self.log_save_time_entry = ttk.Entry(self.etc_frame, textvariable=self.log_save_time_var, font=('Malgun Gothic', 10))
        
        # 시작/종료 버튼 (폰트는 style에 의해 적용됨)
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
        
        # 좌측 패널 배치 (pack)
        self.status_frame.pack(padx=5, pady=5, fill="x")
        self.options_frame.pack(padx=5, pady=5, fill="x")
        self.settings_frame.pack(padx=5, pady=5, fill="x")
        self.etc_frame.pack(padx=5, pady=5, fill="x")
        self.button_frame.pack(padx=5, pady=10, fill="x")

        # 우측 로그 패널 배치 (pack)
        self.log_frame.pack(padx=5, pady=5, fill="both", expand=True)

        # 1. 현재 상태 (pack) 🚨 잔고 버튼 및 레이블 추가에 따른 레이아웃 변경
        self.status_label.pack(fill="x", pady=(5, 0)) 
        self.check_balance_button.pack(fill="x", pady=5)
        self.balance_label.pack(fill="x", pady=(0, 5))
        
        # 2. 트레이딩 옵션 (grid)
        self.options_frame.columnconfigure(1, weight=1)
        self.mode_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.mode_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.strategy_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.strategy_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # 🚨 트레이딩 금액 옵션 배치
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
        
        # 5. 실시간 로그 (grid)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        self.log_scrollbar.grid(row=0, column=1, sticky='ns')

    def _toggle_ma_options(self, event):
        """전략 선택에 따라 이동평균매매 옵션 활성화/비활성화"""
        if self.strategy_var.get() == '이동평균매매':
            self.ma_timeframe_label.config(state='normal')
            self.ma_timeframe_menu.config(state='readonly')
        else:
            self.ma_timeframe_label.config(state='disabled')
            self.ma_timeframe_menu.config(state='disabled')
            
    def _check_balance(self):
        """현재 KRW 잔고를 조회하여 GUI에 표시"""
        
        def fetch_balance():
            # API 키 로드 여부 확인
            if not self.upbit:
                self.master.after(0, lambda: self.balance_text.set("API 키 로드 실패"))
                return
            
            # GUI 업데이트: 버튼 잠금 및 메시지 표시 (GUI 스레드에서 실행)
            self.master.after(0, lambda: self.check_balance_button.config(state='disabled'))
            self.master.after(0, lambda: self.balance_text.set("잔고 조회 중..."))
            self.master.update()
            
            try:
                # KRW 잔고 조회
                balance = self.upbit.get_balance("KRW") 
                
                if balance is not None:
                    # 잔고 표시: 쉼표 형식으로 포맷팅
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

            # GUI 업데이트: 버튼 잠금 해제 (GUI 스레드에서 실행)
            self.master.after(0, lambda: self.check_balance_button.config(state='normal'))

        # 잔고 조회를 새로운 스레드에서 실행 (GUI freeze 방지)
        threading.Thread(target=fetch_balance, daemon=True).start()

    def _log_no_source(self, message):
        """실시간 로그를 Text 위젯에 추가 (소스 태그 없음)"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # 콘솔 출력
        print(log_entry.strip())
        
        # GUI Text 위젯 업데이트
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END) # 스크롤을 항상 아래로 이동
        self.log_text.config(state='disabled')

    def _log(self, message):
        """실시간 로그를 Text 위젯에 추가 (소스 태그 없음)"""
        self._log_no_source(message)

    def _save_log_to_file(self, prefix="TRADING_"): # prefix는 TRADING_으로 통일하여 사용
        """현재까지의 로그 내용을 파일로 저장 (엑셀 형식)"""
        try:
            # 1. TRADING_LOG 폴더 생성 (이미 있다면 건너김)
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            
            # 2. 파일명 생성 (TRADING_LOG_YYYYMMDD_HHMMSS.xlsx 형식)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # 🚨 수정: 파일명 형식 변경 TRADING_LOG_날짜_시간.xlsx
            filename = f"{LOG_DIR}/TRADING_LOG_{timestamp}.xlsx" 
            
            # 3. 로그 내용 파싱
            log_content = self.log_text.get("1.0", tk.END).strip().split('\n')
            
            data = []
            for line in log_content:
                if line.startswith('['):
                    try:
                        # 시간 부분 파싱 ([YYYY-MM-DD HH:MM:SS])
                        time_str = line[1:20] 
                        # 메시지 부분 파싱
                        message = line[22:].strip()
                        data.append({'시간': time_str, '로그 메시지': message})
                    except Exception:
                        # 파싱 오류 발생 시 전체 라인을 메시지로 저장
                        data.append({'시간': '', '로그 메시지': line})
            
            if not data:
                self._log("저장할 로그 내용이 없습니다.")
                return

            # 4. Pandas DataFrame 생성
            df = pd.DataFrame(data)
            
            # 5. 엑셀 파일로 저장 (openpyxl 엔진 사용)
            df.to_excel(filename, index=False, engine='openpyxl')
            
            self._log(f"로그가 성공적으로 엑셀 파일로 저장되었습니다: {filename}")
        except Exception as e:
            self._log(f"로그 파일 저장 중 오류 발생 (엑셀 저장): {e}")


    def _handle_start(self):
        """트레이딩 시작 버튼 클릭 시, 자동 선택 여부에 따라 추가 입력 받음"""
        
        if self.trading_active:
            return

        tickers = [t.strip() for t in self.ticker_input_var.get().upper().split(',') if t.strip()]
        auto_select = self.auto_select_var.get()
        
        # 종목 자동 선택 체크 시, 최소 거래 대금 입력 팝업 띄우기
        if auto_select:
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
        
        elif not tickers:
             messagebox.showwarning("종목 설정 오류", "매매 희망 종목을 입력하거나 '종목 자동 선택'을 활성화해야 합니다.")
             return
             
        # 모든 설정이 완료되면 실제 트레이딩 시작 함수 호출
        self._start_trading()

    def _start_trading(self):
        """실제 트레이딩 로직 시작"""
        
        # 입력값 유효성 검사 (데이터 로딩 시간, 로그 주기, 트레이딩 금액)
        try:
            load_time = int(self.data_load_time_var.get())
            log_save_time_hours = int(self.log_save_time_var.get())
            trade_ratio = int(self.trade_ratio_var.get())
            
            if load_time <= 0 or log_save_time_hours <= 0 or not (0 <= trade_ratio <= 100):
                raise ValueError
        except ValueError:
            messagebox.showerror("입력 오류", "설정값(로딩 시간, 로그 주기, 트레이딩 금액)을 확인해 주세요.")
            return

        # 상태 업데이트 및 버튼 제어
        self.trading_active = True
        self.status_text.set("트레이딩 시작됨 (종목 탐색 중...)")
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        # holdings 초기화 (시작 시 이전 상태 초기화)
        self.holdings = {}

        # 설정 값 로드
        mode = self.mode_var.get()
        strategy = self.strategy_var.get()
        timeframe_label = self.ma_timeframe_var.get()
        timeframe_map = {'1분': 'minute1', '3분': 'minute3', '5분': 'minute5', '10분': 'minute10', '15분': 'minute15', 
                         '30분': 'minute30', '1시간': 'hour1', '4시간': 'hour4', '1일': 'day', '1주': 'week'}
        timeframe = timeframe_map.get(timeframe_label, 'minute1') if strategy == '이동평균매매' else 'N/A'
        tickers = [t.strip() for t in self.ticker_input_var.get().upper().split(',') if t.strip()]
        auto_select = self.auto_select_var.get()
        
        self._log("--- 트레이딩 시작 설정 ---")
        self._log(f"모드: {mode}")
        self._log(f"전략: {strategy} (시간봉: {timeframe_label})") 
        self._log(f"트레이딩 금액: {trade_ratio}%") 
        self._log(f"데이터 로딩 시간: {load_time}초")
        self._log(f"종목 자동 선택: {auto_select}")
        if auto_select:
             self._log(f"  ㄴ 최소 거래 대금: {self.min_trade_volume:,.0f} 원")
             self._log(f"  ㄴ 대상 종목: {'전체 KRW 종목' if not tickers else str(tickers)}")
        else:
             self._log(f"매매 희망 종목: {tickers}")
        self._log(f"로그 저장 주기: {log_save_time_hours} 시간")
        self._log("--------------------------")

        # 📌 실제 트레이딩 로직을 별도의 스레드에서 시작 
        self.trading_thread = threading.Thread(target=self._run_trading_loop, 
                                               args=(load_time, strategy, timeframe, tickers, auto_select, mode))
        self.trading_thread.daemon = True 
        self.trading_thread.start()
        
        # 📌 로그 자동 저장 스레드 시작
        self.log_save_thread = threading.Thread(target=self._run_log_save_loop, 
                                                args=(log_save_time_hours,))
        self.log_save_thread.daemon = True
        self.log_save_thread.start()

    def _run_log_save_loop(self, save_interval_hours):
        """설정된 시간마다 로그를 파일로 저장하는 루프"""
        
        # 초 단위로 변환
        save_interval_seconds = save_interval_hours * 3600
        self._log(f"로그 자동 저장 루프 시작. 주기: {save_interval_hours} 시간 ({save_interval_seconds}초)")
        
        while self.trading_active:
            try:
                # 지정된 시간만큼 대기 (종료 플래그 확인하며 sleep)
                for _ in range(save_interval_seconds):
                    if not self.trading_active:
                        break
                    time.sleep(1)
                
                if self.trading_active:
                    # GUI 스레드에서 파일 저장 호출
                    self.master.after(0, lambda: self._save_log_to_file("AUTO_SAVE")) 
            
            except Exception as e:
                self._log(f"로그 자동 저장 중 치명적인 오류 발생: {e}")
                time.sleep(60) # 오류 발생 시 1분 대기 후 재시도

        self._log("로그 자동 저장 루프 종료.")
        
    def _run_trading_loop(self, load_time, strategy, timeframe, tickers, auto_select, mode):
        """실제 트레이딩 로직 (별도 스레드에서 실행)"""
        
        action_map = {"Buy": "매수 대기 중", "Hold": "보유 중", "Sell": "매도 대기 중", "Wait": "탐색 중"} # 상태 메시지 업데이트
        
        # 🚨 임시 매수 가격 설정 (임시 로직에서 사용)
        initial_buy_price = 45000000 
        initial_buy_volume = 0.001
        
        while self.trading_active:
            try:
                
                # 2. 종목 선택 (자동 선택 로직)
                current_tickers = []
                if auto_select:
                    all_krw = pyupbit.get_tickers(fiat="KRW") 
                    
                    if tickers:
                        scan_list = [t for t in all_krw if t in tickers]
                        self._log(f"제한된 종목({len(scan_list)}개) 내에서 스캔 중.")
                    else:
                        scan_list = all_krw
                        self._log(f"전체 KRW 종목({len(scan_list)}개) 스캔 중.")

                    # TODO: 최소 거래 대금 필터링 로직 추가 필요 
                    current_tickers = scan_list
                    
                elif tickers:
                    current_tickers = tickers
                
                
                # 3. 데이터 로드 및 판단
                if not current_tickers:
                    # 1. 상태 업데이트 (대상 종목 없음)
                    status_msg = f"종목 탐색 중 / 대상 종목 없음"
                    self.master.after(0, lambda: self.status_text.set(status_msg))
                    self._log("자동 선택 기준을 만족하거나, 지정된 매매 희망 종목이 없습니다.")
                     
                else:
                    target_ticker = current_tickers[0] # 임시로 첫 번째 종목만 확인
                    
                    if target_ticker in pyupbit.get_tickers(fiat="KRW"):
                        current_price = pyupbit.get_current_price(target_ticker)
                        
                        if current_price:
                            
                            # 🚨 임시 매수/매도 로직 및 holdings 업데이트
                            raw_action = "Wait"
                            if target_ticker not in self.holdings:
                                # 보유하지 않은 경우: 임시 매수 로직 (4500만원 이하에서만 매수 대기)
                                if current_price <= initial_buy_price:
                                    raw_action = "Buy"
                                    # 임시로 매수 가정 (실제 매수 아님)
                                    self.holdings[target_ticker] = {'buy_price': initial_buy_price, 'buy_volume': initial_buy_volume}
                                    
                            else:
                                # 보유 중인 경우: 임시 보유/매도 로직
                                raw_action = "Hold" 
                                # 매도 로직: 6000만원 이상이면 매도 대기 (임시)
                                if current_price >= 60000000:
                                    raw_action = "Sell"
                                    
                            korean_status = action_map.get(raw_action, "알 수 없음") 
                            
                            # 🚨 수익률 계산
                            profit_rate_str = ""
                            if target_ticker in self.holdings:
                                buy_price = self.holdings[target_ticker]['buy_price']
                                # 수익률 계산: (현재가 / 매수가 - 1) * 100
                                profit_rate = ((current_price / buy_price) - 1) * 100
                                profit_rate_str = f" (수익률: {profit_rate:+.2f}%)"

                                # 임시 매도 시 holding에서 제거 (실제 매도 아님)
                                if raw_action == "Sell":
                                     self._log(f"매도 신호 발생. ({target_ticker}) 보유 청산 가정.")
                                     del self.holdings[target_ticker]
                                     korean_status = "매도 대기 중" # 상태 다시 설정
                            
                            
                            # 🚨 수정: 상태 표시줄 업데이트
                            new_status = f"{target_ticker} ({korean_status}) @ {current_price:,.0f} 원{profit_rate_str}"
                            self.master.after(0, lambda: self.status_text.set(new_status))
                            
                            # 🚨 수정: 로그 형식 변경 (수익률 포함)
                            log_message = f"현재 상태: ({target_ticker}) {korean_status} (현재 가격: {current_price:,.0f} 원{profit_rate_str})"
                            self._log(log_message)
                        else:
                            # 1. 상태 업데이트 (데이터 로드 실패)
                            self.master.after(0, lambda: self.status_text.set(f"{target_ticker} 데이터 로드 실패"))
                            self._log(f"{target_ticker} 현재가 데이터를 불러오지 못했습니다.")
                    else:
                         # 1. 상태 업데이트 (잘못된 종목명)
                         self.master.after(0, lambda: self.status_text.set(f"{target_ticker} (잘못된 종목명)"))
                         self._log(f"지정된 종목({target_ticker})이 KRW 마켓에 없습니다.")


                # 5. 다음 데이터 로딩까지 대기
                time.sleep(load_time)

            except Exception as e:
                error_msg = f"트레이딩 루프 오류 발생: {type(e).__name__} - {e}"
                self._log(error_msg)
                self.master.after(0, lambda: self.status_text.set(f"오류 발생: {type(e).__name__}"))
                time.sleep(5) 
        
        # 루프 종료 후 상태 업데이트
        self.master.after(0, lambda: self.status_text.set("트레이딩 종료 완료"))
        self._log("트레이딩 루프 종료.")


    def _stop_trading(self):
        """트레이딩 종료 버튼 클릭 핸들러"""
        
        if not self.trading_active:
            return
            
        self.trading_active = False
        self.status_text.set("종료 요청 중...")
        
        # 버튼 제어
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        
        self._log("트레이딩 종료 요청됨. 로그 저장 중...")
        
        # 🚨 수정: 트레이딩 종료 시 로그를 파일로 저장
        # GUI 스레드에서 직접 호출
        self._save_log_to_file("MANUAL_STOP")

        # 스레드 종료 대기 (데몬 스레드라 필수는 아니지만, 깔끔한 종료를 위해 짧은 대기 시간만 부여)
        if self.trading_thread and self.trading_thread.is_alive():
            # 0.1초씩 30번 (총 3초)까지만 대기
            for _ in range(30):
                if not self.trading_thread.is_alive():
                    break
                time.sleep(0.1)

        self.status_text.set("트레이딩 종료 완료")

if __name__ == "__main__":
    # 라이브러리 존재 여부 확인 
    try:
        # Pandas와 openpyxl 설치 확인을 위한 임시 코드
        import pandas as pd
        import openpyxl
        print("Pandas 및 openpyxl 로드 확인 완료.")
    except ImportError:
        print("🚨 경고: 엑셀 파일 저장을 위해 'pip install pandas openpyxl' 명령어로 라이브러리를 설치해야 합니다.")
    
    try:
        if not (os.getenv("UPBIT_ACCESS_KEY") and os.getenv("UPBIT_SECRET_KEY")):
             print("경고: .env 파일에 UPBIT_ACCESS_KEY 또는 UPBIT_SECRET_KEY가 설정되지 않았습니다.")
    except Exception:
        pass 

    root = tk.Tk()
    app = AutoTradingGUI(root)
    # 창을 닫을 때 스레드 종료를 위해 trading_active 플래그를 False로 설정
    root.protocol("WM_DELETE_WINDOW", lambda: [app._stop_trading() if app.trading_thread else None, root.destroy()])
    root.mainloop()