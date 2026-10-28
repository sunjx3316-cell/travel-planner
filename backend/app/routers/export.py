"""Generate the user's confirmed itinerary as a private, in-memory PDF."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from xml.sax.saxutils import escape
import unicodedata
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints, model_validator

router = APIRouter(prefix='/api/plans', tags=['export'])
ShortText = Annotated[str, StringConstraints(max_length=300)]
NoteText = Annotated[str, StringConstraints(max_length=2000)]


class ExportBase(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def normalize_missing_text(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            for key in ('spot', 'time', 'why', 'time_reason', 'note', 'name', 'summary',
                        'area_label', 'town', 'price', 'to', 'rail', 'recommend'):
                if key in value and value[key] is None:
                    value[key] = ''
        return value


class ExportItem(ExportBase):
    spot: ShortText = ''
    time: ShortText = ''
    why: NoteText = ''
    time_reason: NoteText = ''


class ExportStay(ExportBase):
    area_label: ShortText = ''
    town: ShortText = ''
    price: ShortText = ''


class ExportTransport(ExportBase):
    to: ShortText = ''
    rail: ShortText = ''
    recommend: ShortText = ''


class ExportFood(ExportBase):
    name: ShortText = ''


class ExportFoods(BaseModel):
    dishes: list[ExportFood] = Field(default_factory=list, max_length=40)


class ExportDay(ExportBase):
    note: NoteText = ''
    items: list[ExportItem] = Field(default_factory=list, max_length=40)
    stay: ExportStay | None = None
    next_transport: ExportTransport | None = None
    foods: ExportFoods | None = None


class RailLeg(BaseModel):
    train: ShortText
    from_: ShortText = Field(alias='from')
    to: ShortText
    departure: int = Field(ge=0, le=10080)
    arrival: int = Field(ge=0, le=10080)


class RailJourney(BaseModel):
    date: Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}$')]
    from_: ShortText = Field(alias='from')
    to: ShortText
    risk: ShortText = '待核实'
    snapshot: ShortText = ''
    cost: float | None = Field(default=None, gt=0, le=100000)
    legs: list[RailLeg] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def ordered_legs(self):
        from datetime import date
        date.fromisoformat(self.date)
        for i, leg in enumerate(self.legs):
            if leg.arrival <= leg.departure or (i and leg.departure < self.legs[i-1].arrival):
                raise ValueError('铁路时间不完整')
        return self


class ExportPlan(ExportBase):
    name: ShortText = '我的行程'
    summary: NoteText = ''
    daily: list[ExportDay] = Field(min_length=1, max_length=60)
    tips: list[NoteText] = Field(default_factory=list, max_length=30)
    workshop_changed: bool = False
    rail_journeys: list[RailJourney] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def limit_document_size(self):
        items = [item for day in self.daily for item in day.items]
        text_size = len(self.name) + len(self.summary) + sum(len(day.note) for day in self.daily)
        text_size += sum(len(item.spot) + len(item.time) + len(item.why) + len(item.time_reason) for item in items)
        text_size += sum(len(tip) for tip in self.tips)
        if len(items) > 400 or text_size > 120000:
            raise ValueError('日程过长，请拆成几份 PDF 导出')
        return self


@lru_cache(maxsize=1)
def pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    # Embed a real Chinese font on Windows so the portable PDF remains legible
    # on phones. On other hosts, use the PDF standard's Chinese CID font.
    for path in (Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/simhei.ttf')):
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont('TravelChinese', str(path), subfontIndex=0))
                return 'TravelChinese'
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    return 'STSong-Light'


def safe_text(value):
    text = ''.join(ch for ch in str(value or '') if
                   (ord(ch) >= 32 or ch == '\n') and unicodedata.category(ch) not in {'So', 'Cs', 'Cf'}
                   and ch != '\ufe0f')
    return escape(text).replace('\n', '<br/>')


def calendar_period(value):
    text = str(value or '').strip()
    if re.search('全天|待安排|晚上|夜|傍晚', text):
        return 'other'
    if re.search('上午|早|中午', text):
        return 'morning'
    if '下午' in text:
        return 'afternoon'
    match = re.match(r'^(\d{1,2})[:：](\d{2})\s*[-–—~～至]\s*(\d{1,2})[:：](\d{2})$', text)
    if match:
        h1, m1, h2, m2 = map(int, match.groups())
        if h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60:
            return 'morning' if h1 < 12 else 'afternoon' if h1 < 18 else 'other'
    return 'other'


def build_pdf(plan: ExportPlan):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    stream = BytesIO()
    font = pdf_font()
    green = colors.HexColor('#165b50')
    base = ParagraphStyle('body', fontName=font, fontSize=9, leading=14, spaceAfter=3, wordWrap='CJK')
    title = ParagraphStyle('title', parent=base, fontSize=25, leading=34, spaceAfter=8, textColor=green)
    heading = ParagraphStyle('day', parent=base, fontSize=12, leading=18, spaceBefore=12, spaceAfter=8, keepWithNext=True)
    muted = ParagraphStyle('muted', parent=base, fontSize=8, leading=12, textColor=colors.HexColor('#6b7e78'))
    item = ParagraphStyle('item', parent=base, fontSize=11, leading=17, spaceAfter=5, textColor=colors.HexColor('#243e38'), keepWithNext=True)
    column = ParagraphStyle('column', parent=base, fontSize=13, leading=21, textColor=green, spaceAfter=0)
    slot = ParagraphStyle('slot', parent=muted, fontSize=8, leading=12, spaceBefore=6, spaceAfter=6, textColor=green, keepWithNext=True)
    time_style = ParagraphStyle('time', parent=muted, fontSize=8, spaceAfter=4, textColor=colors.HexColor('#a07238'), keepWithNext=True)
    small = ParagraphStyle('small', parent=muted, fontSize=7, leading=11, spaceAfter=0)
    # Dense driving days include transfer cards as well as visits. Tighten only
    # vertical spacing, not text size, to avoid a nearly empty memo-only page.
    if any(len(day.items) >= 3 for day in plan.daily):
        base.leading, base.spaceAfter = 12, 2
        muted.leading, muted.spaceAfter = 10, 2
        item.leading, item.spaceAfter = 14, 3
        slot.spaceBefore, slot.spaceAfter = 4, 4
        time_style.spaceAfter = 2
    page_size = landscape(A4)
    doc = SimpleDocTemplate(stream, pagesize=page_size, leftMargin=14*mm, rightMargin=14*mm,
                            topMargin=12*mm, bottomMargin=15*mm,
                            title=plan.name, author='旅行智规')
    date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    total_items = sum(len(day.items) for day in plan.daily)
    story = []

    def period(entry):
        if '全天' in entry.time:
            return 'all_day'
        key = calendar_period(entry.time)
        if key != 'other':
            return key
        if re.search('晚上|夜|傍晚', entry.time) or re.match(r'^(18|19|2[0-3])[:：]', entry.time):
            return 'evening'
        return 'flexible'

    # Day cards, rather than a spreadsheet grid: an all-day visit occupies its
    # own day card instead of leaving two empty rows above it. Flowable lists
    # split safely for long itineraries, repeating the day headers on each page.
    for start in range(0, len(plan.daily), 3):
        days = plan.daily[start:start+3]
        if start:
            story.append(PageBreak())
        masthead = Table([[
            Paragraph('旅行智规  /  日历式行程表', muted),
            Paragraph(f'{len(plan.daily):02d} 天  /  {total_items:02d} 个安排', ParagraphStyle('stats', parent=muted, alignment=2)),
        ]], colWidths=[doc.width * .65, doc.width * .35])
        masthead.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,0), .6, colors.HexColor('#c8d9d2')),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.extend([masthead, Spacer(1, 12), Paragraph(safe_text(plan.name), title)])
        if plan.summary and not start:
            story.append(Paragraph(safe_text(plan.summary), base))
        story.append(Paragraph(f'第 {start+1}–{start+len(days)} 天  ·  最终确认版  ·  导出于 {date}', muted))
        if plan.workshop_changed and not start:
            story.append(Paragraph('已手动调整 · 原路线、住宿与交通推算未重新计算，请出发前核实。', small))
        story.append(Spacer(1, 12))
        def common_value(field):
            values = [getattr(day, field) for day in days]
            return values[0] if not plan.workshop_changed and len(values) > 1 and values[0] and all(value == values[0] for value in values) else None
        common_stay, common_foods = common_value('stay'), common_value('foods')
        headers, cards = [], []
        for index, day in enumerate(days):
            headers.append(Paragraph(f'<font size="22">{start+index+1:02d}</font>  /  第 {start+index+1} 天'
                                     f'<br/><font size="8" color="#6b7e78">{len(day.items)} 个安排</font>', column))
            content = []
            keys = [period(entry) for entry in day.items]
            for key, label in [('all_day', 'ALL DAY  /  全天'), ('morning', 'AM  /  上午'),
                               ('afternoon', 'PM  /  下午'), ('evening', 'NIGHT  /  晚间'),
                               ('flexible', 'FLEX  /  时间待定')]:
                entries = [entry for entry, entry_key in zip(day.items, keys) if entry_key == key]
                if not entries and (key not in {'morning', 'afternoon'} or 'all_day' in keys):
                    continue
                content.append(Paragraph(label, slot))
                if not entries:
                    content.append(Paragraph('留白时间 · 自由安排', muted))
                for entry in entries:
                    if entry.time and entry.time not in {'上午', '下午', '全天', '晚上', '待安排'}:
                        content.append(Paragraph(safe_text(entry.time), time_style))
                    content.append(Paragraph(safe_text(entry.spot or '未命名安排'), item))
                    if entry.why:
                        content.append(Paragraph(safe_text(entry.why), base))
                    if entry.time_reason and not plan.workshop_changed:
                        content.append(Paragraph(safe_text(entry.time_reason), muted))
                    # A non-kept spacer also lets a long title stand alone safely.
                    content.append(Spacer(1, 4))
            notes = []
            if day.note:
                notes.append(Paragraph(safe_text(day.note), muted))
            if not plan.workshop_changed:
                if day.stay and not common_stay:
                    notes.append(Paragraph('住 / ' + safe_text(day.stay.area_label or day.stay.town) + ' ' + safe_text(day.stay.price), muted))
                if day.next_transport:
                    notes.append(Paragraph('次日转场 / ' + safe_text(day.next_transport.to) + ' · ' + safe_text(day.next_transport.rail or day.next_transport.recommend), muted))
                if day.foods and day.foods.dishes and not common_foods:
                    notes.append(Paragraph('食 / ' + '、'.join(safe_text(dish.name) for dish in day.foods.dishes), muted))
            if notes:
                content.extend([Paragraph('MEMO  /  当天备忘', slot), *notes])
            cards.append(content)
        # Narrow white gutters separate day columns without heavy grid lines.
        def with_gutters(cells):
            result = []
            for cell in cells:
                if result:
                    result.append('')
                result.append(cell)
            return result
        gap = 10
        width = (doc.width - gap * (len(days)-1)) / len(days)
        widths = [width if i % 2 == 0 else gap for i in range(len(days)*2-1)]
        table = Table([with_gutters(headers), with_gutters(cards)], colWidths=widths,
                      repeatRows=1, splitByRow=1, splitInRow=1, minRowHeights=[57, 220])
        table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 15), ('RIGHTPADDING', (0,0), (-1,-1), 15),
            ('TOPPADDING', (0,0), (-1,-1), 12), ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ]))
        for col in range(0, len(widths), 2):
            table.setStyle(TableStyle([
                ('BACKGROUND', (col,0), (col,0), colors.HexColor('#e7efe9')),
                ('BACKGROUND', (col,1), (col,-1), colors.HexColor('#f4f7f3')),
                ('LINEABOVE', (col,0), (col,0), 2, green),
            ]))
        for col in range(1, len(widths), 2):
            table.setStyle(TableStyle([('LEFTPADDING', (col,0), (col,-1), 0), ('RIGHTPADDING', (col,0), (col,-1), 0)]))
        story.append(table)
        shared = []
        if common_stay:
            shared.append('住宿参考 / ' + safe_text(common_stay.area_label or common_stay.town) + ' ' + safe_text(common_stay.price))
        if common_foods and common_foods.dishes:
            shared.append('餐饮参考 / ' + '、'.join(safe_text(dish.name) for dish in common_foods.dishes))
        if shared:
            story.extend([Spacer(1, 8), Paragraph('  ·  '.join(shared), small)])
    if plan.tips and not plan.workshop_changed:
        story.append(Paragraph('BEFORE YOU GO  /  出行参考', slot))
        tip_columns = [[], []]
        for index, tip in enumerate(plan.tips):
            tip_columns[index % 2].append(Paragraph(f'{index+1:02d}  ' + safe_text(tip), muted))
        tips_table = Table([[tip_columns[0], tip_columns[1]]], colWidths=[doc.width/2]*2, splitByRow=1, splitInRow=1)
        tips_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),15),
            ('TOPPADDING',(0,0),(-1,-1),0), ('BOTTOMPADDING',(0,0),(-1,-1),0)]))
        story.append(tips_table)
    if plan.rail_journeys:
        story.extend([PageBreak(), Paragraph('RAIL JOURNEY  /  铁路交通', title),
                      Paragraph('铁路日期独立于日程天数，请核对游玩安排。时刻、余票和参考价以 12306 为准；本文件不是车票。', muted)])
        def rail_clock(value):
            return f'{value // 60 % 24:02d}:{value % 60:02d}' + (f' +{value // 1440}天' if value >= 1440 else '')
        for journey in plan.rail_journeys:
            story.append(Paragraph(safe_text(f'{journey.date}  /  {journey.from_} → {journey.to}'), heading))
            rows = [[Paragraph(label, base) for label in ['车次', '出发', '抵达']]]
            for leg in journey.legs:
                rows.append([Paragraph(safe_text(v), base) for v in [leg.train, f'{leg.from_}  {rail_clock(leg.departure)}', f'{leg.to}  {rail_clock(leg.arrival)}']])
            table = Table(rows, colWidths=[doc.width*.18, doc.width*.41, doc.width*.41], repeatRows=1)
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7efe9')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#d9e2dc'))]))
            story.extend([table, Paragraph(safe_text(f'{journey.risk} · 时刻表 {journey.snapshot} · ' + ('票价待核实' if journey.cost is None else f'参考 ¥{journey.cost:g}')), muted), Spacer(1, 12)])
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d9e2dc'))
        canvas.setLineWidth(.5)
        canvas.line(14*mm, 12*mm, page_size[0]-14*mm, 12*mm)
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor('#64756a'))
        canvas.drawString(14*mm, 7*mm, '旅行智规  /  开放时间、预约及交通请出发前核实。')
        canvas.drawRightString(page_size[0]-14*mm, 7*mm, f'{document.page:02d}  /  行程日历')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


@router.post('/export-pdf')
def export_pdf(plan: ExportPlan):
    try:
        data = build_pdf(plan)
    except ImportError as exc:
        raise HTTPException(503, 'PDF 组件未安装，请使用“打印另存”或安装项目依赖') from exc
    filename = quote((plan.name or '我的行程') + '-日程安排.pdf', safe='')
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': "attachment; filename=itinerary.pdf; filename*=UTF-8''" + filename,
        'Cache-Control': 'no-store',
    })
