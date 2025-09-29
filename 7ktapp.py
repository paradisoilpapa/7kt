# velobi_auto_pre_app.py
# ヴェロビ・オート：事前購入版（完全版）
# - 試走ナシ
# - 会場×天気（良/湿＋ナイター）補正
# - 所属（ホーム）ボーナス
# - 偏差値合算 → 印付け → 固定買い目 1-2345-2345（◎軸）
# 使い方:
#   1) 下のテーブルに出走データを入力（%は0..1に直す）
#   2) 会場/路面/ナイターを選択
#   3) [計算する] を押す → 印・買い目を表示
#
# 必要ライブラリ: streamlit, pandas
#   pip install streamlit pandas

from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple
import math
import pandas as pd
import streamlit as st

# -------------------------
# 定数/設定
# -------------------------
MARKS = ["◎","〇","▲","△","×","α","β","γ"]

# 会場特性（仮値：回しながら調整）
# wet_boost: 湿路適性の重み係数（>1で湿が効きやすい場）
# st_boost : STの重み係数（>1でスタートが効きやすい場）
# night_wet_extra: ナイター時に湿が効きやすい微係数（足し込み）
VENUE = {
    "川口":  {"wet_boost": 1.20, "st_boost": 1.00, "night_wet_extra": 0.05},
    "飯塚":  {"wet_boost": 1.20, "st_boost": 1.00, "night_wet_extra": 0.05},
    "伊勢崎":{"wet_boost": 0.85, "st_boost": 1.00, "night_wet_extra": 0.00},
    "山陽":  {"wet_boost": 1.00, "st_boost": 1.10, "night_wet_extra": 0.00},
    "浜松":  {"wet_boost": 0.95, "st_boost": 1.05, "night_wet_extra": 0.00},
}

# 重み（過学習を避けて素直に）
W = {
    "handicap": 0.90,   # 前有利（小mが有利）→反転して偏差値化
    "st":       1.10,   # 平均ST（小さいほど良）
    "raceT":    1.10,   # 平均競走タイム（小さいほど良）
    "recent2":  0.90,   # 直近10走2連対率（0..1）
    "cond":     0.90,   # 良/湿適性（当日路面に合わせる: good2/wet2）
    "home":     1.00,   # 所属ボーナス（偏差値スケールで+定数加点）
}
HOME_BONUS_HEN = 2.0     # 所属=開催場 で偏差値+2点相当
DEFAULT_PARTNERS = 4      # 相手“2345”の人数（出走頭数に応じて自動で詰める）

# -------------------------
# 型定義
# -------------------------
@dataclass
class Rider:
    no: int                 # 車番（1..8）
    name: str               # 任意
    home: str               # 所属場（例: 川口/飯塚/伊勢崎/山陽/浜松）
    handicap_m: int         # 0,10,20...
    avg_st: float           # 平均ST（小さいほど良）
    avg_raceT: float        # 平均競走タイム（小さいほど良）
    top2_10: float          # 直近10走2連対率（0..1）
    good2: float            # 良路2連率（0..1）
    wet2: float             # 湿路2連率（0..1）

@dataclass
class Conditions:
    track: str              # "dry" or "wet"
    venue: str              # 会場名
    is_night: bool = False

# -------------------------
# 偏差値ユーティリティ
# -------------------------
def _z(values: List[float]) -> List[float]:
    n = len(values)
    m = sum(values)/n if n else 0.0
    var = sum((x-m)**2 for x in values)/(n-1) if n>1 else 0.0
    s = math.sqrt(var) if var>0 else 1.0
    return [(x-m)/s for x in values]

def _hensachi(values: List[float]) -> List[float]:
    return [50 + 10*z for z in _z(values)]

# -------------------------
# スコア計算
# -------------------------
def score_riders(riders: List[Rider], cond: Conditions) -> Dict[int, float]:
    venue_cfg = VENUE.get(cond.venue, {"wet_boost":1.0, "st_boost":1.0, "night_wet_extra":0.0})
    wet_mul = venue_cfg["wet_boost"]
    st_mul  = venue_cfg["st_boost"]
    if cond.is_night and cond.track.lower() == "wet":
        wet_mul += venue_cfg.get("night_wet_extra", 0.0)

    # 向き統一（大きいほど“良”）
    hand_base = [-r.handicap_m for r in riders]     # 前ほど有利に
    st_base   = [-r.avg_st      for r in riders]    # 速い（小さい）ほど良
    time_base = [-r.avg_raceT   for r in riders]    # 速い（小さい）ほど良
    recent2   = [r.top2_10      for r in riders]    # 0..1
    cond2     = [r.wet2 if cond.track.lower()=="wet" else r.good2 for r in riders]

    # 偏差値化
    H_hand = _hensachi(hand_base)
    H_st   = _hensachi(st_base)
    H_time = _hensachi(time_base)
    H_rec  = _hensachi(recent2)
    H_cond = _hensachi(cond2)

    # 会場×天気の重み
    st_weight   = W["st"]   * st_mul
    cond_weight = W["cond"] * (wet_mul if cond.track.lower()=="wet" else 1.0)

    scores: Dict[int, float] = {}
    for i, r in enumerate(riders):
        s = (
            W["handicap"] * H_hand[i] +
            st_weight      * H_st[i]   +
            W["raceT"]     * H_time[i] +
            W["recent2"]   * H_rec[i]  +
            cond_weight    * H_cond[i]
        )
        if r.home == cond.venue:
            s += W["home"] * HOME_BONUS_HEN  # 地元ボーナス（軽め）
        scores[r.no] = s
    return scores

def rank_and_marks(scores: Dict[int, float]) -> List[Tuple[str,int,float]]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(MARKS[i] if i < len(MARKS) else "", no, sc) for i,(no,sc) in enumerate(ordered)]

def recommend_fixed_bet(ranked: List[Tuple[str,int,float]], partners_want:int=DEFAULT_PARTNERS) -> Tuple[int, List[int]]:
    anchor = ranked[0][1] if ranked else None
    # 出走頭数に応じて相手数を詰める（◎以外から最大4）
    partners = [no for (_,no,_) in ranked[1:1+partners_want]]
    return anchor, partners

def format_text_output(ranked: List[Tuple[str,int,float]], cond: Conditions, anchor:int, partners:List[int]) -> str:
    lines = []
    lines.append("――――――――――――――――――――")
    lines.append(f"会場: {cond.venue} ／ 路面: {'湿' if cond.track.lower()=='wet' else '良'}"
                 + (" ／ ナイター" if cond.is_night else ""))
    lines.append("印／車番／スコア")
    for m,no,sc in ranked:
        lines.append(f"{m or ' '} {no}  {sc:7.2f}")
    lines.append("――――――――――――――――――――")
    if anchor and partners:
        p = ",".join(str(x) for x in partners)
        lines.append("固定買い目：1-2345-2345（◎軸 → 上位4頭）")
        lines.append(f"＝ {anchor}-[{p}]-[{p}]")
    else:
        lines.append("相手不足（出走頭数不足）")
    lines.append("――――――――――――――――――――")
    return "\n".join(lines)

# -------------------------
# UI（Streamlit）
# -------------------------
st.set_page_config(page_title="ヴェロビ・オート（事前版）", layout="wide")
st.title("ヴェロビ・オート（事前版）")
st.caption("試走ナシ／会場×天気補正／所属ボーナス／偏差値合算 → 固定買い目 1-2345-2345")

with st.sidebar:
    st.subheader("条件")
    venue = st.selectbox("会場", list(VENUE.keys()))
    track = st.radio("路面", ["dry","wet"], horizontal=True, index=0, format_func=lambda x: "良" if x=="dry" else "湿")
    is_night = st.checkbox("ナイター", value=False)
    partners_want = st.number_input("相手数（デフォ4）", min_value=2, max_value=6, value=DEFAULT_PARTNERS, step=1)

st.markdown("#### 出走データ（%は0..1で入力）")
cols = ["no","name","home","handicap_m","avg_st","avg_raceT","top2_10","good2","wet2"]
homes = list(VENUE.keys())

# 初期テンプレ（8車想定・編集可）
default_rows = [
    [1,"", homes[0],  0, 0.19, 3.472, 0.60, 0.45, 0.25],
    [2,"", homes[0], 10, 0.18, 3.462, 0.70, 0.33, 0.57],
    [3,"", homes[1], 10, 0.23, 3.459, 0.60, 0.47, 0.00],
    [4,"", homes[2], 20, 0.14, 3.449, 0.40, 0.33, 0.40],
    [5,"", homes[3], 20, 0.15, 3.445, 0.70, 0.48, 0.31],
    [6,"", homes[3], 20, 0.15, 3.455, 0.50, 0.24, 0.33],
    [7,"", homes[0], 20, 0.16, 3.433, 0.80, 0.58, 0.50],
    [8,"", homes[4], 30, 0.20, 3.480, 0.35, 0.40, 0.35],
]
df_in = pd.DataFrame(default_rows, columns=cols)

# データエディタ
edited = st.data_editor(
    df_in,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "no": st.column_config.NumberColumn("no", min_value=1, max_value=99, step=1),
        "name": st.column_config.TextColumn("name", help="任意入力"),
        "home": st.column_config.SelectboxColumn("home", options=homes),
        "handicap_m": st.column_config.NumberColumn("handicap_m", help="0,10,20...", step=10),
        "avg_st": st.column_config.NumberColumn("avg_st", format="%.3f"),
        "avg_raceT": st.column_config.NumberColumn("avg_raceT", format="%.3f"),
        "top2_10": st.column_config.NumberColumn("top2_10", help="直近10走2連対率 (0..1)"),
        "good2": st.column_config.NumberColumn("good2", help="良2連率 (0..1)"),
        "wet2": st.column_config.NumberColumn("wet2", help="湿2連率 (0..1)"),
    },
    hide_index=True,
)

# 計算
if st.button("計算する", type="primary", use_container_width=True):
    # DataFrame → Rider リストへ
    riders: List[Rider] = []
    for _, row in edited.iterrows():
        try:
            riders.append(Rider(
                no = int(row["no"]),
                name = str(row["name"]),
                home = str(row["home"]),
                handicap_m = int(row["handicap_m"]),
                avg_st = float(row["avg_st"]),
                avg_raceT = float(row["avg_raceT"]),
                top2_10 = float(row["top2_10"]),
                good2 = float(row["good2"]),
                wet2 = float(row["wet2"]),
            ))
        except Exception:
            st.error("入力に数値/型の不整合がある行があります。確認してください。")
            st.stop()

    # 出走0なら停止
    if not riders:
        st.warning("出走データが空です。")
        st.stop()

    cond = Conditions(track=track, venue=venue, is_night=is_night)

    # スコア計算
    scores = score_riders(riders, cond)
    ranked = rank_and_marks(scores)
    anchor, partners = recommend_fixed_bet(ranked, partners_want=partners_want)

    # ランキング表（印/車番/名前/所属/各偏差値要素も確認できるように再計算＆表示）
    # 各成分偏差値も出して“見える化”
    hand_base = [-r.handicap_m for r in riders]
    st_base   = [-r.avg_st      for r in riders]
    time_base = [-r.avg_raceT   for r in riders]
    recent2   = [r.top2_10      for r in riders]
    cond2     = [r.wet2 if cond.track.lower()=="wet" else r.good2 for r in riders]

    H_hand = _hensachi(hand_base)
    H_st   = _hensachi(st_base)
    H_time = _hensachi(time_base)
    H_rec  = _hensachi(recent2)
    H_cond = _hensachi(cond2)

    # 会場×天気の重み（参考表示用）
    venue_cfg = VENUE.get(cond.venue, {"wet_boost":1.0, "st_boost":1.0, "night_wet_extra":0.0})
    wet_mul = venue_cfg["wet_boost"]
    st_mul  = venue_cfg["st_boost"]
    if cond.is_night and cond.track.lower() == "wet":
        wet_mul += venue_cfg.get("night_wet_extra", 0.0)

    st.markdown("#### 偏差値ランキング（印付き）")
    rank_rows = []
    # ranked: [(mark,no,score)]
    # 表示のため、no→Rider行を引けるdict
    rmap = {r.no: r for r in riders}
    for m,no,sc in ranked:
        r = rmap[no]
        rank_rows.append({
            "印": m, "no": no, "name": r.name, "home": r.home,
            "score": round(sc,2),
            "H_hand": round(H_hand[[rr.no for rr in riders].index(no)],1),
            "H_st":   round(H_st  [[rr.no for rr in riders].index(no)],1),
            "H_time": round(H_time[[rr.no for rr in riders].index(no)],1),
            "H_rec":  round(H_rec [[rr.no for rr in riders].index(no)],1),
            "H_cond": round(H_cond[[rr.no for rr in riders].index(no)],1),
        })
    st.dataframe(pd.DataFrame(rank_rows), use_container_width=True)

    # 買い目表示（固定：1-2345-2345）
    st.markdown("#### 固定買い目：1-2345-2345（◎軸 → 上位4頭）")
    if anchor and partners:
        partners_text = ",".join(str(x) for x in partners)
        st.info(f"＝ {anchor}-[{partners_text}]-[{partners_text}]")
    else:
        st.warning("相手不足（出走頭数不足）")

    # コピー用テキスト
    text_out = format_text_output(ranked, cond, anchor, partners)
    st.markdown("#### そのままコピペ用")
    st.code(text_out, language="text")

    # 参考：現在の重み
    with st.expander("現在の重み・会場補正（参考）"):
        st.write("W =", W)
        st.write("HOME_BONUS_HEN =", HOME_BONUS_HEN)
        st.write("VENUE =", VENUE)

else:
    st.info("テーブルの値を調整して「計算する」を押してください。%は0..1で入力（例：57.1% → 0.571）。")
