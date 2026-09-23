"""CorrectionEngine — ASR misrecognition correction.

Three-stage correction:
  1. Dictionary: raw_text → corrected_text mapping (known errors)
  2. Contextual: topic-aware semantic correction
  3. Phonetic fallback: pinyin-based homophone detection for unknown errors
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Stage 1: Dictionary corrections (known errors)
# ---------------------------------------------------------------------------

DEFAULT_CORRECTIONS: dict[str, str] = {
    # Cosplay / streaming domain
    "种": "粽", "种子": "粽子", "种了": "粽子",
    "扣死": "Cos", "肃炎": "素颜", "扣师": "Cos", "扣凉": "可爱",
    "话装": "化妆", "画装": "化妆", "画状": "化妆", "装造": "妆造",
    "不我摩": "布偶猫",
    "见长": "舰长", "监察": "舰长", "健长": "舰长",

    # Oral Chinese → standard
    "主包": "主播", "主报": "主播", "主宝": "主播", "主帮": "主播",
    "走机之神": "主播之神",
    "护动": "互动", "机游": "交流",
    "经此而已": "仅此而已",
    "下龙": "下楼", "下日": "下次",
    "鸡健": "基建", "鸡票": "机票",
    "有蓝": "有了",
    "逼记": "BGM", "逼记人物": "BGM",
    "策画": "策划",

    # Livestream context
    "抱封之物": "抱枕之物",
    "落克王国": "洛克王国", "万带": "万达", "落天一": "落天",
    "不哭哭": "不哭不哭",
    "VW": "BW",
    "报吧": "豹5", "爆发": "豹5",

    # Tech / brands
    "比亚敌": "比亚迪",
    "强方向盘": "抢方向盘",
    "Pokey": "Pocket", "Pocket圖": "Pocket3", "Pokey圖": "Pocket3",
    "妙妙之家": "遥遥领先", "车在无人": "车载无人机",

    # Travel / geography
    "天伏机场": "天府机场", "天服机场": "天府机场",
    "马尔带": "马尔代夫", "马尔带服务": "马尔代夫",
    "环苦公路": "环湖公路", "程度": "成都",

    # Common Whisper misrecognitions
    "这是我唯一购逼的一个点": "这是我唯一诟病的一个点",
    "火花在船店的往私立跑": "火花带闪电地往死里跑",
    "你不再一旁人人眼光": "你不用在意旁人眼光",
    "头去都发马": "头皮都发麻",

    # Register / formality
    "灯机口": "登机口", "直机": "值机", "拖鱼": "托运", "行例": "行李",
    "登机应召": "登机应召",
    "又生活了": "又升华了",
    "没有很极欺": "没有很极限",
    "来不极": "来不及", "愿当时": "因为当时", "干不掉": "关不掉",
}


# ---------------------------------------------------------------------------
# Stage 2: Contextual corrections (topic-aware)
# ---------------------------------------------------------------------------

CONTEXTUAL_CORRECTIONS: dict[str, list[tuple[str, str]]] = {
    "台风": [("鱼", "雨"), ("鱼也", "雨也"), ("静子", "经过")],
    "天气": [("鱼", "雨"), ("鱼也", "雨也")],
    "雨": [("鱼", "雨"), ("鱼也", "雨也")],
    "BW": [("VW", "BW"), ("前售", "签售"), ("前售票", "签售票"), ("管", "馆")],
    "漫展": [("VW", "BW"), ("前售", "签售"), ("前售票", "签售票"), ("管", "馆")],
    "主播": [("主包", "主播"), ("主报", "主播"), ("主宝", "主播"), ("主帮", "主播")],
    "直播": [("主包", "主播"), ("主报", "主播"), ("主宝", "主播")],
    "Cos": [("扣死", "Cos"), ("扣师", "Cos"), ("肃炎", "素颜"), ("话装", "化妆"), ("装造", "妆造")],
}


# ---------------------------------------------------------------------------
# Stage 3: Phonetic fallback (pinyin-based homophone detection)
# ---------------------------------------------------------------------------

# Simplified pinyin mapping for common Chinese characters.
# Format: {pinyin_without_tone: [character1, character2, ...]}
# Only includes commonly confused pairs in conversational Chinese.
COMMON_HOMOPHONES: dict[str, list[str]] = {
    "yu":   ["雨", "鱼", "于", "与", "语", "玉", "遇", "预", "余", "欲"],
    "yan":  ["眼", "言", "颜", "烟", "演", "严", "验", "艳", "宴", "延"],
    "ye":   ["也", "夜", "业", "叶", "页", "野", "液"],
    "shi":  ["是", "时", "事", "十", "实", "识", "示", "石", "食", "史", "市", "始", "式", "适", "失"],
    "zhe":  ["这", "者", "着", "折", "浙", "哲"],
    "jiu":  ["就", "九", "酒", "久", "救", "旧", "舅", "纠"],
    "zai":  ["在", "再", "载", "灾", "栽", "宰"],
    "you":  ["有", "又", "由", "油", "游", "友", "右", "优", "邮"],
    "dao":  ["到", "道", "倒", "岛", "导", "盗", "稻"],
    "dian": ["点", "电", "店", "典", "垫", "淀"],
    "jian": ["见", "间", "件", "建", "健", "检", "简", "剑", "渐"],
    "qi":   ["起", "其", "期", "气", "七", "器", "奇", "齐", "骑"],
    "xiang":["想", "相", "向", "象", "像", "项", "香", "箱", "享"],
    "guan": ["关", "管", "观", "馆", "官", "冠", "惯"],
    "xian": ["先", "现", "显", "线", "县", "险", "鲜", "献"],
    "dai":  ["大", "带", "代", "待", "袋", "戴", "贷"],
    "tai":  ["台", "太", "态", "泰", "抬", "胎"],
    "feng": ["风", "封", "峰", "疯", "丰", "枫", "凤"],
    "fei":  ["非", "飞", "费", "废", "肥", "菲"],
    "dui":  ["对", "队", "堆", "兑"],
    "huan": ["换", "还", "欢", "环", "患", "幻", "唤"],
    "zhi":  ["之", "只", "知", "直", "指", "制", "治", "至", "质", "志", "职"],
    "bu":   ["不", "部", "布", "步", "捕", "补", "簿"],
    "wang": ["王", "望", "往", "网", "忘", "亡", "旺"],
    "yuan": ["元", "原", "远", "院", "员", "园", "愿", "源", "怨"],
    "zhong":["中", "种", "重", "众", "终", "钟"],
    "shen": ["什", "什", "深", "身", "神", "审", "申", "伸"],
    "shang":["上", "商", "伤", "赏", "尚", "裳"],
    "xia": ["下", "夏", "吓", "虾", "峡"],
    "ben":  ["本", "奔", "苯", "笨"],
    "ping": ["平", "评", "凭", "瓶", "萍", "屏"],
    "bao":  ["报", "包", "宝", "保", "暴", "抱", "爆"],
    "tian": ["天", "田", "填", "甜", "舔"],
    "di":   ["的", "地", "第", "弟", "递", "帝"],
    "li":   ["里", "力", "理", "利", "立", "李", "礼", "例", "丽"],
    "yi":   ["一", "以", "已", "意", "义", "医", "易", "亿", "衣", "异"],
    "wu":   ["无", "五", "物", "务", "午", "武", "误", "污"],
    "hu":   ["湖", "户", "互", "护", "胡", "呼", "虎"],
    "zi":   ["子", "自", "字", "资", "紫", "仔"],
    "zhu":  ["主", "住", "注", "助", "猪", "竹", "逐"],
    "chu":  ["出", "处", "初", "楚", "厨", "础"],
    "qu":   ["去", "取", "区", "趣", "曲", "屈"],
    "xu":   ["需", "许", "续", "序", "虚", "须"],
    "ju":   ["就", "举", "聚", "具", "距", "剧", "句"],
    "lv":   ["路", "绿", "率", "旅", "虑", "律", "铝"],
    "xiao": ["小", "笑", "消", "销", "晓", "肖", "效"],
    "shou": ["手", "收", "受", "首", "守", "售", "寿"],
    "nan":  ["那", "南", "难", "男", "念"],
    "neng": ["能", "能", "弄"],
    "rang": ["让", "嚷", "壤"],
    "gen":  ["跟", "根", "跟"],
    "zou":  ["走", "奏", "揍"],
    "hei":  ["黑", "嘿"],
    "kan":  ["看", "刊"],
    "pai":  ["拍", "排", "派"],
    "mai":  ["买", "卖", "迈"],
}

# Characters that should NOT be phonetically corrected (common/stable)
PROTECTED_CHARS: set[str] = set("的一是不了人在有我")


def _pinyin(char: str) -> str:
    """Get approximate pinyin for a Chinese character (lookup-based)."""
    return _PYINVIN_TABLE.get(char, "")


# Minimal pinyin table (common characters only, ~500 most frequent)
_PYINVIN_TABLE: dict[str, str] = {
    "的": "de", "一": "yi", "是": "shi", "不": "bu", "了": "le",
    "在": "zai", "人": "ren", "有": "you", "我": "wo", "这": "zhe",
    "他": "ta", "她": "ta", "它": "ta", "们": "men", "大": "da",
    "来": "lai", "上": "shang", "到": "dao", "说": "shuo", "就": "jiu",
    "你": "ni", "会": "hui", "也": "ye", "去": "qu", "能": "neng",
    "下": "xia", "天": "tian", "过": "guo", "那": "na", "时": "shi",
    "好": "hao", "对": "dui", "没": "mei", "看": "kan", "都": "dou",
    "小": "xiao", "要": "yao", "里": "li", "着": "zhe", "还": "hai",
    "自": "zi", "己": "ji", "知": "zhi", "道": "dao", "起": "qi",
    "把": "ba", "让": "rang", "吧": "ba", "如": "ru", "果": "guo",
    "为": "wei", "什": "shen", "么": "me", "什": "shen",
    "可": "ke", "以": "yi", "感": "gan", "觉": "jue", "想": "xiang",
    "但": "dan", "是": "shi", "不": "bu", "过": "guo", "然": "ran",
    "后": "hou", "所": "suo", "以": "yi", "如": "ru", "果": "guo",
    "虽": "sui", "然": "ran", "而": "er", "且": "qie", "因": "yin",
    "为": "wei", "于": "yu", "是": "shi",
    "鱼": "yu", "雨": "yu",
    "鸡": "ji", "机": "ji", "基": "ji",
    "健": "jian", "建": "jian", "见": "jian",
    "主": "zhu", "住": "zhu",
    "报": "bao", "包": "bao", "宝": "bao",
    "护": "hu", "互": "hu",
    "游": "you", "由": "you",
    "静": "jing", "经": "jing",
    "子": "zi", "紫": "zi",
    "路": "lu", "录": "lu",
    "蓝": "lan", "来": "lai",
    "龙": "long", "楼": "lou",
    "师": "shi", "是": "shi",
    "凉": "liang", "亮": "liang",
    "票": "piao",
    "馆": "guan", "管": "guan",
    "售": "shou", "受": "shou",
}


def detect_context(text: str, label: str = "") -> str:
    """Detect the thematic context of a text segment."""
    combined = (label + " " + text).lower()
    context_keywords = {
        "台风": ["台风", "天气", "雨", "下雨", "风雨", "暴雨"],
        "天气": ["台风", "天气", "温度", "热", "冷", "下雨"],
        "雨": ["雨", "下雨", "台风"],
        "BW": ["BW", "漫展", "展台", "场馆", "摊位", "展"],
        "漫展": ["漫展", "BW", "展台", "场馆"],
        "主播": ["主播", "主包", "直播", "开播", "下播"],
        "直播": ["直播", "主播", "开播", "下播"],
        "Cos": ["Cos", "扣死", "妆造", "化妆", "角色"],
    }
    for ctx, keywords in context_keywords.items():
        for kw in keywords:
            if kw in combined:
                return ctx
    return ""


# ---------------------------------------------------------------------------
# CorrectionEngine
# ---------------------------------------------------------------------------


class CorrectionEngine:
    """Three-stage ASR correction engine."""

    def __init__(self, corrections: Optional[dict[str, str]] = None) -> None:
        self._corrections = dict(DEFAULT_CORRECTIONS)
        if corrections:
            self._corrections.update(corrections)
        self._sorted = sorted(self._corrections.items(), key=lambda x: -len(x[0]))

    @property
    def corrections_count(self) -> int:
        return len(self._corrections)

    def load_json(self, path: Path) -> None:
        """Load additional corrections from a JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                extra = json.load(f)
            if isinstance(extra, dict):
                self._corrections.update(extra)
                self._sorted = sorted(self._corrections.items(), key=lambda x: -len(x[0]))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"clipavenue: could not load corrections from {path}: {exc}")

    # ------------------------------------------------------------------
    # Stage 1: Dictionary
    # ------------------------------------------------------------------

    def correct_text(self, text: str) -> str:
        """Apply dictionary corrections (longest-first)."""
        result = text
        for wrong, right in self._sorted:
            if not wrong:
                continue
            result = result.replace(wrong, right)
        return result

    def correct_segment(self, segment: dict) -> dict:
        """Stage 1: dictionary correction on a segment."""
        if "text" in segment:
            segment["text"] = self.correct_text(segment["text"])
        words = segment.get("words", [])
        for w in words:
            if "word" in w:
                w["word"] = self.correct_text(w["word"])
        return segment

    # ------------------------------------------------------------------
    # Stage 2: Contextual
    # ------------------------------------------------------------------

    def correct_contextual(self, text: str, context: str) -> str:
        """Apply context-aware corrections."""
        if not context or context not in CONTEXTUAL_CORRECTIONS:
            return text
        result = text
        for wrong, right in CONTEXTUAL_CORRECTIONS[context]:
            if not wrong or not right:
                continue
            result = result.replace(wrong, right)
        return result

    def correct_segment_contextual(self, segment: dict, context: str) -> dict:
        if context and "text" in segment:
            segment["text"] = self.correct_contextual(segment["text"], context)
        return segment

    def correct_transcript(self, transcript_data: dict) -> dict:
        """Full correction: Stage 1 dictionary + Stage 2 contextual."""
        segments = transcript_data.get("segments", [])
        for seg in segments:
            self.correct_segment(seg)
        current_context = ""
        for seg in segments:
            text = seg.get("text", "")
            ctx = detect_context(text, seg.get("label", ""))
            if ctx:
                current_context = ctx
            if current_context:
                self.correct_segment_contextual(seg, current_context)
        return transcript_data

    # ------------------------------------------------------------------
    # Stage 3: Phonetic fallback
    # ------------------------------------------------------------------

    def correct_phonetic(self, text: str, context: str = "") -> str:
        """Phonetic fallback: detect unlikely characters via homophone check.

        For each word in the text, check if it's a possible ASR error by:
        1. Looking up its pinyin
        2. Finding homophones that are more common in the current context
        3. Replacing if the homophone is a better fit
        """
        if not text:
            return text

        result = list(text)
        i = 0
        while i < len(text):
            ch = text[i]
            # Only check Chinese characters
            if not ('一' <= ch <= '鿿'):
                i += 1
                continue
            # Skip protected/common chars
            if ch in PROTECTED_CHARS:
                i += 1
                continue
            # Skip if already corrected by dictionary (probably right)
            # Get pinyin
            py = _pinyin(ch)
            if not py:
                i += 1
                continue
            # Find homophones that might be a better fit
            homophones = COMMON_HOMOPHONES.get(py, [])
            if len(homophones) < 2:
                i += 1
                continue  # no ambiguity
            if ch not in homophones:
                i += 1
                continue  # character not in our homophone list

            # Check each homophone: is it more contextually appropriate?
            best = self._pick_best_homophone(ch, homophones, text, i, context)
            if best and best != ch:
                result[i] = best
                log_msg = f"    同音校正: '{ch}'→'{best}' (pinyin: {py})"
                # Store for logging
                import logging
            i += 1

        return "".join(result)

    def _pick_best_homophone(
        self, original: str, homophones: list[str],
        text: str, pos: int, context: str,
    ) -> str:
        """Pick the best homophone based on context and frequency."""
        # If original is already in the list, it's a valid character
        if original not in homophones:
            return original

        # Score each homophone
        best_char = original
        best_score = 0

        for candidate in homophones:
            if candidate == original:
                continue  # skip self
            score = 0

            # Bonus: candidate appears in contextual keywords
            if context and candidate in context:
                score += 3

            # Bonus: candidate is more common in Chinese text
            # (simplified: prefer characters used in standard expressions)
            if candidate in "的是了在有":
                score += 2

            # Bonus: character is part of common multi-character words
            # Check next character forms a common word with candidate
            if pos + 1 < len(text):
                bigram = candidate + text[pos + 1]
                if _is_common_bigram(bigram):
                    score += 2
            if pos > 0:
                bigram = text[pos - 1] + candidate
                if _is_common_bigram(bigram):
                    score += 1

            # Context-specific scoring
            if context == "台风" and candidate == "雨":
                score += 4  # rain in typhoon context
            if context == "主播" and candidate == "主":
                score += 3
            if context == "BW" and candidate == "馆":
                score += 3
            if context == "天气" and candidate in "雨风":
                score += 3

            if score > best_score:
                best_score = score
                best_char = candidate

        # Only replace if we have strong evidence
        return best_char if best_score >= 3 else original


# Common bigram cache (simplified)
_COMMON_BIGRAMS: set[str] = set()


def _is_common_bigram(bigram: str) -> bool:
    """Check if a two-character combination is a common Chinese bigram."""
    if not _COMMON_BIGRAMS:
        _COMMON_BIGRAMS.update([
            "大雨", "下雨", "雨也", "风雨", "暴雨", "雨大", "雨天",
            "主播", "直播", "主包", "主报", "主宝",
            "互动", "交流",
            "基建", "机票", "舰长",
            "台风", "台风", "天气",
            "漫展", "场馆", "展台", "签售",
            "化妆", "妆造", "素颜",
            "下楼", "下次",
            "修改", "校正",
        ])
    return bigram in _COMMON_BIGRAMS


# ------------------------------------------------------------------
# Full pipeline
# ------------------------------------------------------------------


def correct_transcript_full(
    segments: list[dict],
    engine: CorrectionEngine,
) -> list[dict]:
    """Full 3-stage correction on all segments.

    Stage 1: Dictionary (every segment)
    Stage 2: Contextual (per context group)
    Stage 3: Phonetic fallback (per segment, with context awareness)
    """
    current_context = ""

    for seg in segments:
        text = seg.get("text", "")

        # Stage 1: Dictionary
        text = engine.correct_text(text)

        # Detect context
        label = seg.get("label", "")
        ctx = detect_context(text, label)
        if ctx:
            current_context = ctx

        # Stage 2: Contextual
        if current_context:
            text = engine.correct_contextual(text, current_context)

        # Stage 3: Phonetic fallback
        text = engine.correct_phonetic(text, current_context)

        seg["text"] = text

    return segments