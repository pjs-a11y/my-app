import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 A/B 속성 분석기", page_icon="📊", layout="centered")

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

# 공통 속성(교집합) 추출 함수 (3개 일치 시 패스 표출)
def extract_common_attributes(combo1, combo2):
    s1, l1, o1 = ITEM_MAP[combo1]
    s2, l2, o2 = ITEM_MAP[combo2]
    
    commons = []
    if s1 == s2: commons.append(s1)
    if l1 == l2: commons.append(l1)
    if o1 == o2: commons.append(o1)
    
    # 🎯 3개 속성이 모두 같으면 '패스' 텍스트 표출
    if len(commons) == 3:
        return "패스"
    elif len(commons) > 0:
        return "/".join(commons)
    return "대칭 (없음)"

# 🅰️ [A 엔진: 장줄 & 퐁당 중심]
def calculate_score_A_3way(stream, val1, val2):
    n = len(stream)
    if n < 3: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0

    if stream[-1] == stream[-2] == stream[-3]:
        rec = stream[-1]
        if rec == val1: s1 += 30.0
        else: s2 += 30.0
    elif stream[-1] != stream[-2] and stream[-2] != stream[-3]:
        opp_val = val2 if stream[-1] == val1 else val1
        if opp_val == val1: s1 += 25.0
        else: s2 += 25.0

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_A_engine(records):
    valid = [r for r in records if r['result'] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid) < 4: return "분석중"

    s_s = calculate_score_A_3way([ITEM_MAP[r['result']][0] for r in valid], '우', '좌')
    l_s = calculate_score_A_3way([ITEM_MAP[r['result']][1] for r in valid], '사', '삼')
    o_s = calculate_score_A_3way([ITEM_MAP[r['result']][2] for r in valid], '짝', '홀')

    probs_3way = {}
    for c in ALL_COMBOS:
        s, l, o = ITEM_MAP[c]
        probs_3way[c] = (s_s[s]/100.0) * (l_s[l]/100.0) * (o_s[o]/100.0)
    top_3way = sorted(probs_3way.items(), key=lambda x: x[1], reverse=True)[0][0]

    combo_stream = [r['result'] for r in valid]
    c_scores = {c: 25.0 for c in ALL_COMBOS}
    if combo_stream[-1] == combo_stream[-2]:
        c_scores[combo_stream[-1]] += 25.0
    elif combo_stream[-1] != combo_stream[-2] and combo_stream[-2] == combo_stream[-3]:
        c_scores[combo_stream[-1]] += 20.0
    top_combo = sorted(c_scores.items(), key=lambda x: x[1], reverse=True)[0][0]

    return extract_common_attributes(top_3way, top_combo)

# 🅱️ [B 엔진: 박스 & 계단 중심]
def calculate_score_B_3way(stream, val1, val2):
    n = len(stream)
    if n < 4: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0

    if stream[-2] == stream[-3] and stream[-1] != stream[-2]:
        same_val = stream[-1]
        if same_val == val1: s1 += 28.0
        else: s2 += 28.0
    elif n >= 6 and stream[-1] == stream[-2] and stream[-2] != stream[-3] and stream[-3] == stream[-4]:
        same_val = stream[-1]
        if same_val == val1: s1 += 22.0
        else: s2 += 22.0

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_B_engine(records):
    valid = [r for r in records if r['result'] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid) < 4: return "분석중"

    s_s = calculate_score_B_3way([ITEM_MAP[r['result']][0] for r in valid], '우', '좌')
    l_s = calculate_score_B_3way([ITEM_MAP[r['result']][1] for r in valid], '사', '삼')
    o_s = calculate_score_B_3way([ITEM_MAP[r['result']][2] for r in valid], '짝', '홀')

    probs_3way = {}
    for c in ALL_COMBOS:
        s, l, o = ITEM_MAP[c]
        probs_3way[c] = (s_s[s]/100.0) * (l_s[l]/100.0) * (o_s[o]/100.0)
    top_3way = sorted(probs_3way.items(), key=lambda x: x[1], reverse=True)[0][0]

    combo_stream = [r['result'] for r in valid]
    c_scores = {c: 25.0 for c in ALL_COMBOS}
    last_seen = {c: 999 for c in ALL_COMBOS}
    for idx, c in enumerate(reversed(combo_stream)):
        if last_seen[c] == 999: last_seen[c] = idx

    for c in ALL_COMBOS:
        if 2 <= last_seen[c] <= 4: c_scores[c] += 20.0
    top_combo = sorted(c_scores.items(), key=lambda x: x[1], reverse=True)[0][0]

    return extract_common_attributes(top_3way, top_combo)

# 통계 계산 함수 (A결과 / B결과 적중률)
def calculate_ab_stats(records, target_date=None, limit_recent=None):
    if limit_recent: eval_records = records[-limit_recent:]
    else: eval_records = records

    n = len(eval_records)
    if n < 5: return None

    tot_a, tot_b = 0, 0
    a_win, b_win = 0, 0

    for i in range(4, n):
        act = eval_records[i]['result']
        if act not in ALL_COMBOS: continue
        if target_date and eval_records[i]['date'] != target_date: continue

        act_full = ITEM_FULL_MAP[act]
        past_sub = eval_records[:i]
        
        res_a = analyze_A_engine(past_sub)
        res_b = analyze_B_engine(past_sub)

        # '패스', '대칭 (없음)', '분석중'이 아닌 경우만 적중률 통계 집계
        if res_a not in ["패스", "대칭 (없음)", "분석중"]:
            tot_a += 1
            sub_attrs = res_a.split('/')
            if any(attr in act_full for attr in sub_attrs):
                a_win += 1

        if res_b not in ["패스", "대칭 (없음)", "분석중"]:
            tot_b += 1
            sub_attrs = res_b.split('/')
            if any(attr in act_full for attr in sub_attrs):
                b_win += 1

    return {
        'tot_a': tot_a, 'a_win': a_win, 'a_lose': tot_a - a_win, 'a_rate': (a_win/tot_a*100.0) if tot_a > 0 else 0.0,
        'tot_b': tot_b, 'b_win': b_win, 'b_lose': tot_b - b_win, 'b_rate': (b_win/tot_b*100.0) if tot_b > 0 else 0.0
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
    all_stat = calculate_ab_stats(records)
    st.markdown("**전체 누적 통계 (패스/대칭 회차 제외)**")
    if all_stat:
        st.markdown(f"🅰️ **A 결과 적중률 : {all_stat['a_win']}승 {all_stat['a_lose']}패 (승률 {all_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B 결과 적중률 : {all_stat['b_win']}승 {all_stat['b_lose']}패 (승률 {all_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 2. 최근 3000개 누적 통계
    recent_stat = calculate_ab_stats(records, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적 통계 (패스/대칭 회차 제외)**")
    if recent_stat:
        st.markdown(f"🅰️ **A 결과 적중률 : {recent_stat['a_win']}승 {recent_stat['a_lose']}패 (승률 {recent_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B 결과 적중률 : {recent_stat['b_win']}승 {recent_stat['b_lose']}패 (승률 {recent_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 3. 오늘 누적 통계
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_ab_stats(records, target_date=curr_date)
    st.markdown(f"**오늘 누적 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"🅰️ **A 결과 적중률 : {today_stat['a_win']}승 {today_stat['a_lose']}패 (승률 {today_stat['a_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B 결과 적중률 : {today_stat['b_win']}승 {today_stat['b_lose']}패 (승률 {today_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 4. 직전 회차 결과
    if len(records) >= 5:
        prev_sub = records[:-1]
        prev_a_res = analyze_A_engine(prev_sub)
        prev_b_res = analyze_B_engine(prev_sub)
        prev_actual = last_rec['result']
        
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)** ➔ **통계 제외**")
        else:
            act_full = ITEM_FULL_MAP[prev_actual]
            
            if prev_a_res == "패스":
                a_ok = "패스 (통계 제외)"
            elif prev_a_res != "대칭 (없음)" and any(a in act_full for a in prev_a_res.split('/')):
                a_ok = "적중 🎯"
            else:
                a_ok = "미적중"

            if prev_b_res == "패스":
                b_ok = "패스 (통계 제외)"
            elif prev_b_res != "대칭 (없음)" and any(b in act_full for b in prev_b_res.split('/')):
                b_ok = "적중 🎯"
            else:
                b_ok = "미적중"

            st.markdown(f"실제 결과 : **{prev_actual} ({act_full})**")
            st.markdown(f"🅰️ **A 결과 ({prev_a_res})** ➔ **{a_ok}**")
            st.markdown(f"🅱️ **B 결과 ({prev_b_res})** ➔ **{b_ok}**")

    st.markdown("---")

    # 5. 이번회차 A/B 결과 분석 표출
    curr_a_res = analyze_A_engine(records)
    curr_b_res = analyze_B_engine(records)

    st.markdown(f"**이번회차 A/B 결과 분석 ( {next_round}회차 )**")
    st.markdown(f"🅰️ **A 결과 : `{curr_a_res}`**")
    st.markdown(f"🅱️ **B 결과 : `{curr_b_res}`**")

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

    # 6. 당일 세부 결과 전체 표출
    st.markdown("**오늘 세부 결과 (A/B 결과 적중 리스트)**")
    if len(records) >= 5:
        rows = []
        today_indices = [idx for idx, r in enumerate(records) if r['date'] == curr_date]
        
        for i in reversed(today_indices):
            if i < 4: continue
            p_sub = records[:i]
            res_a_prev = analyze_A_engine(p_sub)
            res_b_prev = analyze_B_engine(p_sub)
            act_item = records[i]['result']
            rd_num = records[i]['round']
            
            if act_item == "PASS":
                rows.append({"회차": f"{rd_num}회", "실제 결과": "패스", "A 결과": "-", "A 적중": "-", "B 결과": "-", "B 적중": "-"})
            else:
                act_full = ITEM_FULL_MAP[act_item]
                
                if res_a_prev == "패스":
                    a_match = "패스 (통계 제외)"
                elif res_a_prev != "대칭 (없음)" and any(a in act_full for a in res_a_prev.split('/')):
                    a_match = "적중 🎯"
                else:
                    a_match = "미적중"

                if res_b_prev == "패스":
                    b_match = "패스 (통계 제외)"
                elif res_b_prev != "대칭 (없음)" and any(b in act_full for b in res_b_prev.split('/')):
                    b_match = "적중 🎯"
                else:
                    b_match = "미적중"

                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": f"{act_item} ({act_full})",
                    "A 결과": res_a_prev,
                    "A 적중": a_match,
                    "B 결과": res_b_prev,
                    "B 적중": b_match
                })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
