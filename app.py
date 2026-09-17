import os
import re
import copy
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client, Client

st.set_page_config(page_title="키노사다리 초고속 지울픽 전용 분석기", page_icon="⚡", layout="centered")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

st.markdown("""
<style>
    html, body { overscroll-behavior-y: contain !important; }
    .stApp { overscroll-behavior-y: none !important; }
    .block-container { padding: 0.3rem 0.3rem 80px 0.3rem !important; }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.8rem !important; line-height: 1.3 !important; }

    div[data-testid="stSegmentedControl"] { width: 100% !important; }
    div[data-testid="stSegmentedControl"] > div {
        display: flex !important; flex-direction: row !important;
        width: 100% !important; gap: 2px !important;
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1 1 25% !important; width: 25% !important;
        max-width: 25% !important; min-width: 0px !important;
        padding: 0.3rem 0rem !important; font-size: 0.85rem !important;
        font-weight: bold !important; height: 38px !important;
    }

    .ctrl-container .stButton { width: 100% !important; margin-bottom: 0.2rem !important; }
    .ctrl-container .stButton>button {
        padding: 0.5rem 0.1rem !important; font-size: 0.88rem !important;
        font-weight: bold !important; width: 100% !important;
    }

    .ctrl-container div[data-testid="stDownloadButton"] { width: 100% !important; margin-bottom: 0.2rem !important; }
    .ctrl-container div[data-testid="stDownloadButton"]>button {
        padding: 0.5rem 0.1rem !important; font-size: 0.88rem !important;
        font-weight: bold !important; width: 100% !important;
        background-color: #28a745 !important; color: white !important; border: none !important;
    }

    hr { margin: 0.3rem 0 !important; border-color: #ddd !important; }
</style>
""", unsafe_allow_html=True)

MAX_DATA_SIZE = 2000
ALL_COMBOS = ['우삼', '우사', '좌삼', '좌사']

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
    if not supabase: return []
    try:
        all_records = []
        start = 0
        step = 1000
        while start < MAX_DATA_SIZE:
            res = supabase.table("ladder_records").select("date, round, result, id").order("id", desc=True).range(start, start + step - 1).execute()
            if res and res.data:
                all_records.extend(res.data)
                if len(res.data) < step: break
                start += step
            else: break
        if all_records:
            sorted_records = sorted(all_records, key=lambda x: int(x['id']))
            return [{'date': str(r['date']).strip(), 'round': int(r['round']), 'result': str(r['result']).strip()} for r in sorted_records]
        return []
    except Exception: return []

def sync_all_records_db(records):
    if not supabase: return
    try:
        trimmed_records = records[-MAX_DATA_SIZE:] if records else []
        fetch_ids = supabase.table("ladder_records").select("id").execute()
        if fetch_ids and fetch_ids.data:
            id_list = [r['id'] for r in fetch_ids.data]
            for i in range(0, len(id_list), 200):
                supabase.table("ladder_records").delete().in_("id", id_list[i:i + 200]).execute()

        if trimmed_records:
            bulk_list = [{"date": str(r['date']).strip(), "round": int(r['round']), "result": str(r['result']).strip()} for r in trimmed_records]
            for i in range(0, len(bulk_list), 100):
                supabase.table("ladder_records").insert(bulk_list[i:i + 100]).execute()
    except Exception: pass

def add_single_record_db(date_str, round_num, result_str):
    if supabase:
        try:
            supabase.table("ladder_records").insert({"date": str(date_str), "round": int(round_num), "result": str(result_str)}).execute()
        except Exception: pass

def delete_last_record_db():
    if supabase:
        try:
            res = supabase.table("ladder_records").select("id").order("id", desc=True).limit(1).execute()
            if res and res.data:
                supabase.table("ladder_records").delete().eq("id", res.data[0]['id']).execute()
        except Exception: pass

@st.cache_data(show_spinner=False)
def get_historical_pattern_weights(records_tuple, pattern_len=3):
    results = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(results) <= pattern_len:
        return {c: 25.0 for c in ALL_COMBOS}

    search_arr = np.array(results[-500:])
    target_pattern = search_arr[-pattern_len:]
    counts = {c: 0 for c in ALL_COMBOS}
    total_matches = 0

    for idx in range(len(search_arr) - pattern_len):
        if np.array_equal(search_arr[idx:idx + pattern_len], target_pattern):
            next_val = search_arr[idx + pattern_len]
            if next_val in counts:
                counts[next_val] += 1
                total_matches += 1

    if total_matches == 0:
        return {c: 25.0 for c in ALL_COMBOS}

    return {c: (counts[c] / total_matches) * 100.0 for c in ALL_COMBOS}

def calculate_score_A_engine(stream, val1, val2):
    n = len(stream)
    if n < 2: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0
    
    if stream[-1] == stream[-2]:
        rec = stream[-1]
        streak = 2
        for idx in range(3, min(n + 1, 10)):
            if stream[-idx] == rec: streak += 1
            else: break
        bonus = 15.0 + (streak * 4.5)
        if rec == val1: s1 += bonus
        else: s2 += bonus
        
    if stream[-1] != stream[-2]:
        streak = 2
        for idx in range(3, min(n + 1, 10)):
            if stream[-idx + 1] != stream[-idx]: streak += 1
            else: break
        opp_val = val2 if stream[-1] == val1 else val1
        bonus = 14.0 + (streak * 4.0)
        if opp_val == val1: s1 += bonus
        else: s2 += bonus

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_A_engine_tuple(records_tuple, include_history=False):
    valid = [r for r in records_tuple[-30:] if r[2] in ALL_COMBOS]
    if len(valid) < 2: return None
    s_s = calculate_score_A_engine([ITEM_MAP[r[2]][0] for r in valid], '우', '좌')
    l_s = calculate_score_A_engine([ITEM_MAP[r[2]][1] for r in valid], '사', '삼')
    o_s = calculate_score_A_engine([ITEM_MAP[r[2]][2] for r in valid], '짝', '홀')
    
    base_probs = {c: (s_s[ITEM_MAP[c][0]]/100.0)*(l_s[ITEM_MAP[c][1]]/100.0)*(o_s[ITEM_MAP[c][2]]/100.0) for c in ALL_COMBOS}
    tot_base = sum(base_probs.values())
    norm_base = {c: (p/tot_base)*100.0 for c, p in base_probs.items()}

    if include_history:
        hist_weights = get_historical_pattern_weights(records_tuple, pattern_len=3)
        final_probs = {c: (norm_base[c] * 0.7) + (hist_weights[c] * 0.3) for c in ALL_COMBOS}
    else:
        final_probs = norm_base

    tot_final = sum(final_probs.values())
    norm_probs = {c: (p/tot_final)*100.0 for c, p in final_probs.items()}
    sorted_combos = sorted(norm_probs.items(), key=lambda x: x[1], reverse=True)

    return {'top': sorted_combos[0][0], 'top_prob': sorted_combos[0][1], 'worst': sorted_combos[-1][0], 'worst_prob': sorted_combos[-1][1], 'probs': norm_probs}

def calculate_score_B_engine(stream, val1, val2):
    n = len(stream)
    if n < 3: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0
    
    if n >= 4 and stream[-2] == stream[-3] and stream[-1] != stream[-2]:
        target = stream[-1]
        if target == val1: s1 += 22.0
        else: s2 += 22.0
    elif n >= 4 and stream[-1] == stream[-2] and stream[-2] != stream[-3]:
        opp_target = val2 if stream[-1] == val1 else val1
        if opp_target == val1: s1 += 24.0
        else: s2 += 24.0
        
    if n >= 5 and stream[-1] == stream[-2] and stream[-2] == stream[-3]:
        opp_target = val2 if stream[-1] == val1 else val1
        if opp_target == val1: s1 += 20.0
        else: s2 += 20.0

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_B_engine_tuple(records_tuple, include_history=False):
    valid = [r for r in records_tuple[-30:] if r[2] in ALL_COMBOS]
    if len(valid) < 3: return None
    s_s = calculate_score_B_engine([ITEM_MAP[r[2]][0] for r in valid], '우', '좌')
    l_s = calculate_score_B_engine([ITEM_MAP[r[2]][1] for r in valid], '사', '삼')
    o_s = calculate_score_B_engine([ITEM_MAP[r[2]][2] for r in valid], '짝', '홀')

    base_probs = {c: (s_s[ITEM_MAP[c][0]]/100.0)*(l_s[ITEM_MAP[c][1]]/100.0)*(o_s[ITEM_MAP[c][2]]/100.0) for c in ALL_COMBOS}
    tot_base = sum(base_probs.values())
    norm_base = {c: (p/tot_base)*100.0 for c, p in base_probs.items()}

    if include_history:
        hist_weights = get_historical_pattern_weights(records_tuple, pattern_len=3)
        final_probs = {c: (norm_base[c] * 0.7) + (hist_weights[c] * 0.3) for c in ALL_COMBOS}
    else:
        final_probs = norm_base

    tot_final = sum(final_probs.values())
    norm_probs = {c: (p/tot_final)*100.0 for c, p in final_probs.items()}
    sorted_combos = sorted(norm_probs.items(), key=lambda x: x[1], reverse=True)

    return {'top': sorted_combos[0][0], 'top_prob': sorted_combos[0][1], 'worst': sorted_combos[-1][0], 'worst_prob': sorted_combos[-1][1], 'probs': norm_probs}

def detect_current_pattern_mode(records_tuple):
    valid = [r[2] for r in records_tuple[-6:] if r[2] in ALL_COMBOS]
    if len(valid) < 4: return 'A'
    
    streak_count = 0
    for i in range(len(valid) - 1):
        if valid[i] == valid[i+1]: streak_count += 1
        
    if streak_count >= 3: return 'A'
    return 'B'

# 🎯 [단순 고정 알고리즘] 재귀를 없애 인덱스 꼬임을 100% 원천 차단
def calculate_combined_avoid_pick_simple(records_tuple, res_a, res_b, prev_failed=False):
    if not res_a or not res_b: return None
    
    mode = detect_current_pattern_mode(records_tuple)

    if not prev_failed:
        if mode == 'A':
            target_worst = res_a['worst']
            info = "A(장줄) 선택"
            if target_worst == res_b['top']:
                target_worst = res_b['worst']
                info = "B(박스) 방어선택"
        else:
            target_worst = res_b['worst']
            info = "B(박스) 선택"
            if target_worst == res_a['top']:
                target_worst = res_a['worst']
                info = "A(장줄) 방어선택"
    else:
        if mode == 'A':
            target_worst = res_b['worst']
            info = "⚡실패반전 B선택"
        else:
            target_worst = res_a['worst']
            info = "⚡실패반전 A선택"
            
    return {
        'worst': target_worst,
        'mode_info': info
    }

# 📊 통계 및 순차 계산 로직 (인덱스 꼬임 방지 단일 루프)
@st.cache_data(show_spinner=False)
def calculate_all_history_and_stats(records_tuple, target_date=None):
    n = len(records_tuple)
    if n < 4: return None, None
    
    tot_a, tot_b, tot_comb = 0, 0, 0
    a_avoid_win, b_avoid_win, comb_avoid_win = 0, 0, 0

    comb_avoid_win_streak, max_comb_avoid_win_streak = 0, 0
    comb_avoid_lose_streak, max_comb_avoid_lose_streak = 0, 0

    prev_comb_failed = False
    history_picks = {}  # {인덱스: 지울픽 결과객체}

    for i in range(3, n):
        act = records_tuple[i][2]
        past_sub = records_tuple[:i]
        
        res_a = analyze_A_engine_tuple(past_sub, include_history=False)
        res_b = analyze_B_engine_tuple(past_sub, include_history=False)
        
        # 순차적으로 직전 실패 여부를 전달하여 재귀 계산을 원천 배제
        res_comb = calculate_combined_avoid_pick_simple(past_sub, res_a, res_b, prev_failed=prev_comb_failed)
        history_picks[i] = res_comb

        if act not in ALL_COMBOS: continue

        # 통계집계
        if not target_date or records_tuple[i][0] == target_date:
            if res_a:
                tot_a += 1
                if res_a['worst'] != act: a_avoid_win += 1
            if res_b:
                tot_b += 1
                if res_b['worst'] != act: b_avoid_win += 1
                
            if res_comb:
                tot_comb += 1
                if res_comb['worst'] != act:
                    comb_avoid_win += 1
                    comb_avoid_win_streak += 1
                    comb_avoid_lose_streak = 0
                    if comb_avoid_win_streak > max_comb_avoid_win_streak: max_comb_avoid_win_streak = comb_avoid_win_streak
                else:
                    comb_avoid_lose_streak += 1
                    comb_avoid_win_streak = 0
                    if comb_avoid_lose_streak > max_comb_avoid_lose_streak: max_comb_avoid_lose_streak = comb_avoid_lose_streak

        # 다음 회차 전달용 실패 여부 갱신
        if res_comb and act in ALL_COMBOS:
            prev_comb_failed = (res_comb['worst'] == act)

    stats = {
        'tot_a': tot_a, 'a_avoid_win': a_avoid_win, 'a_avoid_lose': tot_a - a_avoid_win, 'a_avoid_rate': (a_avoid_win/tot_a*100.0) if tot_a > 0 else 0.0,
        'tot_b': tot_b, 'b_avoid_win': b_avoid_win, 'b_avoid_lose': tot_b - b_avoid_win, 'b_avoid_rate': (b_avoid_win/tot_b*100.0) if tot_b > 0 else 0.0,
        'tot_comb': tot_comb, 
        'comb_avoid_win': comb_avoid_win, 'comb_avoid_lose': tot_comb - comb_avoid_win, 
        'comb_avoid_rate': (comb_avoid_win/tot_comb*100.0) if tot_comb > 0 else 0.0,
        'max_comb_avoid_win_streak': max_comb_avoid_win_streak, 
        'max_comb_avoid_lose_streak': max_comb_avoid_lose_streak,
        'last_failed': prev_comb_failed
    }
    
    return stats, history_picks

if "records" not in st.session_state:
    st.session_state.records = load_data()

if "history_stack" not in st.session_state: st.session_state.history_stack = []
if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

records = st.session_state.records
records_tuple = tuple((r['date'], r['round'], r['result']) for r in records)

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
            curr_rd, curr_dt = int(b_start_rd), b_date
            for item in found_items:
                st.session_state.records.append({'date': curr_dt.strftime("%Y-%m-%d"), 'round': curr_rd, 'result': item})
                curr_rd += 1
                if curr_rd > 288:
                    curr_rd = 1
                    curr_dt = curr_dt + timedelta(days=1)
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
            st.cache_data.clear()
            st.toast(f"총 {len(found_items)}개 일괄 등록 완료!")
            st.session_state.show_bulk = False
            st.rerun()
    if col_b2.button("❌ 취소", use_container_width=True):
        st.session_state.show_bulk = False
        st.rerun()

elif not records:
    st.markdown("**⚙️ 최초 환경 설정**")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    sel = st.segmented_control(label="첫 결과 선택", options=ALL_COMBOS, selection_mode="single", label_visibility="collapsed", key="init_seg_ctrl")
    if sel:
        push_backup()
        dt_s, rd_n = init_date.strftime("%Y-%m-%d"), int(init_round)
        st.session_state.records.append({'date': dt_s, 'round': rd_n, 'result': sel})
        add_single_record_db(dt_s, rd_n, sel)
        st.cache_data.clear()
        st.rerun()

else:
    last_rec = records[-1]
    last_dt_obj = datetime.strptime(last_rec['date'], "%Y-%m-%d")
    if last_rec['round'] >= 288:
        next_round = 1
        curr_date = (last_dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        next_round = last_rec['round'] + 1
        curr_date = last_rec['date']

    st.markdown(f"**날짜 : {curr_date} / 다음회차 : {next_round}회차**")
    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    recent_stat, history_picks = calculate_all_history_and_stats(records_tuple)
    recent_cnt = len(records)
    st.markdown(f"**누적 지울픽 통계 (최근 {recent_cnt}개 기준 / 패스 회차 제외)**")
    if recent_stat:
        st.markdown(f"⛔ **종합 지울픽 성공률 : {recent_stat['comb_avoid_win']}승 {recent_stat['comb_avoid_lose']}패 (성공률 {recent_stat['comb_avoid_rate']:.1f}%)**")
        st.markdown(f"🅰️ A 지울픽 성공률 : {recent_stat['a_avoid_win']}승 {recent_stat['a_avoid_lose']}패 ({recent_stat['a_avoid_rate']:.1f}%)")
        st.markdown(f"🅱️ B 지울픽 성공률 : {recent_stat['b_avoid_win']}승 {recent_stat['b_avoid_lose']}패 ({recent_stat['b_avoid_rate']:.1f}%)")

    st.markdown("---")

    try: dt_obj = datetime.strptime(curr_date, "%Y-%m-%d"); w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception: w_str = ""
    today_stat, _ = calculate_all_history_and_stats(records_tuple, target_date=curr_date)
    st.markdown(f"**오늘 누적 지울픽 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"⛔ **종합 지울픽 성공률 : {today_stat['comb_avoid_win']}승 {today_stat['comb_avoid_lose']}패 (성공률 {today_stat['comb_avoid_rate']:.1f}%)**")
        st.markdown(f"   🛡️ **종합 지울픽 오늘 성적 : 최다 {today_stat['max_comb_avoid_win_streak']}연속 성공 / 최다 {today_stat['max_comb_avoid_lose_streak']}연속 나와버림**")
        st.markdown(f"🅰️ A 지울픽 성공률 : {today_stat['a_avoid_win']}승 {today_stat['a_avoid_lose']}패 ({today_stat['a_avoid_rate']:.1f}%)")
        st.markdown(f"🅱️ B 지울픽 성공률 : {today_stat['b_avoid_win']}승 {today_stat['b_avoid_lose']}패 ({today_stat['b_avoid_rate']:.1f}%)")

    st.markdown("---")

    # 📌 직전회차 검증: 역사적 시점 기록(history_picks) 그대로 100% 매칭 표출
    if len(records_tuple) >= 4 and history_picks:
        last_idx = len(records_tuple) - 1
        prev_comb = history_picks.get(last_idx)
        prev_actual = last_rec['result']
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)** ➔ **통계 제외**")
        else:
            act_full = ITEM_FULL_MAP.get(prev_actual, prev_actual)
            comb_avoid_ok = "안나옴 성공 🎯" if prev_comb and prev_comb['worst'] != prev_actual else "나와버림 ❌"
            st.markdown(f"실제 결과 : **{prev_actual} ({act_full})**")
            if prev_comb:
                st.markdown(f"⛔ **종합 지울픽 ({prev_comb['worst']}) ➔ {comb_avoid_ok}**")

    st.markdown("---")

    curr_a_res = analyze_A_engine_tuple(records_tuple, include_history=True)
    curr_b_res = analyze_B_engine_tuple(records_tuple, include_history=True)
    
    # 이번 회차 지울픽 연산 (직전 회차의 실제 실패 여부를 전달)
    last_failed_status = recent_stat['last_failed'] if recent_stat else False
    combined_pick = calculate_combined_avoid_pick_simple(records_tuple, curr_a_res, curr_b_res, prev_failed=last_failed_status)

    st.markdown(f"**이번회차 지울픽 분석 ( {next_round}회차 )**")
    
    if combined_pick:
        st.markdown(f"⛔ **[종합 지울픽] 제외: `{combined_pick['worst']}` ({ITEM_FULL_MAP[combined_pick['worst']]})** `[{combined_pick['mode_info']}]`")
        st.markdown(" ")

    if curr_a_res:
        st.markdown(f"🅰️ **[A 지울픽] 제외: `{curr_a_res['worst']}` ({ITEM_FULL_MAP[curr_a_res['worst']]})** `확률 {curr_a_res['worst_prob']:.1f}%`")
    st.markdown(" ")
    if curr_b_res:
        st.markdown(f"🅱️ **[B 지울픽] 제외: `{curr_b_res['worst']}` ({ITEM_FULL_MAP[curr_b_res['worst']]})** `확률 {curr_b_res['worst_prob']:.1f}%`")

    st.markdown("---")
    st.markdown("**결과 입력**")

    input_val = st.segmented_control(
        label="결과 선택",
        options=ALL_COMBOS,
        selection_mode="single",
        label_visibility="collapsed",
        key=f"seg_ctrl_{len(records)}_{records[-1]['round'] if records else 0}"
    )

    if input_val:
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': input_val})
        if len(st.session_state.records) > MAX_DATA_SIZE:
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
        else: add_single_record_db(curr_date, next_round, input_val)
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

    st.markdown('<div class="ctrl-container">', unsafe_allow_html=True)
    if st.button("패스", use_container_width=True, key="btn_pass"):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        if len(st.session_state.records) > MAX_DATA_SIZE:
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
        else: add_single_record_db(curr_date, next_round, "PASS")
        st.toast(f"{next_round}회차 패스")
        st.cache_data.clear()
        st.rerun()

    if st.button("직전취소", use_container_width=True, key="btn_cancel"):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            delete_last_record_db()
            st.cache_data.clear()
            st.rerun()

    if st.button("초기화", use_container_width=True, key="btn_reset"):
        push_backup()
        st.session_state.records = []
        st.session_state.history_stack = []
        sync_all_records_db([])
        st.cache_data.clear()
        st.rerun()

    if st.button("되돌리기", use_container_width=True, key="btn_undo"):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            sync_all_records_db(st.session_state.records)
            st.cache_data.clear()
            st.rerun()

    export_lines = [f"{r['date']}|{r['round']}|{r['result']}" for r in records]
    export_bytes = "\n".join(export_lines).encode("utf-8-sig")
    st.download_button(label="📥 현재 누적 데이터 TXT 다운로드 (백업)", data=export_bytes, file_name=f"ladder_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", mime="text/plain", use_container_width=True, key="btn_download")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("**오늘 세부 결과 (지울픽 적중 리스트)**")
    if len(records_tuple) >= 4 and history_picks:
        rows = []
        today_indices = [idx for idx, r in enumerate(records_tuple) if r[0] == curr_date]
        for i in reversed(today_indices):
            if i < 3: continue
            p_sub = records_tuple[:i]
            res_a_prev, res_b_prev = analyze_A_engine_tuple(p_sub, include_history=False), analyze_B_engine_tuple(p_sub, include_history=False)
            res_comb_prev = history_picks.get(i)
            act_item, rd_num = records_tuple[i][2], records_tuple[i][1]
            if act_item == "PASS": continue
            act_full = ITEM_FULL_MAP.get(act_item, act_item)
            
            comb_avoid_match = "성공 🎯" if res_comb_prev and res_comb_prev['worst'] != act_item else "나와버림 ❌"
            a_avoid_match = "성공 🎯" if res_a_prev and res_a_prev['worst'] != act_item else "나와버림 ❌"
            b_avoid_match = "성공 🎯" if res_b_prev and res_b_prev['worst'] != act_item else "나와버림 ❌"
            
            rows.append({
                "회차": f"{rd_num}회", "실제 결과": f"{act_item} ({act_full})",
                "종합 지울픽": f"{res_comb_prev['worst']}" if res_comb_prev else "-", 
                "종합 결과": comb_avoid_match,
                "A 지울픽": f"{res_a_prev['worst']}" if res_a_prev else "-",
                "A 결과": a_avoid_match,
                "B 지울픽": f"{res_b_prev['worst']}" if res_b_prev else "-",
                "B 결과": b_avoid_match
            })
        if rows: st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else: st.markdown("오늘 유효한 회차가 없습니다.")
