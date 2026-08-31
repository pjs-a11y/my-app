import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime
from collections import Counter

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 분석기", page_icon="📊", layout="centered")

# 모바일 세로 스크롤 최소화 및 가로 버튼 레이아웃 CSS
st.markdown("""
<style>
    .block-container { padding: 0.5rem 0.6rem !important; }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.82rem !important; line-height: 1.35 !important; }
    .stButton>button { padding: 0.35rem 0.05rem !important; font-size: 0.82rem !important; font-weight: bold; }
    hr { margin: 0.3rem 0 !important; border-color: #ddd !important; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
DATA_FILE = os.path.join(BASE_DIR, "ladder_data_history.txt")
MAX_DATA_SIZE = 3000

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
}

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

def load_data():
    records = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        records.append({'date': parts[0], 'round': int(parts[1]), 'result': parts[2]})
        except Exception:
            pass
    return records

def save_data(records):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            for r in records[-MAX_DATA_SIZE:]:
                f.write(f"{r['date']}|{r['round']}|{r['result']}\n")
    except Exception:
        pass

def analyze_prediction(records):
    target_records = records[-MAX_DATA_SIZE:]
    results = [r['result'] for r in target_records]
    n = len(results)
    if n < 4:
        return None

    last_4 = results[-4:]
    pattern_status = "일반 패턴 구간"
    if len(set(last_4)) == 1:
        pattern_status = f"🔥 {last_4[-1]} 장줄 연속 구간"
    elif n >= 4 and results[-1] != results[-2] and results[-2] != results[-3] and results[-3] != results[-4]:
        pattern_status = "⚡ 퐁당 퐁당 유의 구간"

    p3 = results[-3:]
    m3 = [results[j+3] for j in range(n-3) if results[j:j+3] == p3]
    p2 = results[-2:]
    m2 = [results[j+2] for j in range(n-2) if results[j:j+2] == p2]

    target = m3 if len(m3) >= 3 else m2
    if not target:
        return None

    tot = len(target)
    s_counts = Counter([ITEM_MAP[x][0] for x in target])
    l_counts = Counter([ITEM_MAP[x][1] for x in target])

    rec_s = '우' if s_counts['우'] >= s_counts['좌'] else '좌'
    s_prob = (max(s_counts['우'], s_counts['좌']) / tot) * 100.0

    rec_l = '사' if l_counts['사'] >= l_counts['삼'] else '삼'
    l_prob = (max(l_counts['사'], l_counts['삼']) / tot) * 100.0

    return (rec_s, s_prob, rec_l, l_prob, pattern_status)

def calculate_detailed_stats(records, target_date=None, limit_recent=None):
    if limit_recent:
        eval_records = records[-limit_recent:]
    else:
        eval_records = records

    n = len(eval_records)
    if n < 5:
        return None

    tot_count = 0
    c_win, s_win, l_win = 0, 0, 0

    for i in range(4, n):
        if target_date and eval_records[i]['date'] != target_date:
            continue

        past_sub = eval_records[:i]
        pred = analyze_prediction(past_sub)
        if pred:
            act = eval_records[i]['result']
            act_s, act_l = ITEM_MAP[act][0], ITEM_MAP[act][1]
            rec_s, _, rec_l, _, _ = pred
            
            tot_count += 1
            s_ok = (rec_s == act_s)
            l_ok = (rec_l == act_l)
            
            if s_ok or l_ok: 
                c_win += 1
            if s_ok: 
                s_win += 1
            if l_ok: 
                l_win += 1

    if tot_count == 0:
        return None

    return {
        'total': tot_count,
        'c_win': c_win, 'c_lose': tot_count - c_win, 'c_rate': (c_win/tot_count)*100.0,
        's_win': s_win, 's_lose': tot_count - s_win, 's_rate': (s_win/tot_count)*100.0,
        'l_win': l_win, 'l_lose': tot_count - l_win, 'l_rate': (l_win/tot_count)*100.0,
    }

# 백업 상태 관리
if "records" not in st.session_state:
    st.session_state.records = load_data()
if "history_stack" not in st.session_state:
    st.session_state.history_stack = []
if "show_bulk" not in st.session_state:
    st.session_state.show_bulk = False

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10:
        st.session_state.history_stack.pop(0)

records = st.session_state.records

# 1. 대량 입력 모드 화면
if st.session_state.show_bulk:
    st.markdown("**📋 과거 데이터 한 번에 복사/붙여넣기**")
    st.markdown("글자 사이 공백, 줄바꿈, 회차 구분 상관없이 `우사`, `우삼`, `좌사`, `좌삼` 문자를 자동으로 찾아 연속 등록합니다.")
    
    b_date = st.date_input("입력할 날짜 선택", datetime.now())
    b_start_rd = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    
    raw_text = st.text_area("텍스트 붙여넣기", height=180, placeholder="예시:\n우사 우삼 좌사 좌삼 우사\n또는\n1회 우사\n2회 우삼\n3회 좌사")
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("📥 데이터 일괄 추가", use_container_width=True):
        # 우사, 우삼, 좌사, 좌삼 패턴 추출
        found_items = re.findall(r'우사|우삼|좌사|좌삼', raw_text)
        if found_items:
            push_backup()
            curr_rd = int(b_start_rd)
            dt_str = b_date.strftime("%Y-%m-%d")
            for item in found_items:
                st.session_state.records.append({
                    'date': dt_str,
                    'round': curr_rd,
                    'result': item
                })
                curr_rd += 1
                if curr_rd > 288:
                    curr_rd = 1
            save_data(st.session_state.records)
            st.toast(f"총 {len(found_items)}개의 데이터가 일괄 등록되었습니다!")
            st.session_state.show_bulk = False
            st.rerun()
        else:
            st.error("입력한 텍스트에서 '우사', '우삼', '좌사', '좌삼'을 찾지 못했습니다.")

    if col_b2.button("❌ 취소", use_container_width=True):
        st.session_state.show_bulk = False
        st.rerun()

# 2. 데이터가 완전히 비어있을 때
elif not records:
    st.markdown("**⚙️ 최초 환경 설정**")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    
    st.write("첫 회차 결과 선택:")
    col1, col2, col3, col4 = st.columns(4)
    sel = None
    if col1.button("우삼"): sel = "우삼"
    elif col2.button("우사"): sel = "우사"
    elif col3.button("좌삼"): sel = "좌삼"
    elif col4.button("좌사"): sel = "좌사"

    if sel:
        push_backup()
        st.session_state.records.append({
            'date': init_date.strftime("%Y-%m-%d"),
            'round': int(init_round),
            'result': sel
        })
        save_data(st.session_state.records)
        st.rerun()

    st.markdown("---")
    if st.button("📋 텍스트로 한 번에 대량 입력하기", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    if st.session_state.history_stack:
        if st.button("↩️ 이전 상태로 되돌리기", use_container_width=True):
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.toast("직전 상태로 복원되었습니다.")
            st.rerun()

# 3. 메인 분석 화면
else:
    last_rec = records[-1]
    curr_date = last_rec['date']
    next_round = last_rec['round'] + 1
    if next_round > 288:
        next_round = 1

    # 상단 요약 및 대량 입력 버튼
    st.markdown(f"**날짜 : {curr_date} / 다음회차 : {next_round}회차**")
    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    # 1. 전체 누적 통계
    all_stat = calculate_detailed_stats(records)
    st.markdown("**누적**")
    if all_stat:
        st.markdown(f"조합 : {all_stat['total']}개 / {all_stat['c_win']}승 {all_stat['c_lose']}패 / 승율 {all_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {all_stat['total']}개 / {all_stat['s_win']}승 {all_stat['s_lose']}패 / 승율 {all_stat['s_rate']:.1f}%")
        st.markdown(f"줄수 : {all_stat['total']}개 / {all_stat['l_win']}승 {all_stat['l_lose']}패 / 승율 {all_stat['l_rate']:.1f}%")
    else:
        st.markdown("조합 : 0개 / 0승 0패 / 승율 0.0%\n출발 : 0개 / 0승 0패 / 승율 0.0%\n줄수 : 0개 / 0승 0패 / 승율 0.0%")

    st.markdown("---")

    # 2. 최근 3000개 누적 통계
    recent_stat = calculate_detailed_stats(records, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적**")
    if recent_stat:
        st.markdown(f"조합 : {recent_stat['total']}개 / {recent_stat['c_win']}승 {recent_stat['c_lose']}패 / 승율 {recent_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {recent_stat['total']}개 / {recent_stat['s_win']}승 {recent_stat['s_lose']}패 / 승율 {recent_stat['s_rate']:.1f}%")
        st.markdown(f"줄수 : {recent_stat['total']}개 / {recent_stat['l_win']}승 {recent_stat['l_lose']}패 / 승율 {recent_stat['l_rate']:.1f}%")
    else:
        st.markdown("조합 : 0개 / 0승 0패 / 승율 0.0%\n출발 : 0개 / 0승 0패 / 승율 0.0%\n줄수 : 0개 / 0승 0패 / 승율 0.0%")

    st.markdown("---")

    # 3. 오늘 통계
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_detailed_stats(records, target_date=curr_date)
    st.markdown(f"**오늘 : {curr_date} {w_str}**")
    if today_stat:
        st.markdown(f"조합 : {today_stat['total']}개 / {today_stat['c_win']}승 {today_stat['c_lose']}패 / 승율 {today_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {today_stat['total']}개 / {today_stat['s_win']}승 {today_stat['s_lose']}패 / 승율 {today_stat['s_rate']:.1f}%")
        st.markdown(f"줄수 : {today_stat['total']}개 / {today_stat['l_win']}승 {today_stat['l_lose']}패 / 승율 {today_stat['l_rate']:.1f}%")
    else:
        st.markdown("조합 : 0개 / 0승 0패 / 승율 0.0%\n출발 : 0개 / 0승 0패 / 승율 0.0%\n줄수 : 0개 / 0승 0패 / 승율 0.0%")

    st.markdown("---")

    # 4. 이전 회차 분석
    if len(records) >= 5:
        prev_sub = records[:-1]
        prev_pred = analyze_prediction(prev_sub)
        prev_actual = last_rec['result']
        
        if prev_pred:
            p_s, _, p_l, _, _ = prev_pred
            act_s, act_l = ITEM_MAP[prev_actual][0], ITEM_MAP[prev_actual][1]
            s_res = "성공" if p_s == act_s else "실패"
            l_res = "성공" if p_l == act_l else "실패"
            c_res = "성공" if (p_s == act_s or p_l == act_l) else "실패"
            
            st.markdown(f"**이전회차 ( {last_rec['round']}회차 )**")
            st.markdown(f"결과 : **{prev_actual}** / 예측 : **{p_s}{p_l}**")
            st.markdown(f"출발 : **{s_res}** / 줄수 : **{l_res}** / 조합 : **{c_res}**")
    st.markdown("---")

    # 5. 구간 정보 및 이번회차 예측
    curr_pred = analyze_prediction(records)
    if curr_pred:
        rec_s, s_p, rec_l, l_p, pat = curr_pred
        st.markdown(f"**구간 : {pat}**")
        st.markdown("---")
        st.markdown(f"**이번회차예측 ( {next_round}회차 )**")
        st.markdown(f"출발 : **{rec_s}** `{s_p:.2f}%` / 줄수 : **{rec_l}** `{l_p:.2f}%` ➔ **[{rec_s}{rec_l}]**")
    else:
        st.markdown("**구간 : 분석 데이터 부족**")
        st.markdown("---")
        st.markdown(f"**이번회차예측 ( {next_round}회차 )**\n데이터 축적 중...")

    st.markdown("---")
    st.markdown("**결과 입력**")

    # 가로 배치 4개 버튼
    c1, c2, c3, c4 = st.columns(4)
    b_um = c1.button("우삼", use_container_width=True)
    b_us = c2.button("우사", use_container_width=True)
    b_jm = c3.button("좌삼", use_container_width=True)
    b_js = c4.button("좌사", use_container_width=True)

    input_val = None
    if b_um: input_val = "우삼"
    elif b_us: input_val = "우사"
    elif b_jm: input_val = "좌삼"
    elif b_js: input_val = "좌사"

    if input_val:
        push_backup()
        st.session_state.records.append({
            'date': curr_date,
            'round': next_round,
            'result': input_val
        })
        save_data(st.session_state.records)
        st.rerun()

    st.markdown("---")

    # 가로 배치 제어 버튼 (패스 / 직전취소 / 초기화 / 되돌리기)
    m1, m2, m3, m4 = st.columns(4)
    
    if m1.button("패스", use_container_width=True):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "우사"})
        save_data(st.session_state.records)
        st.toast(f"{next_round}회차 패스")
        st.rerun()

    if m2.button("직전취소", use_container_width=True):
        if st.session_state.records:
            push_backup()
            popped = st.session_state.records.pop()
            save_data(st.session_state.records)
            st.toast(f"{popped['round']}회차 취소")
            st.rerun()

    if m3.button("초기화", use_container_width=True):
        push_backup()
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        st.toast("초기화되었습니다.")
        st.rerun()

    if m4.button("되돌리기", use_container_width=True):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.toast("직전 상태로 복원 완료!")
            st.rerun()
        else:
            st.toast("되돌릴 이전 기록이 없습니다.")

    st.markdown("---")

    # 6. 세부 결과 표 (당일 최신순 정렬)
    st.markdown("**세부 결과**")
    if len(records) >= 5:
        rows = []
        today_indices = [idx for idx, r in enumerate(records) if r['date'] == curr_date]
        
        for i in reversed(today_indices):
            if i < 4:
                continue
            p_sub = records[:i]
            pr = analyze_prediction(p_sub)
            act_item = records[i]['result']
            rd_num = records[i]['round']
            
            if pr:
                pr_s, _, pr_l, _, _ = pr
                pr_str = f"{pr_s}{pr_l}"
                act_s, act_l = ITEM_MAP[act_item][0], ITEM_MAP[act_item][1]
                
                s_chk = "성공" if pr_s == act_s else "실패"
                l_chk = "성공" if pr_l == act_l else "실패"
                c_chk = "성공" if (pr_s == act_s or pr_l == act_l) else "실패"
                
                rows.append({
                    "회차": f"{rd_num}회",
                    "예측 / 결과": f"{pr_str} / {act_item}",
                    "출발 줄수": f"{s_chk} {l_chk}",
                    "조합": c_chk
                })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.markdown("오늘 세부 결과 기록 없음")
    else:
        st.markdown("기록 축적 중...")
