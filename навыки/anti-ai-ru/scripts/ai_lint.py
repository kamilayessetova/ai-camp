#!/usr/bin/env python3
"""Детектор машинных признаков в русском тексте.

Считает AI-риск от 0 до 100 по шести группам: лексика, конструкции, ритм, структура,
типографика, фактура. Норма — 20 и ниже; выше 40 текст читается как машинный.

Детектор видит регулярки и статистику. Он не поймает выдуманный факт, ложную
сбалансированность и пустой абзац, написанный «чистыми» словами, — это работа редактора.

    python ai_lint.py <файл> [--format text|json] [--top N]

Коды выхода: 0 — риск в норме, 1 — риск выше нормы, 2 — файл не прочитан.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

NORM = 20  # порог приёмки

# ── словари ──────────────────────────────────────────────────────────────────

LEXICON = [
    # абстрактные существительные
    "ландшафт", "парадигм", "аспект", "нюанс", "спектр", "синерги", "экосистем",
    "вектор", "потенциал", "реализаци", "имплементаци", "обеспечени", "формировани",
    "оптимизаци", "трансформаци", "эффективност", "критери", "тенденци", "катализатор",
    "краеугольн", "инсайт", "нарратив", "дорожная карта", "точка боли",
    "пользовательский опыт", "экспертиз",
    # оценочные прилагательные
    "ключев", "решающ", "критическ", "жизненно важн", "беспрецедент", "уникальн",
    "инновационн", "революционн", "комплексн", "всеобъемлющ", "многогранн",
    "эффективн", "оптимальн", "перспективн", "динамичн", "масштабируем", "устойчив",
    "значим", "существенн", "фундаментальн", "бесшовн", "интуитивн",
    "клиентоориентирован", "релевантн", "актуальн",
    # глаголы-пустышки
    "является", "являются", "представляет собой", "осуществля", "способству",
    "обеспечива", "подчёркива", "подчеркива", "демонстриру", "характеризу",
    "интегрирова", "оптимизирова", "резониру",
    # вводные и наречия
    "безусловно", "несомненно", "разумеется", "очевидно", "поистине",
    "в свою очередь", "в конечном итоге", "в конечном счёте", "в конечном счете",
    "по сути", "в принципе", "как таковой", "в современном мире", "в наши дни",
    "на сегодняшний день", "в настоящее время", "зачастую",
    # канцелярские связки
    "в связи с тем", "в силу того", "ввиду того", "вследствие", "в случае, если",
    "при условии, что", "для того, чтобы", "в целях", "на основании того",
    "в рамках", "посредством", "при наличии", "данный подход", "вышеуказан",
    "вышеупомянут", "имеет место быть", "в значительной степени",
    # пафос
    "новые горизонты", "на новый уровень", "незаменим", "может похвастаться",
    "не оставит равнодушн", "не заставит себя ждать", "в самом сердце",
    "меняет правила игры", "передов",
]

CONSTRUCTIONS = [
    (r'не только[^.!?]{0,60}но и', "не только X, но и Y"),
    (r'это не (просто )?[^.!?]{0,40}, а ', "это не X, а Y"),
    (r'дело не в[^.!?]{0,40}, (а )?дело в', "дело не в X, дело в Y"),
    (r'важно (понимать|помнить|отметить|учитывать)', "важно понимать, что"),
    (r'(стоит|следует|необходимо) (отметить|подчеркнуть|учитывать|помнить)', "стоит отметить"),
    (r'нельзя недооценива', "нельзя недооценивать"),
    (r'одним из (ключевых|главных|важнейших)', "одним из ключевых факторов"),
    (r'с одной стороны[^.!?]{0,120}с другой стороны', "с одной стороны… с другой"),
    (r'\bкак .{2,30}, так и ', "как X, так и Y"),
    (r'таким образом', "таким образом"),
    (r'подводя итог', "подводя итог"),
    (r'в заключени', "в заключение"),
    (r'резюмиру', "резюмируя"),
    (r'если говорить о[^.!?]{0,40}, то', "если говорить о X, то"),
    (r'когда речь (заходит|идёт|идет) о', "когда речь заходит о"),
    (r'играет (ключев|важн|значим|особ)\w* роль', "играет ключевую роль"),
    (r'имеет (решающее|важное|принципиальное) значение', "имеет решающее значение"),
    (r'можно выделить несколько', "можно выделить несколько"),
    (r'необходимо обеспечить', "необходимо обеспечить"),
    (r'почему это важно\?', "почему это важно?"),
    (r'главное — (начать|помнить)', "главное — начать действовать"),
    (r'в (этой|данной) статье( мы)? (рассмотрим|разберём|разберем|поговорим)',
     "в этой статье мы рассмотрим"),
    (r'дава(й|йте) (погрузимся|разберёмся|разберемся|посмотрим)', "давайте погрузимся"),
    (r'перейд(ём|ем) к', "перейдём к следующему"),
    (r'теперь, когда мы', "теперь, когда мы разобрали"),
    (r'на переднем крае', "на переднем крае"),
    (r'раскры(ть|вает) (весь )?потенциал', "раскрыть потенциал"),
    (r'в быстро меняющемся мире', "в быстро меняющемся мире"),
    (r'в двух словах', "в двух словах"),
    (r'вне зависимости от', "вне зависимости от"),
    (r'на основании вышеизложенного', "на основании вышеизложенного"),
    (r'обусловлено тем, что', "обусловлено тем, что"),
    (r'\bв данном случае\b', "в данном случае"),
    (r'что это значит\? это значит', "псевдодиалог «что это значит?»"),
    (r'в чём же (секрет|смысл)', "псевдовопрос «в чём же секрет?»"),
]

VAGUE_SOURCES = [
    (r'эксперт\w* (отмеча|счита|говор|полага)', "эксперты отмечают"),
    (r'специалист\w* (отмеча|счита|рекоменду)', "специалисты считают"),
    (r'согласно (исследовани|данным|статистике)(?![^.!?]{0,60}\d{4})',
     "согласно исследованиям — без источника"),
    (r'исследовани\w* показыва', "исследования показывают"),
    (r'статистика показыва', "статистика показывает"),
    (r'(многие|большинство) (компани|пользовател|специалист)', "многие компании"),
    (r'принято считать', "принято считать"),
    (r'по некоторым данным', "по некоторым данным"),
    (r'учёные (провели|выяснили|доказали)', "учёные выяснили"),
    (r'как известно', "как известно"),
]

INVISIBLE = {
    "\u00a0": "U+00A0 неразрывный пробел",
    "\u202f": "U+202F узкий неразрывный пробел",
    "\u200b": "U+200B нулевой пробел",
    "\u2060": "U+2060 word joiner",
    "\u00ad": "U+00AD мягкий перенос",
}

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27bf\u2b00-\u2bff\ufe0f]"
)

MONTHS = ("январ", "феврал", "март", "апрел", "мая", "мае", "июн", "июл", "август",
          "сентябр", "октябр", "ноябр", "декабр")


# ── разбор текста ────────────────────────────────────────────────────────────

class Text:
    def __init__(self, raw):
        self.raw = raw
        lines, in_fence = [], False
        for line in raw.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                lines.append(line)
        self.lines = lines
        self.headings = [l for l in lines if re.match(r'^#{1,6}\s', l.strip())]
        self.bullets = [l for l in lines if re.match(r'^\s*([-*+]|\d+[.)])\s', l)]
        self.paragraphs = self._paragraphs()
        self.body = "\n".join(lines)
        self.plain = re.sub(r'[#*_`>|-]', " ", self.body)
        self.words = re.findall(r'[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z-]*', self.plain)
        self.sentences = [s for s in re.split(r'(?<=[.!?…])\s+', " ".join(self.paragraphs)) if s.strip()]

    def _paragraphs(self):
        paras, buf = [], []
        for line in self.lines:
            s = line.strip()
            if not s:
                if buf:
                    paras.append(" ".join(buf))
                    buf = []
                continue
            if re.match(r'^#{1,6}\s', s) or re.match(r'^([-*+]|\d+[.)])\s', s) or s.startswith("|"):
                if buf:
                    paras.append(" ".join(buf))
                    buf = []
                continue
            buf.append(s)
        if buf:
            paras.append(" ".join(buf))
        return paras

    def lists(self):
        """Группы подряд идущих пунктов списка."""
        groups, cur = [], []
        for line in self.lines:
            if re.match(r'^\s*([-*+]|\d+[.)])\s', line):
                cur.append(re.sub(r'^\s*([-*+]|\d+[.)])\s', "", line).strip())
            elif line.strip() == "" and cur:
                continue
            elif cur:
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        return groups


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def snippet(text, start, end, pad=25):
    """Фрагмент вокруг находки в одну строку — иначе в отчёт лезут куски разметки."""
    piece = text[max(0, start - pad):end + pad]
    return re.sub(r"\s+", " ", piece).strip()


def cv(values):
    """Коэффициент вариации: разброс относительно среднего. Ровный ритм даёт низкий CV."""
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    if mean == 0:
        return None
    return statistics.pstdev(values) / mean


# ── группы проверок ──────────────────────────────────────────────────────────

def check_lexicon(t, findings):
    low = t.plain.lower()
    hits = 0
    seen = {}
    for marker in LEXICON:
        for m in re.finditer(re.escape(marker), low):
            hits += 1
            seen[marker] = seen.get(marker, 0) + 1
            if seen[marker] <= 2:
                findings.append(("лексика", line_of(low, m.start()),
                                 snippet(t.plain, m.start(), m.start() + len(marker)),
                                 "слово-маркер: удалить или заменить конкретикой"))
    per100 = hits / max(1, len(t.words)) * 100
    return min(25.0, per100 * 11), {"попаданий": hits, "на 100 слов": round(per100, 2)}


def check_constructions(t, findings):
    low = t.plain.lower()
    hits = 0
    for pattern, name in CONSTRUCTIONS:
        for m in re.finditer(pattern, low):
            hits += 1
            findings.append(("конструкции", line_of(low, m.start()), m.group()[:70],
                             f"конструкция-маркер «{name}»: перестроить фразу"))
    per100 = hits / max(1, len(t.words)) * 100
    return min(25.0, per100 * 22), {"попаданий": hits, "на 100 слов": round(per100, 2)}


def check_rhythm(t, findings):
    lengths = [len(re.findall(r'[А-Яа-яЁёA-Za-z-]+', s)) for s in t.sentences]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 4:
        return 0.0, {"предложений": len(lengths)}
    variation = cv(lengths)
    score = 0.0
    stats = {"предложений": len(lengths),
             "средняя длина": round(statistics.mean(lengths), 1),
             "разброс CV": round(variation, 2) if variation else None}
    if variation is not None and variation < 0.55:
        score += (0.55 - variation) / 0.55 * 12
        findings.append(("ритм", 0, f"CV длины предложений {variation:.2f}",
                         "ровный машинный ритм: добавить короткие и длинные предложения"))
    band = sum(1 for n in lengths if 12 <= n <= 20) / len(lengths)
    stats["доля 12−20 слов"] = round(band, 2)
    if band > 0.55:
        score += 5
        findings.append(("ритм", 0, f"{band:.0%} предложений по 12−20 слов",
                         "однородная длина: разбить часть фраз, часть развернуть"))
    if not any(n <= 5 for n in lengths):
        score += 3
        findings.append(("ритм", 0, "нет ни одного короткого предложения",
                         "живой ритм требует коротких фраз"))
    return min(20.0, score), stats


def check_structure(t, findings):
    score = 0.0
    stats = {}
    para_lens = [len(p) for p in t.paragraphs]
    variation = cv(para_lens)
    stats["абзацев"] = len(t.paragraphs)
    stats["разброс длины абзацев"] = round(variation, 2) if variation else None
    if variation is not None and variation < 0.35:
        score += 4
        findings.append(("структура", 0, f"CV длины абзацев {variation:.2f}",
                         "абзацы одинакового размера: сделать разной длины"))

    groups = t.lists()
    triples = sum(1 for g in groups if len(g) == 3)
    stats["списков"] = len(groups)
    stats["списков из трёх"] = triples
    if groups and triples / len(groups) > 0.6 and len(groups) >= 2:
        score += 4
        findings.append(("структура", 0, f"{triples} из {len(groups)} списков ровно по три пункта",
                         "правило трёх: сделать списки разной длины"))

    for g in groups:
        item_cv = cv([len(x) for x in g])
        if item_cv is not None and item_cv < 0.2 and len(g) >= 3:
            score += 2
            findings.append(("структура", 0, "; ".join(g)[:70],
                             "симметричные пункты: один пункт развернуть примером"))
            break

    term_bullets = sum(1 for b in t.bullets if re.match(r'^\s*[-*+]\s+\*\*[^*]+:?\*\*:?\s', b))
    stats["пунктов «**Термин:** пояснение»"] = term_bullets
    if term_bullets >= 3:
        score += 4
        findings.append(("структура", 0, f"{term_bullets} пунктов вида «**Термин:** пояснение»",
                         "самый узнаваемый машинный формат списка"))

    tail = " ".join(t.paragraphs[-1:]).lower()
    if re.search(r'(в заключение|подводя итог|таким образом|в целом,|резюмиру)', tail):
        score += 4
        findings.append(("структура", 0, tail[:70],
                         "финал объявляет себя финалом: убрать рамку вывода"))

    colon_headings = sum(1 for h in t.headings if re.search(r'\w:\s+\w', h))
    if colon_headings >= 2:
        score += 3
        findings.append(("структура", 0, f"{colon_headings} заголовков вида «Тема: подзаголовок»",
                         "машинный формат заголовка"))
    return min(20.0, score), stats


def check_typography(t, findings):
    score = 0.0
    chars = max(1, len(t.body))
    stats = {}

    dashes = t.body.count("—")
    per1000 = dashes / chars * 1000
    stats["длинных тире на 1000 знаков"] = round(per1000, 1)
    if per1000 > 4:
        score += min(4.0, (per1000 - 4) * 0.8)
        findings.append(("типографика", 0, f"{dashes} длинных тире ({per1000:.1f} на 1000 знаков)",
                         "тире как украшение: часть заменить запятой или точкой"))

    emoji = EMOJI.findall(t.body)
    stats["эмодзи"] = len(emoji)
    if emoji:
        score += min(3.0, len(emoji) * 0.5)
        findings.append(("типографика", 0, "".join(emoji[:10]),
                         "эмодзи в деловом тексте — машинный маркер"))

    bold = re.findall(r'\*\*[^*\n]+\*\*', t.body)
    bold_words = sum(len(b.split()) for b in bold)
    share = bold_words / max(1, len(t.words))
    stats["доля слов жирным"] = round(share, 3)
    if share > 0.06:
        score += 3
        findings.append(("типографика", 0, f"{bold_words} слов выделено жирным",
                         "избыточное выделение: оставить то, что ищут глазами"))

    pathos = re.findall(r'(?:^|\. )(?:Вывод прост|Запомни|Главное правило|Итог)\s*:', t.body)
    if pathos:
        score += 2
        findings.append(("типографика", 0, "; ".join(pathos[:3]),
                         "двоеточие с пафосом: переформулировать"))

    for ch, name in INVISIBLE.items():
        n = t.raw.count(ch)
        if n:
            score += 2
            stats[name] = n
            findings.append(("типографика", 0, f"{name} × {n}",
                             "невидимый символ из генерации: вычистить"))

    if re.search(r'utm_source=(chatgpt|openai)', t.raw, re.IGNORECASE):
        score += 3
        findings.append(("типографика", 0, "utm_source=chatgpt в ссылке",
                         "метка источника генерации: почистить ссылку"))
    return min(15.0, score), stats


def check_facts(t, findings):
    score = 0.0
    low = t.plain.lower()
    stats = {}

    vague = 0
    for pattern, name in VAGUE_SOURCES:
        for m in re.finditer(pattern, low):
            vague += 1
            findings.append(("фактура", line_of(low, m.start()), m.group()[:60],
                             f"обтекаемая атрибуция «{name}»: имя, организация, год — или удалить"))
    stats["обтекаемых атрибуций"] = vague
    score += min(8.0, vague * 2.5)

    concrete = 0
    for p in t.paragraphs:
        has_number = bool(re.search(r'\d', p))
        has_proper = bool(re.search(r'(?<![.!?…]\s)(?<!^)\b[А-ЯЁ][а-яё]{2,}', p))
        has_month = any(mn in p.lower() for mn in MONTHS)
        if has_number or has_proper or has_month:
            concrete += 1
    share = concrete / max(1, len(t.paragraphs))
    stats["доля абзацев с конкретикой"] = round(share, 2)
    if share < 0.6 and t.paragraphs:
        score += (0.6 - share) / 0.6 * 10
        findings.append(("фактура", 0, f"конкретика есть в {share:.0%} абзацев",
                         "в каждом абзаце нужны число, имя, дата, название или деталь"))

    round_pct = re.findall(r'\b(?:10|20|25|30|40|50|60|70|75|80|90)\s?%', t.plain)
    stats["круглых процентов"] = len(round_pct)
    if len(round_pct) >= 2:
        score += 2
        findings.append(("фактура", 0, ", ".join(round_pct[:5]),
                         "круглые проценты подряд: проверить источник или убрать"))
    return min(20.0, score), stats


GROUPS = [
    ("лексика", check_lexicon),
    ("конструкции", check_constructions),
    ("ритм", check_rhythm),
    ("структура", check_structure),
    ("типографика", check_typography),
    ("фактура", check_facts),
]


def analyze(raw):
    t = Text(raw)
    findings = []
    scores, stats = {}, {}
    for name, fn in GROUPS:
        score, group_stats = fn(t, findings)
        scores[name] = round(score, 1)
        stats[name] = group_stats
    total = min(100.0, sum(scores.values()))
    # Показываем сначала то, что требует переписывания, и только потом словарные
    # попадания: лексики всегда много, и она вытесняет из отчёта всё остальное.
    priority = {"конструкции": 0, "фактура": 1, "структура": 2, "ритм": 3,
                "типографика": 4, "лексика": 5}
    findings.sort(key=lambda f: (priority.get(f[0], 9), f[1]))
    return round(total, 1), scores, stats, findings, t


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Детектор машинных признаков в русском тексте")
    ap.add_argument("file")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--top", type=int, default=30, help="сколько находок показать")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print("Файл не найден: {}".format(path), file=sys.stderr)
        return 2

    total, scores, stats, findings, t = analyze(path.read_text(encoding="utf-8", errors="replace"))

    if args.format == "json":
        print(json.dumps({
            "ai_risk": total, "norm": NORM, "scores": scores, "stats": stats,
            "findings": [{"group": g, "line": l, "fragment": f, "fix": h}
                         for g, l, f, h in findings],
        }, ensure_ascii=False, indent=2))
    else:
        verdict = "норма" if total <= NORM else ("повышенный" if total <= 40 else "высокий")
        print("AI-риск: {} из 100 ({}). Норма — {} и ниже.".format(total, verdict, NORM))
        print("Слов {}, предложений {}, абзацев {}\n".format(
            len(t.words), len(t.sentences), len(t.paragraphs)))
        width = max(len(g) for g in scores)
        for group, value in scores.items():
            bar = "#" * int(value)
            print("  {:<{w}}  {:>5}  {}".format(group, value, bar, w=width))
        print()
        for group, line, fragment, fix in findings[:args.top]:
            where = ":{}".format(line) if line else ""
            print("[{}{}] «{}» → {}".format(group, where, fragment, fix))
        if len(findings) > args.top:
            print("… ещё {} находок, показать все: --top {}".format(
                len(findings) - args.top, len(findings)))
        print("\nСтатистика по группам:")
        for group, group_stats in stats.items():
            if group_stats:
                print("  {}: {}".format(group, ", ".join(
                    "{} {}".format(k, v) for k, v in group_stats.items() if v is not None)))
        print("\nДетектор не видит смысла: выдуманные факты, ложную сбалансированность")
        print("и пустые абзацы без слов-маркеров проверяет редактор.")

    return 0 if total <= NORM else 1


if __name__ == "__main__":
    sys.exit(main())
