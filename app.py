import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 A/B 듀얼 분석기", page_icon="📊", layout="centered")

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

ALL_COMBOS = ['우사', '우삼', '좌사', '좌삼']

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
}

ITEM_FULL_MAP = {
    '우사': '우사짝',
    '우삼': '우삼홀',
    '좌사': '좌사홀',
    '좌삼': '좌삼짝'
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

# 🅰️ [방식 A] 3구멍 독립 스캔 엔진
def calculate_standard_pattern_score(stream, val1, val2):
    n = len(stream)
    if n < 4:
        return {val1: 50.0, val2: 50.0}

    score1, score2 = 50.0, 50.0

    if stream[-1] == stream[-2] == stream[-3]:
        rec = stream[-1]
        streak = 3
        for idx in range(4, min(n + 1, 10)):
            if stream[-idx] == rec: streak += 1
            else: break
        bonus = min(15.0 + (streak * 3.5), 35.0)
        if rec == val1: score1 += bonus
        else: score2 += bonus

    elif stream[-1] != stream[-2] and stream[-2] != stream[-3]:
        streak = 3
        for idx in range(4, min(n + 1, 10)):
            if stream[-idx + 1] != stream[-idx]: streak += 1
            else: break
        opp_val = val2 if stream[-1] == val1 else val1
        bonus = min(12.0 + (streak * 2.5), 30.0)
        if opp_val == val1: score1 += bonus
        else: score2 += bonus

    elif n >= 4 and stream[-2] == stream[-3] and stream[-1] != stream[-2]:
        same_val = stream[-1]
        if same_val == val1: score1 += 18.0
        else: score2 += 18.0

    tot = score1 + score2
    return {val1: (score1 / tot) * 100.0, val2: (score2 / tot) * 100.0}

def analyze_method_A(records):
    valid_records = [r for r in records if r['result'] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid_records) < 4: return None

    s_stream = [ITEM_MAP[r['result']][0] for r in valid_records]
    s_scores = calculate_standard_pattern_score(s_stream, '우', '좌')

    l_stream = [ITEM_MAP[r['result']][1] for r in valid_records]
    l_scores = calculate_standard_pattern_score(l_stream, '사', '삼')

    o_stream = [ITEM_MAP[r['result']][2] for r in valid_records]
    o_scores = calculate_standard_pattern_score(o_stream, '짝', '홀')

    combo_probs = {}
    for combo in ALL_COMBOS:
        s_val, l_val, o_val = ITEM_MAP[combo]
        p_s = s_scores[s_val] / 100.0
        p_l = l_scores[l_val] / 100.0
        p_o = o_scores[o_val] / 100.0
        combo_probs[combo] = p_s * p_l * p_o

    tot_p = sum(combo_probs.values())
    final_probs = {c: (p / tot_p) * 100.0 for c, p in combo_probs.items()}
    sorted_combos = sorted(final_probs.items(), key=lambda x: x[1], reverse=True)

    return sorted_combos[0][0], sorted_combos[0][1]

# 🅱️ [방식 B] 3원화 없이 조합 통분석 엔진
def analyze_method_B(records):
    valid_records = [r for r in records if r['result'] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid_records) < 4: return None

    combo_stream = [r['result'] for r in valid_records]

    scores = {c: 25.0 for c in ALL_COMBOS}

    # 1. 조합 직접 연속성
    if combo_stream[-1] == combo_stream[-2]:
        scores[combo_stream[-1]] += 20.0

    # 2. 조합 교차 패턴
    elif combo_stream[-1] != combo_stream[-2] and combo_stream[-2] == combo_stream[-3]:
        scores[combo_stream[-1]] += 15.0

    # 3. 미출현 갭 가산점
    last_seen = {c: 999 for c in ALL_COMBOS}
    for idx, c in enumerate(reversed(combo_stream)):
        if last_seen[c] == 999:
            last_seen[c] = idx

    for c in ALL_COMBOS:
        if 2 <= last_seen[c] <= 5:
            scores[c] += 10.0

    tot_p = sum(scores.values())
    final_probs = {c: (p / tot_p) * 100.0 for c, p in scores.items()}
    sorted_combos = sorted(final_probs.items(), key=lambda x: x[1], reverse=True)

    return sorted_combos[0][0], sorted_combos[0][1]

# 승패 및 승률 집계 함수 (상세)
def calculate_combo_stats(records, target_date=None, limit_recent=None):
    if limit_recent: eval_records = records[-limit_recent:]
    else: eval_records = records

    n = len(eval_records)
    if n < 5: return None

    tot_count = 0
    a_win, b_win = 0, 0

    for i in range(4, n):
        act = eval_records[i]['result']
        if act not in ALL_COMBOS: continue
        if target_date and eval_records[i]['date'] != target_date: continue

        past_sub = eval_records[:i]
        p_a = analyze_method_A(past_sub)
        p_b = analyze_method_B(past_sub)

        if p_a and p_b:
            tot_count += 1
            if p_a[0] == act: a_win += 1
            if p_b[0] == act: b_win += 1

    if tot_count == 0: return None

    return {
        'total': tot_count,
        'a_win': a_win, 'a_lose': tot_count - a_win, 'a_rate': (a_win / tot_count) * 100.0,
        'b_win': b_win, 'b_lose': tot_count - b_win, 'b_rate': (b_win / tot_count) * 100.0
    }

# 백업 상태 관리
if "records" not in st.session_state: st.session_state.records = load_data()
if "history_stack" not in st.session_state: st.session_state.history_stack = []
if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

records = st.session_state.records

# 1. 대량 입력 모드
if st.session_state.show_bulk:
    st.markdown("**📋 과거 데이터 한 번에 복사/붙여넣기**")
    b_date = st.date_input("입력할 날짜 선택", datetime.now())
    b_start_rd = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    raw_text = st.text_area("텍스트 붙여넣기", height=180, placeholder="예시:\n우사 우삼 좌사 좌삼 우사")
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("📥 데이터 일괄 추가", use_container_width=True):
        found_items = re.findall(r'우사|우삼|좌사|좌삼', raw_text)
        if found_items:
            push_backup()
            curr_rd = int(b_start_rd)
            dt_str = b_date.strftime("%Y-%m-%d")
            for item in found_items:
                st.session_state.records.append({'date': dt_str, 'round': curr_rd, 'result': item})
                curr_rd += 1
                if curr_rd > 288: curr_rd = 1
            save_data(st.session_state.records)
            st.toast(f"총 {len(found_items)}개 일괄 등록 완료!")
            st.session_state.show_bulk = False
            st.rerun()

    if col_b2.button("❌ 취소", use_container_width=True):
        st.session_state.show_bulk = False
        st.rerun()

# 2. 최초 데이터 없을 때
elif not records:
    st.markdown("**⚙️ 최초 환경 설정**")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    
    col1, col2, col3, col4 = st.columns(4)
    sel = None
    if col1.button("우삼"): sel = "우삼"
    elif col2.button("우사"): sel = "우사"
    elif col3.button("좌삼"): sel = "좌삼"
    elif col4.button("좌사"): sel = "좌사"

    if sel:
        push_backup()
        st.session_state.records.append({'date': init_date.strftime("%Y-%m-%d"), 'round': int(init_round), 'result': sel})
        save_data(st.session_state.records)
        st.rerun()

# 3. 메인 분석 화면
else:
    last_rec = records[-1]
    curr_date = last_rec['date']
    next_round = last_rec['round'] + 1
    if next_round > 288: next_round = 1

    st.markdown(f"**날짜 : {curr_date} / 다음회차 : {next_round}회차**")
    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    # 1. 전체 누적 통계
    all_stat = calculate_combo_stats(records)
    st.markdown("**전체 누적 통계 (패스 회차 제외)**")
    if all_stat:
        st.markdown(f"🅰️ **[현재] 3원화 분석 적중률 : {all_stat['a_win']}승 {all_stat['a_lose']}패 (승률 {all_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **[신규] 조합통합 분석 적중률 : {all_stat['b_win']}승 {all_stat['b_lose']}패 (승률 {all_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 2. 최근 3000개 누적 통계
    recent_stat = calculate_combo_stats(records, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적 통계 (패스 회차 제외)**")
    if recent_stat:
        st.markdown(f"🅰️ **[현재] 3원화 분석 적중률 : {recent_stat['a_win']}승 {recent_stat['a_lose']}패 (승률 {recent_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **[신규] 조합통합 분석 적중률 : {recent_stat['b_win']}승 {recent_stat['b_lose']}패 (승률 {recent_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 3. 오늘 누적 통계
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_combo_stats(records, target_date=curr_date)
    st.markdown(f"**오늘 누적 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"🅰️ **[현재] 3원화 분석 적중률 : {today_stat['a_win']}승 {today_stat['a_lose']}패 (승률 {today_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **[신규] 조합통합 분석 적중률 : {today_stat['b_win']}승 {today_stat['b_lose']}패 (승률 {today_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 4. 직전 회차 결과
    if len(records) >= 5:
        prev_sub = records[:-1]
        prev_a = analyze_method_A(prev_sub)
        prev_b = analyze_method_B(prev_sub)
        prev_actual = last_rec['result']
        
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)** ➔ **통계 제외**")
        elif prev_a and prev_b:
            res_a_str = "적중 🎯" if prev_a[0] == prev_actual else "실패"
            res_b_str = "적중 🎯" if prev_b[0] == prev_actual else "실패"
            
            st.markdown(f"실제 결과 : **{prev_actual} ({ITEM_FULL_MAP[prev_actual]})**")
            st.markdown(f"🅰️ [A방식 추천] : **{prev_a[0]}** ➔ **{res_a_str}**")
            st.markdown(f"🅱️ [B방식 추천] : **{prev_b[0]}** ➔ **{res_b_str}**")
        else:
            st.markdown(f"실제 결과 : **{prev_actual}**")

    st.markdown("---")

    # 5. 이번회차 듀얼 추천 표출
    res_a = analyze_method_A(records)
    res_b = analyze_method_B(records)

    if res_a and res_b:
        st.markdown(f"**이번회차 A/B 듀얼 추천 ( {next_round}회차 )**")
        st.markdown(f"🅰️ **[A: 현재 3원화 추천] : {res_a[0]} ({ITEM_FULL_MAP[res_a[0]]})** `확률 {res_a[1]:.1f}%`")
        st.markdown(f"🅱️ **[B: 조합통합 추천] : {res_b[0]} ({ITEM_FULL_MAP[res_b[0]]})** `확률 {res_b[1]:.1f}%`")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")
    st.markdown("**결과 입력**")

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
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': input_val})
        save_data(st.session_state.records)
        st.rerun()

    st.markdown("---")

    m1, m2, m3, m4 = st.columns(4)
    if m1.button("패스", use_container_width=True):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        save_data(st.session_state.records)
        st.toast(f"{next_round}회차 패스")
        st.rerun()

    if m2.button("직전취소", use_container_width=True):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            save_data(st.session_state.records)
            st.rerun()

    if m3.button("초기화", use_container_width=True):
        push_backup()
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        st.rerun()

    if m4.button("되돌리기", use_container_width=True):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.rerun()

    st.markdown("---")

    # 6. 당일 세부 결과 전체 리스트 표출
    st.markdown("**오늘 세부 결과 (A/B 추천 적중 여부 전체)**")
    if len(records) >= 5:
        rows = []
        today_indices = [idx for idx, r in enumerate(records) if r['date'] == curr_date]
        
        for i in reversed(today_indices):
            if i < 4: continue
            p_sub = records[:i]
            pa = analyze_method_A(p_sub)
            pb = analyze_method_B(p_sub)
            act_item = records[i]['result']
            rd_num = records[i]['round']
            
            if act_item == "PASS":
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": "패스 (PASS)",
                    "A방식 추천": "-",
                    "A 적중": "-",
                    "B방식 추천": "-",
                    "B 적중": "-"
                })
            elif pa and pb:
                a_ok = "성공 🎯" if pa[0] == act_item else "실패"
                b_ok = "성공 🎯" if pb[0] == act_item else "실패"
                
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": f"{act_item} ({ITEM_FULL_MAP[act_item]})",
                    "A방식 추천": f"{pa[0]} ({ITEM_FULL_MAP[pa[0]]})",
                    "A 적중": a_ok,
                    "B방식 추천": f"{pb[0]} ({ITEM_FULL_MAP[pb[0]]})",
                    "B 적중": b_ok
                })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
