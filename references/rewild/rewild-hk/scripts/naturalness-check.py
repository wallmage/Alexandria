#!/usr/bin/env python3
"""Naturalness check: statistical AI-tell screening for EN / ZH / HK / TW / DE.

Usage:
    python3 naturalness-check.py FILE [--source ORIGINAL] [--lang en|zh|hk|tw|de]
    python3 naturalness-check.py --audit [--lang en|zh|hk|tw|de]

`zh` is mainland Simplified Chinese. `hk` and `tw` are Traditional Chinese for
Hong Kong and Taiwan, which are separate languages to this checker for a
reason: their native vocabularies overlap with each other's *wrong* vocabulary.
網絡 is correct in Hong Kong and a defect in Taiwan; 網路 is the reverse. A
single Traditional mode could not flag either without flagging both.

Screens a text for the measurable signals described in the Rewild pattern
catalogs: sentence-length uniformity, repeated sentence openers, uniform
paragraph sizes, AI vocabulary, and punctuation problems. Zero dependencies.

--source turns on the fidelity pass, which is the more important half. Style
tells are what the model is already good at removing; fidelity is where
rewrites actually break. It compares the rewrite against the original and
flags four things, each an observed failure mode rather than a theoretical
one:

  * names, numbers and dates in the rewrite that are not in the original
  * attributed claims ("observers have cited X") that became bare assertions
  * commitments ("we'll send an update") the original never made
  * severity raised beyond what the original said

A style warning is a suggestion. A fidelity warning is a defect: the rewrite
is now saying something the source did not.

Exit status is 0 when the report is clean and 1 when anything is flagged, so
the check can gate a workflow. It measures signals, not truth — a clean report
does not prove the text reads well. Judgment stays with the writer.

--audit compares the word lists below against `references/patterns.md` and
reports terms the catalog documents but the checker cannot see. Run it after
editing a catalog so the two never drift apart.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

# Languages written without spaces, so sentence length is counted in characters
# and word-boundary regexes do not apply.
CJK_LANGS = ("zh", "hk", "tw")
# The two Traditional variants, which additionally get the region pass.
HANT_LANGS = ("hk", "tw")

# Terms that raise a warning. Kept in sync with the "AI vocabulary" pattern in
# each catalog; matched with light inflection (showcase → showcasing/showcased).
AI_WORDS_EN = [
    "additionally", "moreover", "furthermore", "boast", "breathtaking",
    "comprehensive", "crucial", "cutting-edge", "delve", "elevate", "embark",
    "enduring", "enhance", "exemplify", "foster", "game-changing", "garner",
    "groundbreaking", "holistic", "interplay", "intricacy", "intricate",
    "intuitive", "leverage", "myriad", "nestle", "pivotal", "realm",
    "renowned", "robust", "seamless", "showcase", "streamline", "stunning",
    "tapestry", "testament", "underscore", "vibrant",
]
AI_PHRASES_EN = [
    # hedged notes and closers
    "it's worth noting", "it is worth noting", "it's important to note",
    "it is important to note", "in conclusion", "in summary", "to sum up",
    "not only", "plays a crucial role", "stands as", "serves as",
    "ever-evolving", "indelible mark", "reflects broader", "must-visit",
    "everything from",
    "underscores its importance", "highlights its importance",
    "several sources", "several publications",
    # formulaic openers
    "in today's", "fast-paced world", "in an era where",
    "have you ever wondered", "imagine a world where", "picture this",
    "since the dawn of", "throughout history", "in recent years,",
    # empty future framing
    "sets the stage", "setting the stage for", "marks a shift",
    "future looks bright", "exciting times lie ahead", "looking ahead",
    "only time will tell", "it remains to be seen",
    "journey toward excellence", "the biggest lesson i learned",
    "this experience taught me",
    # vague attribution
    "industry reports", "observers have cited", "experts argue",
    "experts believe", "some critics argue", "commitment to",
    # outline skeletons
    "despite these challenges", "challenges and legacy", "future outlook",
    # assistant artifacts
    "let me break this down", "let me walk you through", "here's the thing",
    "the real question is", "what most people get wrong",
    "here's what nobody tells you", "the part everyone misses",
    "what if i told you", "the short answer is", "so here's what happened",
    "what struck me most", "i find it fascinating that", "i hope this helps",
    "you're absolutely right", "would you like me", "certainly!",
    "of course!", "while specific details are limited",
    "up to my last training update",
]
# Context-dependent terms: reported for visibility, never flagged. "landscape"
# is AI slop in "the evolving landscape" and plain English in a gardening post.
AI_WATCH_EN = [
    "align", "collaboration", "contributing", "emphasizing", "ensuring",
    "establishment", "examination", "facilitation", "highlight",
    "implementation", "journey", "key", "landscape", "navigate",
    "optimization", "powerful", "profound", "reflecting", "rich",
    "symbolizing", "transformation", "ultimately", "unlock", "utilization",
    "valuable",
]

AI_WORDS_DE = [
    "zudem", "folglich", "nichtsdestotrotz", "zusammenfassend",
    "abschließend", "infolgedessen", "innovativ", "nahtlos", "ganzheitlich",
    "bahnbrechend", "facettenreich", "maßgeblich", "essenziell",
    "meilenstein", "umfassend", "eintauch", "unterstreich", "vielfältig",
    "atemberaubend", "renommiert", "tiefgreifend", "zusätzlich",
]
AI_PHRASES_DE = [
    "darüber hinaus", "in der heutigen zeit", "im digitalen zeitalter",
    "es ist wichtig zu beachten", "tauchen wir ein", "eine vielzahl",
    "breite palette", "nicht nur", "schlüsselrolle", "lässt sich sagen",
    "auf ein neues level", "es lässt sich nicht leugnen", "seit jeher",
    "in einer welt, in der", "bleibt festzuhalten", "insgesamt zeigt sich",
    "es bleibt spannend", "die zukunft wird zeigen",
    "was die meisten übersehen", "die eigentliche frage ist",
    "lassen sie uns eintauchen", "hier ist eine aufschlüsselung",
    "das sagt dir niemand", "was die meisten falsch machen",
    "immer mehr menschen fragen sich", "fazit:", "dient als",
    "steht für", "eingebettet in", "spiegelt breitere trends wider",
    "ist ein beweis", "ist ein zeugnis", "bis hin zu", "angefangen bei",
]
AI_WATCH_DE = [
    "effizient", "entscheidend", "ermöglich", "landschaft", "lebendig",
    "markiert", "präzise", "spannend", "zentral",
]

AI_PHRASES_ZH = [
    "此外", "值得注意的是", "值得一提的是", "综上所述", "总而言之",
    "总的来说", "与此同时", "不难发现", "在当今", "众所周知", "赋能",
    "砥砺前行", "不忘初心", "深耕细作", "精益求精", "高质量发展",
    "开拓创新", "与时俱进", "未来可期", "我们有理由相信", "深刻变革",
    "不可忽视", "近年来，随着", "随着人工智能", "展望未来", "守正创新",
    "行稳致远", "新质生产力", "数字化转型", "机遇与挑战并存",
    "在此基础上", "特别需要关注的是", "需要指出的是", "必须强调的是",
    "基于以上分析", "具体来说", "另一方面", "在一定程度上", "某种程度上",
    "起到了积极作用", "首先，", "其次，", "最后，", "相信在不久的将来",
    "很多人都忽略了", "没人告诉你的是", "大多数人都搞错了",
    "真正的问题其实是", "让我来分析", "下面我将", "进行优化", "开展实施",
    "随着科技的发展", "无缝", "彰显", "构成了",
]
AI_WATCH_ZH = [
    "显著", "构建", "机制", "框架", "促进", "体现", "有助于", "提升",
    "随着", "然而", "不仅",
]

# Traditional Chinese. The generic connective slop is shared with AI_PHRASES_ZH
# in converted form; the mainland set-phrases are kept because they survive a
# character conversion intact and are the loudest sign of an unconverted source.
AI_PHRASES_HANT = [
    # generic AI framing
    "值得注意的是", "值得一提的是", "綜上所述", "總而言之",
    "總的來說", "與此同時", "不難發現", "在當今", "眾所周知",
    "近年來，隨著", "近年來，隨着", "展望未來", "在此基礎上",
    "特別需要關注的是", "需要指出的是", "必須強調的是", "基於以上分析",
    "具體來說", "在一定程度上", "某種程度上", "首先，", "其次，", "最後，",
    "相信在不久的將來", "隨著科技的發展", "隨着科技的發展", "彰顯",
    # assistant artifacts
    "很多人都忽略了", "沒人告訴你的是", "大多數人都搞錯了",
    "真正的問題其實是", "讓我來分析", "下面我將", "我希望這對你有幫助",
    # Mainland set-phrases that survive conversion unchanged. The ones that are
    # purely a provenance signal live in MAINLAND_ONLY instead — carrying a
    # term in both lists produced two separate failures for one occurrence.
    "精益求精", "與時俱進", "未來可期", "我們有理由相信", "深刻變革",
    "機遇與挑戰並存", "起到了積極作用", "數字化轉型", "以此為契機",
    # Mainland business jargon, in the collocations that carry it. The bare
    # forms were removed after an audit found them firing on 絕對標準,
    # 天衣無縫, 地層下沉 and 麗寶賽道 — the terms are real tells, the
    # substring match was not.
    "內卷", "破圈", "復盤",
    "助力企業", "助力產業", "助力發展", "助力轉型", "助力創新",
    "助力成長", "助力升級", "助力經濟",
    "新賽道", "細分賽道", "換賽道",
    "下沉市場", "渠道下沉", "通路下沉",
    "對標國際", "對標世界", "對標先進", "對標一流",
    "無縫接軌", "無縫銜接", "無縫整合", "無縫串接", "無縫體驗",
    # Generic closers, shared across both regions.
    "不可否認的是", "值得我們深思", "希望對你有幫助",
    "讓我們拭目以待", "仍有待時間檢驗", "後續發展仍待觀察",
    "未來發展值得期待", "期待帶來更多驚喜", "以上就是這次的分享",
    "其實你一直搞錯了",
]
# Each region's OWN set-phrase inventory: the formulas local writers overuse
# and a model reproduces when told to "write like a Taiwanese person". They do
# double duty, and the second duty is the one a converted catalog misses.
# Inside their own region they are cliché — flagged as AI vocabulary. Inside
# the other region they are a *provenance* defect, because the input to a
# Taiwan→Hong Kong rewrite is full of them and no amount of noun-swapping
# removes them.
#
# The two duties need different lists, and this is the trap: a formula can be a
# regional cliché without being regionally *exclusive*. 攜手合作 appears 74
# times in 8.2M characters of Hong Kong government press releases, so using it
# as a "this text came from Taiwan" signal reports clean Hong Kong prose as
# foreign. Only the *_PROVENANCE lists cross over.
TW_SET_PHRASES = [
    "共襄盛舉", "一同見證", "不遺餘力", "以上供參", "備受矚目", "共創雙贏",
    "共勉之", "創下佳績", "劃下完美句點", "善盡企業社會責任", "圓滿落幕",
    "大放異彩", "寫下新頁", "屢創新高", "拚經濟", "掀起熱潮", "接軌國際",
    "揭開序幕", "攜手合作", "有目共睹", "深化合作",
    "滾動式檢討", "締造佳績", "與大家共勉", "蔚為風潮", "超前部署",
]
# Measured against that corpus: everything below scores 4 or fewer hits, while
# the six removed from it score 5 to 74.
TW_PROVENANCE = [t for t in TW_SET_PHRASES if t not in {
    "攜手合作", "揭開序幕", "深化合作", "一同見證", "不遺餘力", "有目共睹"}]

# Hong Kong's own inventory, counted in the same corpus. Hong Kong corporate
# and government registers are formulaic in their own way, and 「是次」「乃」
# 「謹此」 are not ornaments a Taiwanese writer would produce — they are the
# skeleton of a Hong Kong notice, and they survive every lexical conversion.
# Exclusive to Hong Kong, so safe for both duties.
HK_SET_PHRASES = [
    "背靠祖國", "聯通世界", "超級聯繫人", "超級增值人", "內聯外通",
    "說好香港故事", "由治及興", "融入國家發展大局", "拆牆鬆綁",
    "國家所需", "香港所長",
    "再創高峰", "邁向新里程", "更上一層樓", "與時並進", "鞏固及提升",
    "急市民所急", "以民為本",
]
# Hong Kong-overused but pan-Chinese: flagged as Hong Kong vocabulary, never
# used as a provenance signal, because Taiwan writes them just as freely.
HK_OWN_CLICHES = [
    "圓滿成功", "圓滿舉行", "反應熱烈", "多管齊下", "一站式", "互利共贏",
    "重要里程碑", "追求卓越", "屢獲殊榮", "誠意推介", "信心保證",
    "貼心服務", "專業團隊", "全力以赴", "迎難而上", "再接再厲",
    "把握機遇", "獨特優勢", "共創美好將來", "攜手邁進", "業界翹楚",
    "全城矚目", "引領潮流",
]
# Hong Kong's formal-correspondence skeleton. Purely a provenance signal:
# inside Hong Kong these are correct register, so they are never flagged for
# hk — only for tw, where they are the tell that a rewrite converted the nouns
# and left the bones. Found by a Hong Kong→Taiwan rewrite in which the only
# lexical hits were 網絡/質素/數碼/人工智能 and every one of these survived.
HK_CORRESPONDENCE = [
    "是次", "今次", "謹此", "謹將", "謹啟", "鳴謝", "順頌業祺", "順頌台祺",
    "敬希垂注", "敬請留意", "煩請", "有勞", "務請", "如有查詢",
    "茲通知", "現謹將", "有見及此", "就此", "暢順", "推展", "深明",
]
AI_PHRASES_HK = AI_PHRASES_HANT + HK_SET_PHRASES + HK_OWN_CLICHES + [
    # Hong Kong writes 隨着. The 著 spelling was the only one listed here for a
    # while, so correctly-spelled Hong Kong text walked straight past it.
    "隨着人工智能", "隨著人工智能",
    # Assistant register in Cantonese.
    "大部分人其實搞錯咗", "好多人都唔知", "有一件事無人會同你講",
]
AI_PHRASES_TW = AI_PHRASES_HANT + TW_SET_PHRASES + ["隨著人工智慧"]
# Fed to the region pass, not the vocabulary pass: the other side's formulas.
REGION_FOREIGN_PHRASES = {
    "hk": TW_PROVENANCE,
    "tw": HK_SET_PHRASES + HK_CORRESPONDENCE,
}
AI_WATCH_HANT = [
    "顯著", "構建", "機制", "框架", "促進", "體現", "有助於", "提升",
    "隨著", "然而", "不僅",
    # Demoted from the flagged list. Every one of these is ordinary Traditional
    # Chinese; what makes a text read machine-written is how many of them are
    # crowded together, which CONNECTIVE_DENSITY judges instead.
    "此外", "另一方面", "具體而言", "由此可見", "總括而言", "整體而言",
    "換言之", "更重要的是", "除此之外", "不可忽視",
    "打造", "痛點", "全方位", "助力",
]
AI_WATCH_HK = AI_WATCH_HANT + [
    "隨着", "群策群力", "繼往開來", "同心協力", "里程碑", "締造",
    "標誌着", "共贏", "新篇章", "奠定", "堅實基礎", "一如既往",
    "鼎力支持", "持份者", "檢視", "揭開序幕", "攜手合作",
    # Not errors — 隊列 is the correct Hong Kong word. But a Hong Kong IT
    # department writes "message queue" or MQ, and translating it was the
    # one place four separate rewrites gave themselves away.
    "訊息隊列", "消息隊列", "回滾",
    "深化合作", "一同見證", "不遺餘力", "有目共睹",
]
AI_WATCH_TW = AI_WATCH_HANT + [
    "永續經營", "產業升級",
    # Correct Taiwanese words; a Taiwanese engineer still says the English.
    "訊息佇列", "消息隊列", "回滾",
]
# Presence of 此外 is not a defect; five different connectives on one page is.
# The demotions above cost real coverage, and this is how it comes back without
# telling a writer that an ordinary word is wrong.
CONNECTIVE_DENSITY = {
    "hant": ["此外", "另一方面", "具體而言", "由此可見", "總括而言",
             "整體而言", "換言之", "更重要的是", "除此之外", "不可忽視",
             "也因此", "與此同時", "值得注意的是", "具體來說",
             "首先", "其次", "最後"],
    "zh": ["此外", "另一方面", "具体而言", "由此可见", "总的来说",
           "整体而言", "换言之", "更重要的是", "除此之外", "不可忽视",
           "与此同时", "值得注意的是", "具体来说",
           "首先", "其次", "最后"],
}

# (flagged words, flagged phrases, reported-only watchlist) per language.
VOCAB = {
    "en": (AI_WORDS_EN, AI_PHRASES_EN, AI_WATCH_EN),
    "de": (AI_WORDS_DE, AI_PHRASES_DE, AI_WATCH_DE),
    "zh": ([], AI_PHRASES_ZH, AI_WATCH_ZH),
    "hk": ([], AI_PHRASES_HK, AI_WATCH_HK),
    "tw": ([], AI_PHRASES_TW, AI_WATCH_TW),
}

ZH_PARTICLES = "呢啊吧嘛哦啦哇喽呀"
# Hong Kong writing draws its particles from Cantonese, and most of them are
# wrong outside 書面粵語. Taiwan's set is wider and appears in ordinary prose.
HK_PARTICLES = "呢吧嘛啦囉喎咩㗎啩呀"
TW_PARTICLES = "喔唷耶欸啦齁嘛吧呢囉啊"

# ------------------------------------------------- Traditional Chinese: region
# The premise of the hk/tw split. Each region's native vocabulary overlaps the
# other's wrong vocabulary, so these lists are deliberately not symmetric with
# MAINLAND_ONLY: 網絡 is a defect in Taiwan and correct in Hong Kong, so it
# belongs in TW_FOREIGN, never in MAINLAND_ONLY.
#
# REGION_FOREIGN[lang] holds terms native to the *other* Traditional region.
#
# These lists are deliberately short. The catalogs carry 120+ rows each; only
# the unambiguous ones belong in a gate, because several obvious candidates are
# traps. 項目 means "project" in Hong Kong but "item" in Taiwan (比賽項目,
# 檢驗項目), so flagging it would fire on ordinary Taiwanese prose. 短片, 招聘,
# 影片, 行動 and 線上 fail the same way. Precision over recall: a false
# positive here trains the writer to ignore the whole section.
REGION_FOREIGN = {
    # Hong Kong text: these are Taiwan's words.
    "hk": ["維運", "基礎架構", "資料儲存", "多多包涵",
           "網路", "軟體", "硬體", "人工智慧", "智慧型", "專案", "印表機",
           "列印", "部落格", "網際網路", "佇列", "客製化", "串接", "計程車", "捷運", "悠遊卡", "便當",
           "筆記型電腦", "隨身碟", "雷射", "單眼相機", "執行長",
           "多頭市場", "空頭市場", "已開發國家", "數位",
           "伴手禮", "腳踏車", "泡麵", "鮪魚", "鮭魚", "起司", "葡萄柚",
           "冰淇淋", "壓克力", "太白粉", "魔術方塊", "金氏世界紀錄",
           "國內生產毛額", "首次公開發行", "商辦大樓", "營運長", "財務長"],
    # Taiwan text: these are Hong Kong's words.
    # 項目 alone stays out — it means "item" in Taiwan (比賽項目, 檢驗項目) and
    # flagging it would fire on ordinary Taiwanese prose. These collocations
    # only ever mean "project", so they are safe where the bare word is not.
    "tw": ["項目管理", "項目經理", "項目團隊", "項目進度", "項目負責人",
           "網絡", "軟件", "硬件", "人工智能", "智能手機", "互聯網", "打印機",
           "質素", "私隱", "數碼", "寫字樓", "行政總裁", "機械人", "博客",
           "夾萬", "按揭", "強積金", "綜援", "打工仔", "擠擁", "取錄",
           "銜頭", "梳化", "荷里活", "升降機", "迴旋處", "八達通", "雪糕",
           "芝士", "忌廉", "三文治", "士多啤梨", "香口膠", "吞拿魚",
           "士多", "手信", "利是", "電飯煲",
           "本地生產總值", "首次公開招股", "董事總經理", "市場推廣"],
}
# Wrong in both Hong Kong and Taiwan: mainland-only vocabulary and jargon that
# survives a Simplified-to-Traditional conversion unchanged. Note what is NOT
# here: 打造 and 助力 are ordinary in Taiwanese marketing, 質量 is legitimate
# physics in both, and 網絡/智能/項目 are correct Hong Kong words. Those belong
# to the region lists or the catalogs, never here.
MAINLAND_ONLY = [
    "視頻", "信息", "默認值", "默認設置", "默認選項", "默認情況下", "鼠標", "內存條", "內存卡", "內存不足", "內存空間", "服務器", "筆記本電腦", "出租車",
    "公交車", "優盤", "軟盤", "賦能", "抓手", "閉環", "頂層設計", "顆粒度",
    "新質生產力", "高質量發展", "砥礪前行", "守正創新", "行穩致遠",
    "不忘初心", "保駕護航", "深耕細作", "開拓創新", "五險一金", "小程序",
    "公眾號", "打工人", "模塊", "運維", "移動端", "數據看板", "響應速度", "響應時間",
                 "塑料", "西紅柿", "方便麵", "冰激凌", "信息技術",
    # PRC administrative register. Unlike the business jargon above, none of
    # this appears in Hong Kong or Taiwanese writing.
    "切實抓好", "有力有序", "貫徹落實", "順祝商祺", "此致敬禮",
]
# Proper-noun transliterations, the fastest tell of all. {lang: {wrong: right}}
TRANSLIT_FOREIGN = {
    # Hong Kong text carrying Taiwan's renderings.
    "hk": {"川普": "特朗普", "歐巴馬": "奧巴馬", "柯林頓": "克林頓",
           "小布希": "小布殊", "布希總統": "布殊總統", "雷根": "列根", "柴契爾": "戴卓爾",
           "梅克爾": "默克爾", "馬克宏": "馬克龍", "普丁": "普京",
           "澤倫斯基": "澤連斯基", "賓拉登": "拉登", "紐西蘭": "新西蘭",
           "義大利": "意大利", "寮國": "老撾", "卡達": "卡塔爾",
           "肯亞": "肯尼亞", "奈及利亞": "尼日利亞", "衣索比亞": "埃塞俄比亞",
           "克羅埃西亞": "克羅地亞", "莫三比克": "莫桑比克", "雪梨歌劇院": "悉尼歌劇院", "雪梨大學": "悉尼大學",
           "杜拜": "迪拜", "坎城": "康城", "舊金山": "三藩市",
           "賓士": "平治", "福斯": "福士", "臉書": "Facebook",
           "貝克漢": "碧咸", "梅西": "美斯", "費德勒": "費達拿",
           "星際大戰": "星球大戰", "蜘蛛人": "蜘蛛俠", "鋼鐵人": "鐵甲奇俠",
           "寶可夢": "寵物小精靈", "沙烏地阿拉伯": "沙特阿拉伯"},
    # Taiwan text carrying Hong Kong's renderings.
    "tw": {"特朗普": "川普", "奧巴馬": "歐巴馬", "克林頓": "柯林頓",
           "布殊": "布希", "列根": "雷根", "戴卓爾": "柴契爾",
           "默克爾": "梅克爾", "馬克龍": "馬克宏", "普京": "普丁",
           "澤連斯基": "澤倫斯基", "貝理雅": "布萊爾", "新西蘭": "紐西蘭",
           "意大利": "義大利", "老撾": "寮國", "卡塔爾": "卡達",
           "肯尼亞": "肯亞", "尼日利亞": "奈及利亞", "埃塞俄比亞": "衣索比亞",
           "克羅地亞": "克羅埃西亞", "莫桑比克": "莫三比克", "悉尼": "雪梨",
           "迪拜": "杜拜", "康城影展": "坎城影展", "康城影帝": "坎城影帝", "三藩市": "舊金山",
           "平治": "賓士", "福士": "福斯", "碧咸": "貝克漢",
           "美斯": "梅西", "費達拿": "費德勒", "米高佐敦": "麥可喬丹",
           "星球大戰": "星際大戰", "蜘蛛俠": "蜘蛛人", "鐵甲奇俠": "鋼鐵人",
           "寵物小精靈": "寶可夢", "沙特阿拉伯": "沙烏地阿拉伯"},
}

# High-frequency characters that exist only in Simplified. One of these in a
# Traditional text means the conversion was partial.
SIMPLIFIED_ONLY = (
    "这个们时会说对来国过学发电长开关门问间车东马书华应该网经给结级线统"
    "义业产无为与从众体处备头实宝写军农达边进运还远连选递图团园圆场坏块"
    "声复够夹夺奋奖妇妈宁审导尔尽层属岁岛帅师带帮广庆庄库张归当录总战戏"
    "扩扫扬担挥损换据数断旧显术机杀权条极构标树样桥检楼欢欧气汉汤沟洁济"
    "湾满灭灯灵热营烧爱现环画码确离积称稳简类紧罗习联肠脑脸艺节苏药获蓝"
    "补装见觉计认论设证评识词试诚话语请读课调谈谢财责败货质购贵费资赞赢"
    "赶转轮软轻载输邓邮郑针钟钢钱铁银销锁错键镇闪闻队阴阶际陆陈险难韩页"
    "项顺须顾预领题颜额风飞饭馆验骑鱼鲜鸟鸡麦齐龄龙纪约纸细终绝络续维编"
    "练纳纯综缩绍绩缴讲记访许译询详诉谓诸谋谱贤贫贺赛贸赏赖赚贴赋贷账赠"
    "较辆辑辉闭闲阅闹阔铺铜链锐铃饮饰饱饼观规视览凤凭击刘则剑办务动劳势"
    "医区单卫厂厅历压厌厉叶号吗员听启吨执壮壶奉妆孙宠宪寻尘岂岭巩庙废异"
    "弃弯彻径忆态怀怜恋恳惊惧惯扑拟拢择挂挤据掷揽摄摆敌旧晓暂杀枪栋残欢"
)
# A Simplified-to-Traditional conversion picks the wrong character when one
# Simplified form maps to several Traditional ones. Every left-hand string is
# made of valid Traditional characters, so nothing above catches these.
CONVERSION_ARTIFACTS = [
    # 后 (empress) standing in for 後 (after)
    ("以后", "以後"), ("然后", "然後"), ("最后", "最後"), ("之后", "之後"),
    ("后面", "後面"), ("后來", "後來"), ("背后", "背後"), ("今后", "今後"),
    ("稍后", "稍後"), ("前后", "前後"), ("隨后", "隨後"), ("事后", "事後"),
    ("幕后", "幕後"), ("后續", "後續"), ("后期", "後期"), ("后果", "後果"),
    # 干 (interfere) standing in for 乾 (dry) or 幹 (do, trunk)
    ("干淨", "乾淨"), ("干燥", "乾燥"), ("干脆", "乾脆"), ("干杯", "乾杯"),
    ("餅干", "餅乾"), ("干旱", "乾旱"), ("干活", "幹活"), ("能干", "能幹"),
    ("骨干", "骨幹"), ("主干", "主幹"),
    # 髮 (hair) standing in for 發 (issue, develop), and the reverse
    ("髮展", "發展"), ("髮生", "發生"), ("髮現", "發現"), ("髮佈", "發佈"),
    ("髮布", "發布"), ("開髮", "開發"), ("髮送", "發送"), ("髮表", "發表"),
    ("頭發", "頭髮"), ("理發", "理髮"), ("發型", "髮型"),
    # 面 (face) standing in for 麵 (noodle, flour)
    ("面條", "麵條"), ("拉面", "拉麵"), ("面包", "麵包"), ("泡面", "泡麵"),
    ("面粉", "麵粉"),
    # 松 (pine) standing in for 鬆 (loose)
    ("放松", "放鬆"), ("輕松", "輕鬆"), ("松開", "鬆開"), ("松散", "鬆散"),
    # 表 (surface) standing in for 錶 (watch)
    ("手表", "手錶"), ("鐘表", "鐘錶"),
    # 制 (system) standing in for 製 (manufacture)
    ("制造", "製造"), ("制作", "製作"), ("制品", "製品"), ("複制", "複製"),
    ("研制", "研製"),
    # 只 (only) standing in for 隻 (counter)
    ("一只", "一隻"), ("兩只", "兩隻"), ("幾只", "幾隻"), ("只身", "隻身"),
    # 系 standing in for 係 (relation) or 繫 (tie)
    ("聯系", "聯繫"), ("關系", "關係"), ("維系", "維繫"),
    # 准 (permit) standing in for 準 (standard, accurate)
    ("標准", "標準"), ("准確", "準確"), ("准備", "準備"), ("精准", "精準"),
    ("水准", "水準"),
    # 征 (expedition) standing in for 徵 (sign, levy)
    ("特征", "特徵"), ("象征", "象徵"), ("征求", "徵求"), ("征收", "徵收"),
    ("征兆", "徵兆"), ("征信", "徵信"),
    # 志 (will) standing in for 誌 (record, journal)
    ("雜志", "雜誌"), ("日志", "日誌"), ("標志", "標誌"),
    # 采 (bearing) standing in for 採 (pick, adopt)
    ("采取", "採取"), ("采用", "採用"), ("采購", "採購"), ("采訪", "採訪"),
    ("采集", "採集"),
    # 舍 (dwelling) standing in for 捨 (give up)
    ("舍不得", "捨不得"), ("取舍", "取捨"), ("舍棄", "捨棄"),
    # 游 (swim) standing in for 遊 (travel, play)
    ("旅游", "旅遊"), ("游客", "遊客"), ("游戲", "遊戲"), ("游行", "遊行"),
    # 划 (row a boat) standing in for 劃 (delineate, plan)
    ("計划", "計劃"), ("規划", "規劃"), ("划分", "劃分"),
    # 斗 (dipper) standing in for 鬥 (fight)
    ("戰斗", "戰鬥"), ("奮斗", "奮鬥"), ("斗爭", "鬥爭"),
    # 于 for 於, 咸 for 鹹, 郁 for 鬱, 涂 for 塗, 板 for 闆, 谷 for 穀
    ("由于", "由於"), ("關于", "關於"), ("對于", "對於"), ("等于", "等於"),
    ("終于", "終於"), ("至于", "至於"), ("在于", "在於"), ("位于", "位於"),
    ("屬于", "屬於"), ("咸水", "鹹水"), ("憂郁", "憂鬱"), ("郁悶", "鬱悶"),
    ("涂料", "塗料"), ("涂抹", "塗抹"), ("老板", "老闆"), ("谷物", "穀物"),
]
# Same word, two regional standards: (Taiwan form, Hong Kong form). Taiwan
# writes 裡 and 著, Hong Kong writes 裏 and 着 — 常用字字形表 for Hong Kong,
# 教育部 standard for Taiwan.
#
# 著 is only listed as bigrams because the bare character is not a fork: 著作,
# 顯著 and 著名 are 著 on both sides. Only the aspect particle differs, so
# flagging the character alone would fire on ordinary Hong Kong prose.
REGION_GLYPHS = [
    ("裡", "裏"), ("身分", "身份"),
    ("隨著", "隨着"), ("接著", "接着"), ("跟著", "跟着"), ("看著", "看着"),
    ("帶著", "帶着"), ("想著", "想着"), ("拿著", "拿着"), ("等著", "等着"),
    ("試著", "試着"), ("沿著", "沿着"), ("對著", "對着"), ("朝著", "朝着"),
    ("活著", "活着"), ("坐著", "坐着"), ("站著", "站着"), ("靠著", "靠着"),
    ("留著", "留着"), ("忙著", "忙着"), ("急著", "急着"), ("趕著", "趕着"),
    ("照著", "照着"), ("順著", "順着"), ("藉著", "藉着"), ("撐著", "撐着"),
]
# Forks where only one direction can be flagged. 計畫 is Taiwan's standard and
# reads Taiwanese in Hong Kong prose, but Taiwanese writers use 計劃 freely too,
# so the mirror rule would fire on ordinary Taiwanese writing. Anything listed
# here as {wrong: right} is checked for that region only.
REGION_GLYPHS_ONEWAY = {
    "hk": [("計畫", "計劃")],
    "tw": [],
}
# 您 does not exist in Cantonese. One character is enough to place a Hong Kong
# text's source on the mainland, which makes it the cheapest tell in the
# language. Taiwan is the opposite case — 您好 is ordinary Taiwanese business
# courtesy — so this is deliberately not symmetric.
HK_POLITE_PRONOUN = "您"
DE_MODAL_PARTICLES = [
    "doch", "halt", "mal", "eben", "ja", "schon", "wohl", "eigentlich",
    "übrigens",
]

# Titles are always followed by a name, so their period never ends a sentence.
ABBREV_TITLE = {
    "en": ["mr", "mrs", "ms", "dr", "prof", "rev", "hon", "sr", "jr", "st",
           "fig", "vol", "no", "dept", "approx"],
    "de": ["dr", "prof", "hr", "fr", "st", "nr", "abb", "bd", "ca"],
}
# These can also close a sentence ("...at 4 p.m. The team left"), so their
# period is only hidden when the next word is not capitalized.
ABBREV_OTHER = {
    "en": ["vs", "etc", "e.g", "i.e", "cf", "al", "inc", "ltd", "co", "corp",
           "est", "min", "max", "a.m", "p.m", "ph.d", "jan", "feb", "mar",
           "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
           "mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    "de": ["z.b", "u.a", "d.h", "bzw", "evtl", "ggf", "inkl", "exkl", "vgl",
           "usw", "etc", "mio", "mrd", "jh", "bspw", "allg", "engl", "dt",
           "s.o", "s.u", "o.g", "jan", "feb", "mär", "apr", "jun", "jul",
           "aug", "sep", "okt", "nov", "dez"],
}

DOT = "\x00"  # stand-in for a period that does not end a sentence
CJK = r"㐀-䶿一-鿿豈-﫿"
WORD_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+(?:['’\-][0-9A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+)*")
CJK_RE = re.compile(f"[{CJK}]")

sections = []
flags = []


def section(title):
    sections.append({"title": title, "lines": []})
    print(f"\n{title}")


def report(ok, message):
    if not ok:
        flags.append({"section": sections[-1]["title"] if sections else "",
                      "message": message})
    if sections:
        sections[-1]["lines"].append({"ok": ok, "message": message})
    print(f"{'  ·' if ok else '  ⚠'} {message}")


def note(message):
    if sections:
        sections[-1]["lines"].append({"ok": True, "message": message})
    print(f"  · {message}")


def is_cjk(ch):
    return bool(CJK_RE.match(ch))


def fold(text):
    """Normalize typography so matching is not defeated by smart quotes."""
    return (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("‑", "-").replace(" ", " ").lower())


def strip_markdown(text):
    """Drop markdown scaffolding that is not prose, keep the prose."""
    stats = {"code": 0, "heading": 0, "table": 0}
    text, stats["code"] = re.subn(
        r"(?ms)^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$", "", text)
    text = re.sub(r"(?s)<!--.*?-->", "", text)

    kept = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|"):
            stats["table"] += 1
            continue
        if re.match(r"^#{1,6}\s", stripped):
            stats["heading"] += 1
            kept.append("")  # a heading is a break, not a sentence
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            continue
        kept.append(line)
    text = "\n".join(kept)

    text = re.sub(r"(?m)^[ \t]*>+[ \t]?", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # A list item is its own sentence; give it a terminator so it does not
    # merge with the line below and distort every length statistic.
    out = []
    for line in text.split("\n"):
        m = re.match(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+(.*)$", line)
        if m:
            body = m.group(2).rstrip()
            if body and body[-1] not in ".!?:;。！？…":
                body += "。" if CJK_RE.search(body) else "."
            out.append(body)
        else:
            out.append(line)
    return "\n".join(out), stats


def detect_chinese_region(text):
    """Simplified, or Traditional for which side?

    Region markers are read straight off REGION_FOREIGN so there is one source
    of truth: the words foreign to Taiwan are exactly the words native to Hong
    Kong. On a tie this returns "tw" and main() says the guess was a coin toss,
    because a wrong region is worse than an explicit --lang.
    """
    if any(c in SIMPLIFIED_ONLY for c in text):
        return "zh"
    hk = sum(text.count(t) for t in REGION_FOREIGN["tw"]) + text.count("裏")
    tw = sum(text.count(t) for t in REGION_FOREIGN["hk"]) + text.count("裡")
    return "hk" if hk > tw else "tw"


def detect_lang(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    cjk = sum(1 for c in letters if is_cjk(c))
    if cjk / len(letters) > 0.2:
        return detect_chinese_region(text)
    de_hits = len(re.findall(
        r"\b(der|die|das|und|nicht|ist|ein|eine|mit|für|auf|werden|wird)\b",
        text.lower()))
    en_hits = len(re.findall(
        r"\b(the|and|of|to|is|that|for|with|was|are|this|not)\b",
        text.lower()))
    return "de" if de_hits > en_hits else "en"


def split_paragraphs(text):
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]


def protect_periods(text, lang):
    """Hide periods that belong to abbreviations, decimals, and initials."""
    hide = lambda m: m.group(0).replace(".", DOT)  # noqa: E731
    for abbr in ABBREV_TITLE.get(lang, []):
        text = re.sub(rf"(?<![0-9A-Za-zÀ-ÖØ-öø-ÿ]){re.escape(abbr)}\.",
                      hide, text, flags=re.I)
    for abbr in ABBREV_OTHER.get(lang, []):
        text = re.sub(
            rf"(?<![0-9A-Za-zÀ-ÖØ-öø-ÿ]){re.escape(abbr)}\.(?!\s+[A-ZÄÖÜ])",
            hide, text, flags=re.I)
    text = re.sub(r"(?<=\d)\.(?=\d)", DOT, text)
    text = re.sub(r"(?<![0-9A-Za-zÀ-ÖØ-öø-ÿ])([A-ZÄÖÜ])\.", rf"\1{DOT}", text)
    return text


def split_sentences(text, lang):
    if lang in CJK_LANGS:
        parts = re.split(r"[。！？…]+", text)
    else:
        protected = protect_periods(text, lang)
        parts = re.split(r"(?<=[.!?…])[\"'”’)\]]*\s+", protected)
        parts = [p.replace(DOT, ".") for p in parts]
    return [s.strip() for s in parts if s.strip()]


def sentence_length(sentence, lang):
    if lang in CJK_LANGS:
        # Count Han characters plus each run of Latin/digits as one unit, so
        # mixed-script technical Chinese is not systematically undercounted.
        cjk = len(CJK_RE.findall(sentence))
        latin = len(WORD_RE.findall(re.sub(f"[{CJK}]", " ", sentence)))
        return cjk + latin
    return len(WORD_RE.findall(sentence))


def inflections(word, lang):
    """Regex alternatives for the ordinary English/German inflections."""
    if " " in word or "-" in word:
        return re.escape(word)
    stem = re.escape(word)
    if lang == "de":
        # Covers adjective declension (innovative/-en/-er/-es) and the common
        # verb endings, which is why some entries are stems (unterstreich).
        return stem + r"(?:e|en|em|er|es|n|s|t|te|ten|end)?"
    if word.endswith("e"):
        return re.escape(word[:-1]) + r"(?:e|es|ed|ing)"
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        return re.escape(word[:-1]) + r"(?:y|ies|ied|ying)"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return stem + r"(?:es|ed|ing)?"
    return stem + r"(?:s|ed|ing)?"


def count_hits(text, words, phrases, lang):
    hits = {}
    for word in words:
        if lang in CJK_LANGS:
            n = text.count(word)
            if n:
                hits[word] = hits.get(word, 0) + n
            continue
        for found in re.findall(rf"\b{inflections(word, lang)}\b", text):
            hits[found] = hits.get(found, 0) + 1
    for phrase in phrases:
        n = text.count(phrase)
        if n:
            hits[phrase] = hits.get(phrase, 0) + n
    return sorted(hits.items(), key=lambda x: (-x[1], x[0]))


def check_rhythm(sentences, lang):
    section("Rhythm")
    lengths = [sentence_length(s, lang) for s in sentences]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 4:
        note("too few sentences for rhythm statistics")
        return
    mean = statistics.mean(lengths)
    stdev = statistics.pstdev(lengths)
    # Judge the printed value, so the verdict never contradicts the number.
    cv = round(stdev / mean, 2) if mean else 0
    unit = "chars" if lang in CJK_LANGS else "words"
    note(f"{len(lengths)} sentences, mean {mean:.1f} {unit}, "
         f"min {min(lengths)}, max {max(lengths)}")
    if len(lengths) < 8:
        # CV over four or five samples is noise, and a three-paragraph product
        # announcement was being told its rhythm was machine-uniform on it.
        note(f"sentence-length variation (CV {cv:.2f}) — too few sentences to "
             "judge; treat as informational")
    else:
        report(cv >= 0.35,
               f"sentence-length variation (CV {cv:.2f}) — "
               + ("healthy spread" if cv >= 0.35 else
                  "uniform lengths; the most consistent statistical AI tell"))
    if len(lengths) >= 8:
        # Taiwan's baseline sentence is longer and looser, and its catalog
        # revokes 短句連發 outright as 大陸公眾號體 — demanding a sub-8-character
        # sentence made one rewrite manufacture a six-character one purely to
        # clear the check. Ask Taiwan for a shorter sentence, not a clipped one.
        if lang == "tw":
            short_cut, long_cut = 12, 45
        elif lang in CJK_LANGS:
            short_cut, long_cut = 8, 40
        else:
            short_cut, long_cut = 6, 25
        report(min(lengths) < short_cut,
               f"has a short sentence (<{short_cut} {unit})" if
               min(lengths) < short_cut else
               f"no sentence under {short_cut} {unit} — mix in a short one")
        if len(lengths) >= 12:
            report(max(lengths) > long_cut,
                   f"has a long sentence (>{long_cut} {unit})" if
                   max(lengths) > long_cut else
                   f"no sentence over {long_cut} {unit} — let one breathe")
        else:
            note(f"longest sentence {max(lengths)} {unit} — short document, "
                 "not asked for a long sentence")


def check_openers(sentences, lang):
    if lang in CJK_LANGS or len(sentences) < 5:
        return
    section("Sentence openers")
    firsts = []
    for s in sentences:
        m = re.match(r"[^A-Za-zÀ-ÖØ-öø-ÿ]*([A-Za-zÀ-ÖØ-öø-ÿ']+)", s)
        if m:
            firsts.append(m.group(1).lower())
    if not firsts:
        return
    top, count = max(((w, firsts.count(w)) for w in set(firsts)),
                     key=lambda x: x[1])
    share = count / len(firsts)
    report(share <= 0.3 or count < 3,
           f'most common opener "{top}" starts {count}/{len(firsts)} '
           f"sentences" + ("" if share <= 0.3 or count < 3
                           else " — vary the openings"))


def check_serial_enumeration(sentences, lang):
    if lang != "en":
        return
    section("Serial enumeration")
    crowded = [sentence for sentence in sentences if sentence.count(",") >= 5]
    word_count = sum(sentence_length(sentence, lang) for sentence in sentences)
    budget = (word_count * 3) // 1000
    report(
        len(crowded) <= budget,
        f"{len(crowded)} sentence(s) contain at least five commas; "
        f"budget is {budget} for {word_count} words"
        + ("" if len(crowded) <= budget else " — group, tabulate, or cut the list"),
    )


def check_paragraphs(paragraphs, lang):
    if len(paragraphs) < 4:
        return
    section("Paragraphs")
    sizes = [len(split_sentences(p, lang)) for p in paragraphs]
    mean = statistics.mean(sizes)
    cv = round(statistics.pstdev(sizes) / mean, 2) if mean else 0
    report(cv >= 0.25,
           f"paragraph sizes {sizes} (CV {cv:.2f}) — "
           + ("varied" if cv >= 0.25
              else "uniform; human paragraphs range from 1 line to 10"))


def check_vocabulary(text, lang):
    section("AI vocabulary")
    words, phrases, watch = VOCAB[lang]
    hits = count_hits(text, words, phrases, lang)
    if hits:
        shown = ", ".join(f"{w} ×{n}" for w, n in hits[:8])
        extra = f" (+{len(hits) - 8} more)" if len(hits) > 8 else ""
        report(len(hits) <= 1 and hits[0][1] <= 1, f"catalog hits: {shown}{extra}")
    else:
        report(True, "no catalog vocabulary found")
    seen = count_hits(text, watch, [], lang)
    if seen:
        note("watchlist (context-dependent, not flagged): "
             + ", ".join(f"{w} ×{n}" for w, n in seen[:8]))
    if lang in CJK_LANGS:
        table = CONNECTIVE_DENSITY["zh" if lang == "zh" else "hant"]
        connectives = [c for c in table if c in text]
        # Scale with length so a long report is not punished for containing
        # what a short one would be. Under 400 characters, three is a crowd.
        budget = max(3, len(text) // 400 + 2)
        report(len(connectives) <= budget,
               f"{len(connectives)} distinct connectives"
               + (" — within range" if len(connectives) <= budget else
                  ": " + "、".join(connectives[:8])
                  + " — no single one is wrong; this many in one text is the "
                    "scaffolding showing"))


def check_punctuation(original, folded, lang, sentences):
    section("Punctuation")
    if lang == "de":
        em = original.count("—")
        report(em == 0,
               "no em-dash (Geviertstrich)" if em == 0 else
               f"{em} Geviertstrich(e) — German uses – with spaces")
        loose = len(re.findall(r"(?<=\S) (?:-|--) (?=\S)", original))
        report(loose == 0,
               "no hyphen used as a dash" if loose == 0 else
               f"{loose} hyphen(s) used as a dash — German uses – with spaces")
        german = original.count("„")
        guillemets = original.count("»") + original.count("«")
        english = original.count("”") + len(
            re.findall(r"(?:^|[\s(\[–—-])“", original, re.M))
        straight = original.count('"')
        if english or straight:
            parts = []
            if english:
                parts.append(f"{english} English curly quote(s)")
            if straight:
                parts.append(f"{straight} straight quote(s)")
            report(False, " and ".join(parts) + " — German prose uses „…“")
        elif german and guillemets:
            report(False, "mixed „…“ and »…« — pick one")
        else:
            report(True, "quotation marks consistent")
    elif lang in CJK_LANGS:
        half = len(re.findall(rf"[{CJK}][,\.;:!\?]", original))
        report(half == 0,
               "no half-width punctuation after Chinese characters"
               if half == 0 else
               f"{half} half-width mark(s) inside Chinese text — "
               "use full-width")
        semis = original.count("；")
        if lang == "tw":
            # The mainland threshold came from a 虎嗅 frequency study. Taiwan's
            # written register is shaped by legal and 公文 drafting and carries
            # more semicolons natively, and no Taiwanese corpus has been run
            # against it — so this reports and does not fail. T15 and C9 both
            # say 分號不必刻意壓低; the checker used to say otherwise.
            note(f"{semis} Chinese semicolon(s) — the mainland threshold is "
                 "not applied to Taiwan; see T15")
        else:
            report(semis <= max(1, len(sentences) // 10),
                   f"{semis} Chinese semicolon(s)" + (
                       "" if semis <= max(1, len(sentences) // 10)
                       else " — AI overuses ；"))
        if lang == "tw":
            # Taiwan is uniform on 「」; “” reads as unconverted mainland text.
            curly = original.count("“") + original.count("”")
            report(curly == 0,
                   "quotation marks use 「」" if curly == 0 else
                   f"{curly} “” quote mark(s) — Taiwan uses 「」")
        elif lang == "hk":
            # Not a defect in Hong Kong, and this took a correction to get
            # right: HK government writing follows the PRC punctuation
            # standard and its own style manual uses “ ”, while the HK press
            # uses 「」. Both are native, so this reports rather than flags —
            # consistency within one text is the only real requirement.
            curly = original.count("“") + original.count("”")
            corner = original.count("「")
            if curly and corner:
                report(False, "mixed “” and 「」 — either is Hong Kong style, "
                              "but pick one and hold it")
            elif curly:
                note(f"{curly} “” quote mark(s) — government register. The "
                     "press uses 「」; both are Hong Kong")
            elif corner:
                note("quotation marks use 「」 — press register")
        elif "“" in original and "「" in original:
            report(False, "mixed “” and 「」 quote styles — pick one")
    else:
        em = original.count("—")
        per_sent = em / max(1, len(sentences))
        report(per_sent <= 0.2,
               f"{em} em-dash(es) across {len(sentences)} sentences" + (
                   "" if per_sent <= 0.2 else " — thin them out"))
        curly_q = original.count("“") + original.count("”")
        straight_q = original.count('"')
        if curly_q and straight_q:
            report(False, "mixed curly and straight quotes — pick one")
        curly_ap = original.count("’")
        straight_ap = len(re.findall(r"(?<=\w)'(?=\w)", original))
        if curly_ap and straight_ap:
            report(False, "mixed curly and straight apostrophes — pick one")


CANTONESE_MARKERS = ["係", "唔", "嘅", "咗", "喺", "啲", "嘢", "佢", "乜",
                     "點解", "而家", "仲", "喐", "冇", "梗係", "睇"]
# Two of those characters are also ordinary standard written Chinese, and
# counting them raw reported clean 書面語 as mixed register: 係 inside 關係 or
# 係數, 仲 inside 仲裁 or 仲介. Subtract the compounds before judging.
# List only the shortest form of each compound: 沒關係 is already counted by
# 關係, so listing both would subtract the same 係 twice. Everything here is
# subtracted — an earlier version hard-coded a second tuple of which entries to
# honour, which silently ignored anything added to this table afterwards.
CANTONESE_EXCEPTIONS = {
    "係": ["關係", "係數", "干係", "幹係", "係屬", "係爭", "純係",
           "確係", "實係"],
    "仲": ["仲裁", "仲介", "仲夏", "仲春", "仲秋", "仲冬", "伯仲",
           "昆仲", "仲尼"],
    "而家": ["然而家"],
    "點解": ["重點解", "觀點解", "論點解", "焦點解", "要點解", "難點解",
             "特點解", "優點解", "缺點解", "地點解"],
    "睇": [],
}


def cantonese_hits(text):
    """Cantonese grammar markers, minus their standard-Chinese homographs."""
    total = 0
    for marker in CANTONESE_MARKERS:
        n = text.count(marker)
        for compound in CANTONESE_EXCEPTIONS.get(marker, []):
            n -= text.count(compound)
        total += max(0, n)
    return total


# Cantonese potential complements, spelled entirely in standard characters.
# 「一樣處理到工作」 is Cantonese syntax that a Simplified/Traditional character
# check is blind to, and it survived a blind benchmark inside a 書面語 press
# release. Only unambiguous items belong here: 做到 and 看到 are standard
# Mandarin and must never be listed.
CANTONESE_SYNTAX = ["處理到", "應付到", "負擔到", "頂到", "捱到", "幫到",
                    "搞得掂", "搞唔掂", "睇唔到", "睇得到", "趕唔切",
                    "買唔起", "食得落", "做唔到", "應付唔到"]


def check_language_flavor(original, folded, lang, sentences):
    if lang == "hk":
        section("Hong Kong flavor (informational)")
        particles = sum(1 for s in sentences if s and s[-1] in HK_PARTICLES)
        canto = cantonese_hits(original)
        register = ("書面粵語" if canto >= 3 else
                    "書面語" if canto == 0 else "mixed")
        note(f"register reads as {register} "
             f"({canto} Cantonese marker(s): 係/唔/嘅/咗/喺…)")
        if register == "mixed":
            note("a few Cantonese markers in otherwise standard prose is the "
                 "unstable middle. Either commit to 粵文 or cut them — half "
                 "and half reads as a writer who could not decide")
        syntax = [t for t in CANTONESE_SYNTAX if t in original]
        if register == "書面語":
            report(not syntax,
                   "no Cantonese potential complements" if not syntax else
                   "Cantonese syntax in 書面語: " + "、".join(syntax[:5])
                   + " — standard characters, Cantonese grammar. 處理到 → "
                     "可以處理")
        elif syntax:
            note("Cantonese potential complements: " + "、".join(syntax[:5])
                 + " — correct in 粵文")
        note(f"sentence-final particles: {particles} — Cantonese particles "
             "(㗎/喎/咩/囉) belong to 書面粵語 only. In a press release, an "
             "internal email or a report they are wrong, and zero is correct")
    elif lang == "tw":
        section("Taiwan flavor (informational)")
        particles = sum(1 for s in sentences if s and s[-1] in TW_PARTICLES)
        note(f"sentence-final particles (喔/耶/啦/欸/齁…): {particles} — "
             "not a quota. Taiwanese prose carries more of them than mainland "
             "prose does, but a 新聞稿 or 公文 carries none. A particle bolted "
             "onto a sentence nobody would say aloud reads worse than none")
    elif lang == "zh":
        section("Chinese flavor (informational)")
        particles = sum(1 for s in sentences if s and s[-1] in ZH_PARTICLES)
        note(f"sentence-final particles (呢/啊/吧/嘛…): {particles} — "
             "not a quota. A particle bolted onto a sentence that was never "
             "spoken (\"辛苦了啊\") reads more artificial than none at all, "
             "and email, announcements and reports are not informal text. "
             "Zero is the right answer more often than not")
    elif lang == "de":
        section("German flavor (informational)")
        n = len(re.findall(
            r"\b(" + "|".join(DE_MODAL_PARTICLES) + r")\b", folded))
        note(f"modal particle hits (doch/halt/mal/eben…): {n} — "
             "zero in informal text is a strong AI tell; "
             "in formal text zero is correct")
    else:
        section("English flavor (informational)")
        short = len(re.findall(
            r"\b(don't|it's|can't|won't|isn't|we're|i'm|didn't|doesn't"
            r"|you're|that's|there's|wasn't|aren't|couldn't|wouldn't"
            r"|they're|we've|i've|let's|he's|she's|hasn't|haven't)\b", folded))
        full = len(re.findall(
            r"\b(do not|it is|cannot|can not|will not|is not|we are|i am"
            r"|did not|does not|you are|that is|there is|was not|are not"
            r"|could not|would not|they are|we have|i have|let us|has not"
            r"|have not)\b", folded))
        note(f"contractions {short} vs full forms {full} — "
             "all-full-forms in casual prose reads machine or lawyer")


# A conversion artefact is reported as an objective error, so a false positive
# here is the most expensive kind the checker can make — and an audit found 17
# of the 108 pairs firing on ordinary correct Traditional Chinese, because the
# wrong sequence also spans the seam between two innocent words: 抑制|作用,
# 相關|系統, 舉手|表決, 若干|活動, 研發|型企業, 山谷|物種. Each entry lists the
# characters that, immediately before the sequence, make it legitimate. The
# scan keeps looking past a guarded hit, so 相關系統 in one sentence does not
# hide 關系我們 in the next.
ARTIFACT_GUARD = {
    "制作": "抑機控限體編", "制造": "體機限控編", "制品": "控限機",
    "能干": "可不未才竟", "干活": "若一", "面包": "方表畫地層局",
    "手表": "舉拱握伸招揮", "鐘表": "時警", "關系": "相有",
    "只身": "不", "一只": "唯統", "發型": "研開外轉",
    "游行": "上下中", "面粉": "牆地表", "研制": "科教",
    "准備": "核批獲", "准確": "核批獲", "谷物": "山峽矽",
    "複制": "重", "主干": "民自", "聯系": "關串",
    "維系": "思三四", "后來": "皇太", "后果": "皇太",
    "后期": "皇太", "后續": "皇太",
}


def artifact_hits(text):
    """Conversion errors, skipping sequences that straddle a word boundary."""
    out = []
    for wrong, right in CONVERSION_ARTIFACTS:
        guard = ARTIFACT_GUARD.get(wrong, "")
        i = text.find(wrong)
        while i != -1:
            if not (guard and i > 0 and text[i - 1] in guard):
                out.append((wrong, right))
                break
            i = text.find(wrong, i + 1)
    return out


REGION_NAME = {"hk": "Hong Kong", "tw": "Taiwan"}


def check_region(original, lang):
    """The pass that makes hk and tw separate languages rather than one.

    A rewrite can be flawless Traditional Chinese, carry no AI tells at all,
    and still land wrong because it reads as written by someone from the other
    side. Vocabulary, transliterations and orthography give that away in the
    first paragraph, and none of the style checks above can see it.
    """
    if lang not in HANT_LANGS:
        return
    here, there = REGION_NAME[lang], REGION_NAME["tw" if lang == "hk" else "hk"]
    section(f"Region ({here} Traditional Chinese)")

    foreign = [(t, original.count(t)) for t in REGION_FOREIGN[lang]
               if t in original]
    report(not foreign,
           f"no {there} vocabulary" if not foreign else
           f"{there} vocabulary: "
           + ", ".join(f"{t} ×{n}" for t, n in sorted(
               foreign, key=lambda x: -x[1])[:8])
           + f" — correct Chinese, wrong side. A {here} reader stops here")

    # Set-phrase provenance. The vocabulary line above only sees nouns, and a
    # region's formulas outlive every noun a rewrite swaps: 共襄盛舉 and 圓滿落幕
    # in a Hong Kong notice, 是次 and 順頌業祺 in a Taiwanese one.
    formulas = [(t, original.count(t)) for t in REGION_FOREIGN_PHRASES[lang]
                if t in original]
    report(not formulas,
           f"no {there} set-phrases" if not formulas else
           f"{there} set-phrase(s): "
           + ", ".join(f"{t} ×{n}" for t, n in sorted(
               formulas, key=lambda x: -x[1])[:8])
           + " — the nouns were converted and the skeleton was not")

    mainland = [(t, original.count(t)) for t in MAINLAND_ONLY if t in original]
    report(not mainland,
           "no mainland-only vocabulary" if not mainland else
           "mainland vocabulary: "
           + ", ".join(f"{t} ×{n}" for t, n in sorted(
               mainland, key=lambda x: -x[1])[:8])
           + " — converted characters, unconverted words")

    bad_names = [(w, r) for w, r in TRANSLIT_FOREIGN[lang].items()
                 if w in original]
    report(not bad_names,
           "no foreign transliterations" if not bad_names else
           f"{there} transliteration(s): "
           + ", ".join(f"{w}→{r}" for w, r in bad_names[:6])
           + " — the single fastest tell there is")

    simplified = sorted({c for c in original if c in SIMPLIFIED_ONLY})
    report(not simplified,
           "no Simplified characters" if not simplified else
           f"{len(simplified)} Simplified character(s): "
           + "".join(simplified[:12]) + " — the conversion was partial")

    artifacts = artifact_hits(original)
    report(not artifacts,
           "no one-to-many conversion errors" if not artifacts else
           "conversion error(s): "
           + ", ".join(f"{w}→{r}" for w, r in artifacts[:6])
           + " — valid characters, wrong meaning")

    mine, theirs = (0, 1) if lang == "tw" else (1, 0)
    wrong = [(pair[theirs], pair[mine]) for pair in REGION_GLYPHS
             if pair[theirs] in original]
    wrong += [(w, r) for w, r in REGION_GLYPHS_ONEWAY[lang] if w in original]
    used = sum(1 for pair in REGION_GLYPHS if pair[mine] in original)
    if wrong or used:
        report(not wrong,
               f"regional glyphs follow the {here} standard" if not wrong else
               f"{here} writes " + ", ".join(f"{r} not {w}"
                                             for w, r in wrong[:5])
               + (" (mixed with the correct form elsewhere)" if used else ""))

    if lang == "hk":
        polite = original.count(HK_POLITE_PRONOUN)
        report(not polite,
               "no 您" if not polite else
               f"您 ×{polite} — Cantonese has no 您. One of them places the "
               "source on the mainland; write 你")


# ---------------------------------------------------------------- fidelity --
# Words that begin a sentence or are grammatically capitalized, so seeing them
# capitalized proves nothing about them being a name.
CAP_STOPWORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "he", "her",
    "his", "i", "if", "in", "is", "it", "its", "my", "no", "not", "of", "on",
    "or", "our", "she", "so", "that", "the", "their", "then", "there", "they",
    "this", "to", "we", "what", "when", "where", "which", "who", "why",
    "with", "yes", "you", "your", "every", "most", "some", "one", "two",
    "der", "die", "das", "und", "wir", "sie", "ich", "es", "ein", "eine",
    "der", "den", "dem", "aber", "auch", "nicht", "wenn", "dann", "hier",
}
ATTRIBUTION_RE = {
    "en": r"\b(according to|observers?|experts?|critics?|analysts?|"
          r"researchers?|stud(?:y|ies)|survey|industry reports?|"
          r"sources?|cited|reported|said|says|argues?|claims?|"
          r"noted|per the)\b",
    "de": r"\b(laut|zufolge|Beobachter|Branchenexperten|Expert(?:en|innen)|"
          r"Kritiker|Studien? (?:zeigen|zeigt)|Forschung zeigt|berichtet|"
          r"sagte|sagt)\b",
    # 據 and 根據 used to be listed bare, which matched inside 依據, 數據 and
    # 佔據 — a product sentence reading 依據使用者的偏好 was read as an
    # attributed claim. Only the collocations that actually credit a source.
    "zh": r"(据说|据报|据悉|据称|据传|据了解|据统计|据调查|据报道|"
          r"表示|认为|指出|业内人士|专家|观察人士|研究表明|"
          r"报道称|调查显示|数据显示|消息人士|知情人士)",
    "hk": r"(據說|據報|據悉|據稱|據傳|據了解|據統計|據調查|據報道|"
          r"表示|認為|指出|業內人士|專家|觀察人士|研究表明|"
          r"報道稱|調查顯示|數據顯示|消息人士|知情人士|有指)",
    "tw": r"(據說|據報|據悉|據稱|據傳|據了解|據統計|據調查|據報導|"
          r"表示|認為|指出|業界人士|專家|觀察人士|研究顯示|"
          r"報導指出|調查顯示|數據顯示|外界認為|傳出)",
}
COMMITMENT_RE = {
    "en": r"\b(we(?:'ll| will| are going to| shall)|i(?:'ll| will)|"
          r"you(?:'ll| will) (?:receive|get|see))\b",
    "de": r"\b(wir werden|ich werde|wir kümmern uns|wir melden uns)\b",
    "zh": r"(我们[^，。！？]{0,6}会|我们将|我会|我将|接下来会|后续会|今后会|今后将|"
          r"未来会|未来将|将继续|将持续)",
    "hk": r"(我們[^，。！？]{0,6}會|我們將|我會|我將|稍後會|其後會|後續會|接下來會|日後會|"
          r"日後將|將繼續|將持續|未來會|未來將)",
    "tw": r"(我們[^，。！？]{0,6}會|我們將|我會|我將|接下來會|之後會|未來會|未來將|"
          r"後續會|日後會|將繼續|將持續)",
}
# 我們會 and 我們將 are the same promise, and comparing the matched strings
# made a rewrite that reworded one into the other look like a new commitment
# the original never made. The skill calls fidelity warnings non-negotiable, so
# a false positive here forces an edit made purely to dodge a regex. Compare
# what kind of promise it is instead of which words carry it.
COMMITMENT_CLASS = [
    ({"我们会", "我们将", "我会", "我将", "我們會", "我們將", "我會", "我將",
      "後續會", "后续会",
      "wir werden", "ich werde", "wir kümmern uns", "wir melden uns",
      "we'll", "we will", "we are going to", "we shall", "i'll", "i will"},
     "first person"),
    ({"接下来会", "后续会", "今后会", "今后将", "未来会", "未来将",
      "将继续", "将持续", "接下來會", "之後會", "未來會", "未來將",
      "後續會", "日後會", "日後將", "將繼續", "將持續", "稍後會", "其後會"},
     "future"),
    ({"you'll receive", "you will receive", "you'll get", "you will get",
      "you'll see", "you will see"}, "second person"),
]


def commitment_classes(text, lang):
    found = set()
    for raw in re.findall(COMMITMENT_RE[lang], text, re.I):
        token = raw.lower()
        for members, name in COMMITMENT_CLASS:
            if token in members:
                found.add(name)
                break
        else:
            # 我們下星期會 is the same class as 我們會 with an adverb wedged in.
            if re.match(r"^(我們|我们|我)", token) and token[-1] in "會会將将":
                found.add("first person")
            else:
                found.add(token)
    return found
# Absolutes and totalising words. Present in the rewrite but not the source
# means the rewrite raised the stakes on its own.
SEVERITY = {
    "en": ["nothing", "never", "always", "everyone", "nobody", "completely",
           "entirely", "totally", "catastrophic", "disaster", "all of",
           "every single", "zero", "no one", "worst", "impossible"],
    "de": ["nichts", "nie", "niemals", "immer", "jeder", "niemand", "völlig",
           "komplett", "katastrophal", "unmöglich", "schlimmste"],
    "zh": ["完全", "彻底", "从来没有", "永远", "所有人", "没有人", "灾难",
           "最差", "不可能", "全部", "整个", "根本", "所有"],
    "hk": ["完全", "徹底", "從來沒有", "永遠", "所有人", "沒有人", "冇人",
           "災難", "最差", "不可能", "全部", "一律", "整個", "根本", "所有",
           "冇晒", "死晒", "爆晒"],
    # Taiwanese prose carries a high baseline of intensifiers, so a rewrite
    # drifts upward without anybody deciding to. Catalog pattern 44 names these
    # explicitly; the checker used to carry only 根本 out of the whole set.
    "tw": ["完全", "徹底", "從來沒有", "永遠", "所有人", "沒有人", "災難",
           "最差", "不可能", "全部", "整個", "根本", "所有", "有夠", "極度",
           "崩潰", "掛掉"],
}


# Swapping one quantifier for a synonym is not an escalation. 所有的社交軟件
# becoming 全部刪掉 used to be reported as raised severity, which teaches a
# writer to avoid an ordinary word. Only a jump the source did not make counts.
SEVERITY_CLASSES = [
    {"所有", "所有人", "全部", "整個", "整个", "一律", "everyone",
     "all of",
     "every single", "jeder"},
    {"完全", "彻底", "徹底", "根本", "completely", "entirely", "totally",
     "völlig", "komplett"},
    {"從來沒有", "从来没有", "永遠", "永远", "never", "nie", "niemals"},
    {"沒有人", "没有人", "冇人", "nobody", "no one", "niemand"},
    {"災難", "灾难", "崩潰", "掛掉", "catastrophic", "disaster",
     "katastrophal"},
]


def severity_escalations(source, output, lang):
    low, src_low = output.lower(), source.lower()
    out = []
    for word in SEVERITY[lang]:
        if word not in low or word in src_low:
            continue
        peers = next((c for c in SEVERITY_CLASSES if word in c), None)
        if peers and any(p in src_low for p in peers):
            continue
        out.append(word)
    return out


CJK_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# Require a counter or unit after the numeral, or 一 alone turns 這一區 and
# 一樣 into figures. 一 by itself stays out even with a counter: 一個 is an
# article far more often than a quantity anyone is checking.
CJK_UNITS = "個點時分秒天日週月年次家名人位間隻台部件套成倍元度級層項條張份種" \
            "類步輪季期章節里米克斤噸萬千百億"
CJK_NUM_RE = re.compile(
    rf"(?<![〇零一二兩三四五六七八九十百千萬])"
    rf"([〇零一二兩三四五六七八九十百千萬]+)(?=[{CJK_UNITS}])")


def cjk_number(text):
    """三十五 -> 35. Returns None for anything that is not a plain numeral."""
    if not text or any(c not in CJK_DIGITS and c not in "十百千萬" for c in text):
        return None
    total, section, digit = 0, 0, 0
    for char in text:
        if char in CJK_DIGITS:
            digit = CJK_DIGITS[char]
        elif char == "十":
            section += (digit or 1) * 10
            digit = 0
        elif char == "百":
            section += (digit or 1) * 100
            digit = 0
        elif char == "千":
            section += (digit or 1) * 1000
            digit = 0
        elif char == "萬":
            total += (section + digit or 1) * 10000
            section = digit = 0
    return total + section + digit


CONTRACTION_RE = re.compile(r"['’](ve|d|ll|s|m|re|t)$", re.I)

# Chinese has no capitalization, so the English name-detection trick has no
# equivalent and this pass used to be skipped outright for zh, hk and tw —
# meaning "no names in the rewrite that are absent from the original" printed
# unconditionally and the fabricated-name gate did nothing in three of the five
# skills. Chinese does mark proper nouns structurally instead: institutions,
# places and titled people all end or begin with a closed set of morphemes.
# Matching on that suffix rather than on the name itself keeps the precision a
# gate needs — a candidate has to look like an organisation, not merely be an
# unfamiliar word.
CJK_ORG_SUFFIX = ("公司", "集團", "銀行", "大學", "學院", "中學", "小學",
                  "醫院", "協會", "學會", "基金會", "研究院", "研究所",
                  "委員會", "事務所", "交易所", "報社", "電視台", "航空",
                  "酒店", "百貨", "書院", "教會", "工會", "商會", "政府")
CJK_PLACE_SUFFIX = ("特別行政區", "自治區", "縣", "省", "州", "鎮", "村",
                    "島", "區")
CJK_TITLE = ("先生", "女士", "小姐", "教授", "博士", "醫生", "律師", "總監",
             "經理", "主任", "主席", "部長", "局長", "署長", "校長",
             "執行長", "行政總裁", "理事長", "董事長", "總裁", "議員")
# Generic compounds that end in an organisation morpheme without naming one.
CJK_NAME_STOPWORDS = {
    "本公司", "貴公司", "該公司", "母公司", "子公司", "分公司", "有限公司",
    "股份有限公司", "上市公司", "科技公司", "保險公司", "本集團", "該集團",
    "中央銀行", "本協會", "該協會", "本委員會", "各大學", "本大學", "該大學",
    "私家醫院", "公立醫院", "本醫院", "該醫院", "特別行政區", "行政區",
    "本地區", "該地區", "各地區", "多個地區", "本研究所", "該研究所",
}
CJK_RUN_RE = re.compile(rf"[{CJK}]+")
# No proper noun contains these, so a candidate that swallowed one has run past
# the start of the name and into the sentence around it. Kept to grammatical
# particles only: 中, 是, 有, 為, 明, 會 and friends all occur inside real names
# (中國銀行, 明基電通, 商會), so excluding them would blind the pass instead.
CJK_NAME_BOUNDARY = set("的與和及或了我你他她們就也都而但並把被讓使這那每在"
                        "該此其將已卻仍很更最又再另則因所若雖且於乎嗎呢吧是"
                        "各慢漸終開始繼續學會知道覺得變成成為")


# A personal name next to a title is only recognisable by its surname —
# without one, 理事長表示會如期上線 hands back 表示會 as a person.
CJK_SURNAMES = set(
    "王李張劉陳楊黃趙吳周徐孫馬朱胡郭何高林羅鄭梁謝宋唐許韓馮鄧曹彭曾蕭"
    "田董袁潘蔣蔡余杜葉程蘇魏呂丁任沈姚盧姜崔鍾譚陸汪范金石廖賈夏韋方白"
    "鄒孟熊秦邱江尹薛段雷侯龍史陶黎賀顧毛郝龔邵萬錢嚴戴莫孔湯歐洪紀翁"
)


def _keep(cand):
    return (cand not in CJK_NAME_STOPWORDS
            and not any(c in CJK_NAME_BOUNDARY for c in cand))


def _keep_person(cand):
    return _keep(cand) and cand[0] in CJK_SURNAMES


def cjk_proper_nouns(text):
    """Institution, place and titled-person names, by structural marker.

    Deliberately narrow. Anything that does not carry one of the markers is not
    collected at all, so an invented bare personal name ("小明說⋯") still slips
    through — catalog pattern 43 covers that in prose. Missing a name is a
    smaller failure than telling a writer their own company is fabricated.

    Overlapping widths are all kept rather than picking one, because the caller
    compares by containment: 觀光協會 in the rewrite and 台灣觀光協會 in the
    source have to recognise each other.
    """
    found = set()
    for run in CJK_RUN_RE.findall(text):
        for suffix in CJK_ORG_SUFFIX + CJK_PLACE_SUFFIX:
            start = 0
            while (i := run.find(suffix, start)) >= 0:
                start = i + 1
                for width in (2, 3, 4):
                    if i - width < 0:
                        break
                    cand = run[i - width:i + len(suffix)]
                    if _keep(cand):
                        found.add(cand)
        for title in CJK_TITLE:
            start = 0
            while (i := run.find(title, start)) >= 0:
                start = i + 1
                # Chinese puts the name on either side of the title:
                # 王大明先生, 理事長王大明.
                for width in (2, 3):
                    before = run[i - width:i] if i - width >= 0 else ""
                    if before and _keep_person(before):
                        found.add(before)
                    after = run[i + len(title):i + len(title) + width]
                    if len(after) == width and _keep_person(after):
                        found.add(after)
    return found


def fidelity_tokens(text, lang, generous=False):
    """Names, numbers and dates, as comparable normalized tokens.

    generous=True also accepts sentence-initial capitals. Use it on the
    source so a name that happens to open a sentence there ("Stack Overflow
    provided...") still counts as known; use it off on the rewrite so an
    ordinary word opening a sentence is not mistaken for an invented name.

    Known limitation: an invented name that opens a sentence in the rewrite
    ("Acme rebuilt the flow.") is not flagged, because nothing distinguishes
    it from an ordinary capitalized opener without a dictionary. False
    positives are worse than misses in a gate, so this errs toward silence;
    catalog pattern 43 covers the case in prose.
    """
    numbers = set()
    for raw in re.findall(r"\d[\d,]*(?:[.:]\d+)?%?", text):
        n = raw.rstrip(".,").replace(",", "")
        if n:
            numbers.add(n)
            numbers.add(n.rstrip("%"))
    if lang in CJK_LANGS:
        # Chinese prose writes its quantities in Chinese numerals, so a text
        # like 三個星期，凌晨兩點至六點 contains no ASCII digit at all and the
        # figure check used to run on an empty set — inert exactly where it
        # was needed. Both forms normalise to the same token, which also stops
        # 兩點 → 2 點 being reported as an invented figure.
        for raw in CJK_NUM_RE.findall(text):
            if raw == "一":
                continue
            value = cjk_number(raw)
            if value is not None:
                numbers.add(str(value))
    names = set()
    if lang in CJK_LANGS:
        names |= cjk_proper_nouns(text)
    else:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][\w'’\-]*", sentence)
            for i, w in enumerate(words):
                if not w[0].isupper() or (i == 0 and not generous):
                    continue
                stem = CONTRACTION_RE.sub("", w).lower()
                if not stem or stem in CAP_STOPWORDS:
                    continue
                names.add(stem)
    return names, numbers


def source_acronyms(source):
    """"artificial intelligence" in the source licenses "AI" in the rewrite."""
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", source)
    out = set()
    for size in (2, 3, 4):
        for i in range(len(words) - size + 1):
            run = words[i:i + size]
            if all(w.lower() not in CAP_STOPWORDS for w in run):
                out.add("".join(w[0] for w in run).lower())
    return out


def orphaned_claims(source, output, lang):
    """Attributed claims in the source that survive in the rewrite unattributed.

    Dropping an attribution is only theft if the claim comes with it. A
    rewrite that cuts "observers have cited X as a barrier" outright is doing
    exactly what the catalog asks, and must not be flagged for it.
    """
    attr = re.compile(ATTRIBUTION_RE[lang], re.I)
    out_low = output.lower()
    out_sentences = [s.lower() for s in split_sentences(output, lang)]
    orphans = []
    for sentence in split_sentences(source, lang):
        if not attr.search(sentence):
            continue
        body = attr.sub(" ", sentence)
        if lang in CJK_LANGS:
            # Bigrams, not whole runs: 這一 becoming 這個 used to break the
            # entire run and let a lightly reworded claim through, so the
            # check only ever fired on text nobody had rewritten.
            terms = []
            for run in re.findall(rf"[{CJK}]{{2,}}", body):
                terms += [run[i:i + 2] for i in range(len(run) - 1)]
            terms = sorted(set(terms))
        else:
            terms = [w.lower() for w in WORD_RE.findall(body)
                     if len(w) > 3 and w.lower() not in CAP_STOPWORDS]
        if not terms:
            continue
        kept = sum(1 for t in terms if t in out_low)
        if kept / len(terms) < 0.5:
            continue
        # The claim survived. Ask whether *the sentences carrying it* credit
        # anyone — not whether the rewrite credits anyone anywhere. Testing the
        # whole document meant a single unrelated 「據」 switched the check off
        # for every claim in the piece, which two separate rewrites found by
        # keeping one legitimate attribution and sailing past two fabricated
        # statistics.
        carriers = [s for s in out_sentences
                    if sum(1 for t in terms if t in s) / len(terms) >= 0.5]
        if carriers and not any(attr.search(s) for s in carriers):
            orphans.append(sentence.strip()[:70])
    return orphans


def check_fidelity(source, output, lang):
    section("Fidelity (rewrite vs original)")
    src_names, src_nums = fidelity_tokens(source, lang, generous=True)
    out_names, out_nums = fidelity_tokens(output, lang)

    acronyms = source_acronyms(source)
    new_names = sorted(n for n in out_names - src_names
                       if n not in acronyms
                       and not any(n in s or s in n for s in src_names))
    # The Chinese extractor emits overlapping widths of the same name on
    # purpose, so the comparison can match 觀光協會 against 台灣觀光協會. Report
    # only the longest form of each, or one invented company reads as three.
    new_names = [n for n in new_names
                 if not any(n != o and n in o for o in new_names)]
    report(not new_names,
           "no names in the rewrite that are absent from the original"
           if not new_names else
           "names not in the original: " + ", ".join(new_names[:8])
           + " — invented, or confirm each is a form of a source name")

    new_nums = sorted(n for n in out_nums - src_nums)
    report(not new_nums,
           "no figures in the rewrite that are absent from the original"
           if not new_nums else
           "figures not in the original: " + ", ".join(new_nums[:8])
           + " — invented, or confirm each is derived from source figures")

    stolen = orphaned_claims(source, output, lang)
    report(not stolen,
           "no attributed claim was taken over as the rewrite's own"
           if not stolen else
           f"{len(stolen)} attributed claim(s) kept without the attribution: "
           + "; ".join(f'"{s}"' for s in stolen[:2])
           + " — cut the claim with the attribution, or keep the attribution")

    new_com = sorted(commitment_classes(output, lang)
                     - commitment_classes(source, lang))
    report(not new_com,
           "no promises the original did not make" if not new_com else
           "new commitment(s): " + ", ".join(new_com[:5])
           + " — the original promised nothing here")

    esc = severity_escalations(source, output, lang)
    report(not esc,
           "severity matches the original" if not esc else
           "raised severity: " + ", ".join(esc[:6])
           + " — the original did not go this far")


# Catalog entries that describe a syntactic shape rather than a string, so no
# word list can ever cover them. The model reads these; the checker cannot.
AUDIT_STRUCTURAL = [
    "名词化表达", "被动句滥用", "每句都从主语起头", "过长的",
    "把该连成一口气的流水句",
    "名詞化表達", "被動句濫用", "每句都從主語起頭", "過長的",
    "把該連成一口氣的流水句",
]

CATALOG_MARKERS = [
    r"Words to watch:", r"Wörter:", r"Hochfrequente KI-Wörter:",
    r"Hochfrequente KI-Konnektoren:", r"Todesphrasen(?: \([^)]*\))?:",
    r"Auch Pseudo-Einsicht-Auftakte:", r"Signal:",
    r"需要注意的套语：", r"需要注意：", r"高频 AI 连接词：", r"如：",
    r"也要注意假洞察开场：",
    r"需要注意的套語：", r"高頻 AI 連接詞：", r"也要注意假洞察開場：",
    r"訊號：", r"對面用詞：", r"大陸用詞：",
]

# The Traditional catalogs carry reference tables the gate is not meant to
# mirror: 200-row lexicon forks, 80-row transliteration tables, classifier and
# phone-number examples. Those exist for the model to read, and the checker
# deliberately gates only a high-precision subset of them (see REGION_FOREIGN).
# So for hk/tw the audit is strict about AI vocabulary — where drift between
# catalog and checker is a real bug — and reports the reference layer without
# failing on it.
STRICT_MARKERS = [
    r"Words to watch:", r"Wörter:", r"Hochfrequente KI-Wörter:",
    r"Hochfrequente KI-Konnektoren:", r"Todesphrasen(?: \([^)]*\))?:",
    r"Auch Pseudo-Einsicht-Auftakte:",
    r"需要注意的套语：", r"高频 AI 连接词：", r"也要注意假洞察开场：",
    r"需要注意的套語：", r"高頻 AI 連接詞：", r"也要注意假洞察開場：",
]


def catalog_terms(path, markers=None):
    text = Path(path).read_text(encoding="utf-8")
    marker = re.compile("(?:" + "|".join(markers or CATALOG_MARKERS) + r")(.*)")
    terms = []
    for line in text.split("\n"):
        m = marker.search(line)
        if not m:
            continue
        body = re.sub(r"[（(][^）)]*[）)]", "", m.group(1))
        for raw in re.split(r"[,、，]", body):
            term = raw.strip().strip("*").strip('"“”「」').strip(".。…").strip()
            # Some catalog entries describe a shape rather than a string
            # ("过长的'的'字串"); an ellipsis is the reliable marker.
            if "…" in term or "..." in term or term.startswith("http"):
                continue
            min_len = 2 if CJK_RE.search(term) else 3
            if len(term) < min_len:
                continue
            # "stands/serves as" documents two phrasings, not one term.
            terms.extend(p for p in expand_alternatives(term)
                         if len(p) >= min_len)
    return sorted(set(terms))


def expand_alternatives(term):
    """"stands/serves as" -> ["stands as", "serves as"]."""
    tokens = term.split(" ")
    for i, token in enumerate(tokens):
        if "/" in token:
            return [" ".join(tokens[:i] + [alt] + tokens[i + 1:])
                    for alt in token.split("/") if alt]
    return [term]


# The one criterion three separate blind rounds failed on, and the only one
# with no gate behind it. A rewrite can be flawless on region, register and
# fidelity and still stop being the document it claims to be — an announcement
# with nothing announced, a press release with no date and no source. Deleting
# for tone with nobody checking the result is still a press release.
GENRE_ITEMS = {
    "release": [
        ("product", r"[0-9]+\.[0-9]|版本|版|推出|發布|發佈|上線|上市|發表",
         "which product or version shipped"),
        ("when", r"今日|今天|即日|本日|[0-9]{1,2}\s*[）)]?\s*[月日]|即將|下週|下星期",
         "when it ships"),
        ("where", r"下載|更新至|升級至|升級到|前往|網站|網頁|瀏覽|申請|連結|"
                  r"http|App ?[Ss]tore|應用商店|後台|管理介面",
         "how to get it"),
    ],
    "outage": [
        ("when", r"[0-9]{1,2}\s*[:：時點]|凌晨|上午|下午|晚上|星期|週|周",
         "the window"),
        ("impact", r"影響|暫停|中斷|無法|不能使用|受影響", "what is affected"),
        ("action", r"準備|登出|儲存|保存|備份|安排|配合|留意|處理",
         "what the reader must do"),
        ("contact", r"查詢|聯絡|聯繫|找我|搵我|回報|回覆|電郵|email|分機|熱線",
         "who to ask"),
    ],
    "pressrelease": [
        ("when", r"今日|今天|[0-9]{1,2}\s*[）)]?\s*[月日]|昨日|本週|上週", "a date"),
        ("issuer", r"公司|協會|集團|機構|部|局|署|處|會|中心|學院|大學",
         "the issuing body"),
        ("source", r"表示|指出|說|稱|指|認為|補充|強調",
         "an attributed source"),
    ],
    "notice": [
        ("when", r"[0-9]{1,2}\s*[:：時點]|星期|週|周|日|即日", "when"),
        ("impact", r"影響|暫停|中斷|變更|調整|更新", "what changes"),
        ("contact", r"查詢|聯絡|聯繫|找我|搵我|回覆|回報|電郵|email",
         "who to ask"),
    ],
}


def run_genre(path, genre, lang):
    """Does the rewrite still work as the kind of document it claims to be?"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return 2
    items = GENRE_ITEMS[genre]
    print(f"genre check · {Path(path).name} · {genre}")
    missing = []
    for _, pattern, description in items:
        if re.search(pattern, text, re.I):
            print(f"  · carries {description}")
        else:
            missing.append(description)
            print(f"  ⚠ no {description}")
    if not missing:
        print("  · still works as a " + genre)
        return 0
    print("\n  A rewrite cannot supply what the source never had — inventing a "
          "date or a\n  contact is fabrication, not repair. If the source is "
          "missing these too, say\n  so to the reader instead of filling them "
          "in.")
    return 1


def run_siblings(paths, lang):
    """Shared phrasing across several rewrites produced in one batch.

    Rewriting five related documents in one sitting converges them: same
    paragraph count, same closing move, the same sentence carrying the same
    content in two files. Each one passes every check on its own, because every
    other check only ever sees one document. Two independent benchmark runs hit
    this and both had to catch it by reading the outputs side by side.
    """
    texts = {}
    for path in paths:
        try:
            texts[path] = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {path}: {exc}")
            return 2
    if len(texts) < 2:
        print("--siblings needs at least two files")
        return 2

    def shingles(text):
        stripped, _ = strip_markdown(text)
        out = set()
        for sentence in split_sentences(stripped, lang):
            if lang in CJK_LANGS:
                body = re.sub(rf"[^{CJK}]", "", sentence)
                out |= {body[i:i + 6] for i in range(len(body) - 5)}
            else:
                words = [w.lower() for w in WORD_RE.findall(sentence)]
                out |= {" ".join(words[i:i + 5])
                        for i in range(len(words) - 4)}
        return out

    print(f"sibling scan · {len(texts)} file(s) · language: {lang}")

    def skeleton(text):
        """Shape only — no vocabulary, so it survives a change of region.

        Two blind judges found the same defect from opposite sides: a Hong Kong
        and a Taiwanese rewrite of one source come out as the same document in
        two accents. 「也許哪天會裝，也許不會⋯我還蠻喜歡的」 against 「或許有一天
        會裝，或許不會⋯我覺得幾好」 is one sentence through two filters. Word
        overlap cannot see it — every word differs. The shape does not.
        """
        paras = split_paragraphs(text)
        return tuple(len(split_sentences(p, lang)) for p in paras)

    grams = {p: shingles(t) for p, t in texts.items()}
    shapes = {p: (len(split_paragraphs(t)),
                  len(split_sentences(t, lang))) for p, t in texts.items()}
    flagged = 0
    names = sorted(texts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = grams[a] & grams[b]
            union = grams[a] | grams[b]
            share = len(common) / len(union) if union else 0
            longest = sorted(common, key=len, reverse=True)[:3]
            # Shared facts and shared genre furniture are expected — T19 says
            # 不便之處，敬請見諒 is *supposed* to repeat verbatim — so overlap is
            # reported, not failed. Only near-duplication is a defect.
            if share >= 0.35:
                flagged += 1
                print(f"  ⚠ {Path(a).name} / {Path(b).name}: "
                      f"{share:.0%} shared phrasing — near-duplicate"
                      + (": " + "; ".join(f'"{g}"' for g in longest)
                         if longest else ""))
            elif share >= 0.05 or longest:
                print(f"  · {Path(a).name} / {Path(b).name}: "
                      f"{share:.0%} shared phrasing"
                      + (" — " + "; ".join(f'"{g}"' for g in longest[:2])
                         if longest else "")
                      + " (expected if the sources overlap)")
    # Two short documents landing on the same paragraph and sentence count is
    # coincidence; it only means something once there is structure to collide
    # and a batch big enough for the collision to be a pattern.
    # Same skeleton in two accents: same paragraph count, and sentence lengths
    # tracking each other bucket for bucket.
    bones = {p: skeleton(t) for p, t in texts.items()}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = bones[a], bones[b]
            if len(x) < 3 or len(x) != len(y):
                continue
            aligned = sum(1 for p, q in zip(x, y) if p == q) / len(x)
            if aligned < 0.8:
                continue
            flagged += 1
            print(f"  ⚠ {Path(a).name} / {Path(b).name}: same skeleton "
                  f"({len(x)} paragraphs, {aligned:.0%} of them the same "
                  "length) — one document in two accents. No vocabulary check "
                  "can see this, because every word differs")

    same_shape = [p for p in names
                  if list(shapes.values()).count(shapes[p]) > 1
                  and shapes[p][0] >= 3]
    if len(texts) >= 3 and len(same_shape) > 1:
        flagged += 1
        print("  ⚠ identical shape (paragraphs, sentences): "
              + ", ".join(Path(p).name for p in same_shape)
              + " — real documents written days apart are not this tidy")
    if not flagged:
        print("  · no repeated shape across the batch")
        return 0
    print("\n  If the sources genuinely share content this is expected — read "
          "the two\n  aloud and decide. Some genres also carry fixed furniture "
          "that is supposed\n  to repeat verbatim (a Hong Kong outage notice "
          "and its 不便之處，敬請見諒).\n  What is not expected is the same "
          "*shape*: same paragraph count, same closing\n  move, the same "
          "sentence carrying the same fact.")
    return 1


def run_audit(lang, catalog):
    words, phrases, watch = VOCAB[lang]
    # SEVERITY is checked by the fidelity pass rather than the vocabulary
    # pass, but it is still covered — the audit should not report it missing.
    extra = []
    if lang in HANT_LANGS:
        # The region tables are word lists too, so terms the catalog documents
        # there are covered even though the vocabulary pass never sees them.
        extra = (REGION_FOREIGN[lang] + MAINLAND_ONLY
                 + list(TRANSLIT_FOREIGN[lang])
                 + REGION_FOREIGN_PHRASES[lang]
                 + [w for w, _ in REGION_GLYPHS_ONEWAY[lang]])
    known = fold(" ".join(words + phrases + watch + SEVERITY[lang] + extra))
    gated = STRICT_MARKERS if lang in HANT_LANGS else None
    terms = [t for t in catalog_terms(catalog, gated)
             if not any(t.startswith(s) for s in AUDIT_STRUCTURAL)]
    reference = []
    if lang in HANT_LANGS:
        strict = set(terms)
        reference = [t for t in catalog_terms(catalog) if t not in strict]
    missing = []
    for term in terms:
        probe = fold(term)
        if lang in CJK_LANGS:
            covered = any(p in probe or probe in p
                          for p in [fold(x) for x in
                                    phrases + watch + SEVERITY[lang] + extra])
        else:
            head = probe.split()[0] if probe.split() else probe
            covered = probe in known or re.search(
                rf"\b{re.escape(head[:max(4, len(head) - 3)])}", known)
        if not covered:
            missing.append(term)
    print(f"catalog audit · {catalog}")
    print(f"  · {len(terms)} matchable term(s) documented in the catalog")
    if reference:
        seen = sum(1 for t in reference
                   if any(fold(t) in fold(x) or fold(x) in fold(t)
                          for x in extra))
        print(f"  · {len(reference)} reference term(s) in the region tables, "
              f"{seen} of them gated — the rest are for the model to read, "
              "not for the checker to match")
    if missing:
        print(f"  ⚠ {len(missing)} not visible to the checker:")
        for term in missing:
            print(f"      {term}")
        print("\n  Add the important ones to AI_WORDS_* / AI_PHRASES_* "
              "(flagged)\n  or AI_WATCH_* (reported only).")
    else:
        print("  · every catalog term is covered")
    return 1 if missing else 0


def main():
    parser = argparse.ArgumentParser(
        description="Statistical AI-tell screening for EN/ZH/HK/TW/DE text.")
    parser.add_argument("file", nargs="?", help="text file to screen")
    parser.add_argument("--source",
                        help="the original text, to run the fidelity pass")
    parser.add_argument("--lang", choices=["en", "zh", "hk", "tw", "de"],
                        help="language (default: auto-detect). zh is mainland "
                             "Simplified; hk and tw are Traditional for Hong "
                             "Kong and Taiwan")
    parser.add_argument("--json", action="store_true",
                        help="emit the report as JSON")
    parser.add_argument("--audit", action="store_true",
                        help="compare word lists against references/patterns.md")
    parser.add_argument("--genre", choices=sorted(GENRE_ITEMS),
                        help="check the rewrite still functions as this kind "
                             "of document (needs FILE)")
    parser.add_argument("--siblings", nargs="+", metavar="FILE",
                        help="compare several rewrites from one batch for "
                             "shared phrasing and repeated shape")
    parser.add_argument("--catalog",
                        help="catalog path for --audit "
                             "(default: ../references/patterns.md)")
    args = parser.parse_args()

    if args.audit:
        catalog = args.catalog or (
            Path(__file__).resolve().parent.parent / "references"
            / "patterns.md")
        if not Path(catalog).exists():
            sys.exit(f"error: catalog not found: {catalog}")
        lang = args.lang or detect_lang(
            Path(catalog).read_text(encoding="utf-8"))
        sys.exit(run_audit(lang, catalog))

    if args.genre:
        if not args.file:
            parser.error("--genre needs a FILE")
        lang = args.lang or detect_lang(
            Path(args.file).read_text(encoding="utf-8"))
        sys.exit(run_genre(args.file, args.genre, lang))

    if args.siblings:
        lang = args.lang or detect_lang(
            Path(args.siblings[0]).read_text(encoding="utf-8"))
        sys.exit(run_siblings(args.siblings, lang))

    if not args.file:
        parser.error("a FILE is required unless --audit or --siblings is used")
    try:
        raw = Path(args.file).read_text(encoding="utf-8")
    except OSError as e:
        sys.exit(f"error: {e}")
    if not raw.strip():
        sys.exit("error: file is empty")

    text, stripped = strip_markdown(raw)
    if not text.strip():
        sys.exit("error: nothing left after removing markdown scaffolding")
    folded = fold(text)
    lang = args.lang or detect_lang(text)
    paragraphs = split_paragraphs(text)
    sentences = [s for p in paragraphs for s in split_sentences(p, lang)]

    dropped = ", ".join(f"{n} {name}" for name, n in stripped.items() if n)
    print(f"naturalness-check · language: {lang} · "
          f"{len(paragraphs)} paragraph(s), {len(sentences)} sentence(s)"
          + (f" · skipped {dropped}" if dropped else ""))
    if lang in HANT_LANGS and not args.lang:
        print(f"  note: region guessed as {REGION_NAME[lang]}. The whole "
              "point of the region pass is that the two sides disagree, so "
              "pass --lang hk or --lang tw rather than trusting the guess.")

    check_rhythm(sentences, lang)
    check_openers(sentences, lang)
    check_serial_enumeration(sentences, lang)
    check_paragraphs(paragraphs, lang)
    check_vocabulary(folded, lang)
    check_punctuation(text, folded, lang, sentences)
    check_language_flavor(text, folded, lang, sentences)
    check_region(text, lang)
    if args.source:
        try:
            src = strip_markdown(
                Path(args.source).read_text(encoding="utf-8"))[0]
        except OSError as e:
            sys.exit(f"error: --source: {e}")
        check_fidelity(src, text, lang)

    print(f"\n{len(flags)} warning(s)." if flags else
          "\nNo warnings. (Signals only — read it aloud anyway.)")

    if args.json:
        print(json.dumps({
            "file": args.file,
            "lang": lang,
            "paragraphs": len(paragraphs),
            "sentences": len(sentences),
            "skipped": stripped,
            "sections": sections,
            "warnings": flags,
            "ok": not flags,
        }, ensure_ascii=False, indent=2))

    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
