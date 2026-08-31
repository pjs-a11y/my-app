import os
import re
import pandas as pd
import streamlit as st
from datetime import datetime
from collections import Counter

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 정밀 분석기", page_icon="📊", layout="centered")

# 모바일 한 화면에 쏙 들어오도록 CSS 스타일 수정
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; padding-left: 0.8rem !important; padding-right: 0.8rem !important; }
    h1 { font-size: 1.4rem !important; margin-bottom: 0.2rem !important; padding-top: 0rem !important; }
    h2, h3 { font-size: 1.05rem !important; margin-top: 0.4rem !important; margin-bottom: 0.2rem !important; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    div[data-testid="stMetricDelta"] { font-size: 0.7rem !important; }
    .stButton>button { padding: 0.3rem 0.2rem !important; font-size: 0.85rem !important; }
    hr { margin: 0.4rem 0 !important; }
    .element-container { margin-bottom: 0.3rem !important; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
DATA_FILE = os.path.join(BASE_DIR, "ladder_data_history.txt")
LOG_FILE = os.path.join(BASE_DIR, "ladder_predict_log.txt")
MAX_DATA_SIZE = 3000

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
}

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

def save_log(date, rd, rec_s, rec_l, actual):
    act_s, act_l = ITEM_MAP[actual][0], ITEM_MAP[actual][1]
    s_ok = (rec_s == act_s)
    l_ok = (rec_l == act_l)
    log_line = f"{date}|{rd}|예측:{rec_s}{rec_l}|실제:{actual}|방향:{'성공' if s_ok else '실패'}|줄수:{'성공' if l_ok else '실패'}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass

def calculate_stats(records):
    n = len(records)
    if n < 5:
        return None
    
    total_preds = 0
    combo_wins = 0
    dir_wins = 0
    
    for i in range(4, n):
        past_sub = records[:i]
        pred = analyze_prediction(past_sub)
        if pred:
            actual = records[i]['result']
            rec_s, _, rec_l, _, _ = pred
            pred_combo = f"{rec_s}{rec_l}"
            act_s = ITEM_MAP[actual][0]
            
            total_preds += 1
            if pred_combo == actual:
                combo_wins += 1
            if rec_s == act_s:
                dir_wins += 1
                
    if total_preds == 0:
        return None
        
    combo_rate = (combo_wins / total_preds) * 100.0
    dir_rate = (dir_wins / total_preds) * 100.0
    
    return {
        'total': total_preds,
        'combo_wins': combo_wins,
        'combo_loses': total_preds - combo_wins,
        'combo_rate': combo_rate,
        'dir_wins': dir_wins,
        'dir_rate': dir_rate
    }

def analyze_prediction(records):
    results = [r['result'] for r in records]
    n = len(results)
    if n < 4:
        return None

    p3 = results[-3:]
    m3 = [results[j+3] for j in range(n-3) if results[j:j+3] == p3]
    p2 = results[-2:]
    m2 = [results[j+2] for j in range(n-2) if results[j:j+2] == p2]

    target = m3 if len(m3) >= 3 else m2
    used_p = "3회 패턴" if len(m3) >= 3 else "2회 패턴"
    if not target:
        return None

    tot = len(target)
    s_counts = Counter([ITEM_MAP[x][0] for x in target])
    l_counts = Counter([ITEM_MAP[x][1] for x in target])

    rec_s = '우' if s_counts['우'] >= s_counts['좌'] else '좌'
    s_prob = (max(s_counts['우'], s_counts['좌']) / tot) * 100.0

    rec_l = '사' if l_counts['사'] >= l_counts['삼'] else '삼'
    l_prob = (max(l_counts['사'], l_counts['삼']) / tot) * 100.0

    return (rec_s, s_prob, rec_l, l_prob, used_p)

# 메인 UI 화면
st.markdown("<h1>📊 키노사다리 정밀 분석기</h1>", unsafe_allow_html=True)

if "records" not in st.session_state:
    st.session_state.records = load_data()

records = st.session_state.records

if not records:
    st.subheader("⚙️ 최초 환경 설정")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    
    st.write("첫 회차 결과 선택:")
    col1, col2, col3, col4 = st.columns(4)
    btn_us = col1.button("우사")
    btn_um = col2.button("우삼")
    btn_js = col3.button("좌사")
    btn_jm = col4.button("좌삼")
    
    selected_val = None
    if btn_us: selected_val = "우사"
    elif btn_um: selected_val = "우삼"
    elif btn_js: selected_val = "좌사"
    elif btn_jm: selected_val = "좌삼"

    if selected_val:
        st.session_state.records.append({
            'date': init_date.strftime("%Y-%m-%d"),
            'round': int(init_round),
            'result': selected_val
        })
        save_data(st.session_state.records)
        st.rerun()

else:
    last_record = records[-1]
    curr_date = last_record['date']
    next_round = last_record['round'] + 1
    if next_round > 288:
        next_round = 1

    st.caption(f"📅 **날짜:** {curr_date} | 🔢 **다음 입력 회차:** {next_round}회차")

    # 실시간 승률 통계
    stats = calculate_stats(records)
    if stats:
        st.markdown("### 🏆 누적 예측 성적")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("조합 승률", f"{stats['combo_rate']:.1f}%", f"{stats['combo_wins']}승 {stats['combo_loses']}패")
        sc2.metric("방향 적중률", f"{stats['dir_rate']:.1f}%", f"{stats['dir_wins']}회")
        sc3.metric("예측 횟수", f"{stats['total']}회")
        st.markdown("---")

    # 예측 엔진 구동
    pred_res = analyze_prediction(records)
    
    if pred_res:
        rec_s, s_p, rec_l, l_p, p_name = pred_res
        st.markdown("### 💡 이번 회차 예측")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("추천 방향", rec_s, f"{s_p:.0f}%")
        col_b.metric("추천 줄수", rec_l, f"{l_p:.0f}%")
        col_c.metric("추천 조합", f"{rec_s}{rec_l}", ITEM_MAP[rec_s+rec_l][2])
    else:
        st.info("💡 4회차 이상 입력 시 승률과 예측이 표시됩니다.")

    st.markdown("---")
    st.markdown("### 🎯 결과 빠른 입력")

    c1, c2, c3, c4 = st.columns(4)
    b_us = c1.button("우사", use_container_width=True)
    b_um = c2.button("우삼", use_container_width=True)
    b_js = c3.button("좌사", use_container_width=True)
    b_jm = c4.button("좌삼", use_container_width=True)

    input_item = None
    if b_us: input_item = "우사"
    elif b_um: input_item = "우삼"
    elif b_js: input_item = "좌사"
    elif b_jm: input_item = "좌삼"

    if input_item:
        if pred_res:
            save_log(curr_date, next_round, pred_res[0], pred_res[2], input_item)
        
        st.session_state.records.append({
            'date': curr_date,
            'round': next_round,
            'result': input_item
        })
        save_data(st.session_state.records)
        st.rerun()

    st.markdown("---")
    col_undo, col_skip, col_reset = st.columns(3)
    
    if col_undo.button("↩️ 취소", use_container_width=True):
        popped = st.session_state.records.pop()
        save_data(st.session_state.records)
        st.toast(f"{popped['round']}회차 취소됨")
        st.rerun()

    if col_skip.button("⏩ 패스", use_container_width=True):
        st.session_state.records.append({
            'date': curr_date,
            'round': next_round,
            'result': "우사"
        })
        st.toast(f"{next_round}회차 패스")
        st.rerun()

    if col_reset.button("🧹 초기화", use_container_width=True):
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔍 최근 5개 흐름")
    recent_5 = [f"{r['round']}회:{r['result']}" for r in records[-5:]]
    st.write(" ➔ ".join(recent_5))
