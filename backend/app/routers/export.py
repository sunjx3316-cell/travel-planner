"""Generate the user's confirmed itinerary as a private, in-memory PDF."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from xml.sax.saxutils import escape
import unicodedata

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


class ExportPlan(ExportBase):
    name: ShortText = '我的行程'
    summary: NoteText = ''
    daily: list[ExportDay] = Field(min_length=1, max_length=60)
    tips: list[NoteText] = Field(default_factory=list, max_length=30)
    workshop_changed: bool = False

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


def build_pdf(plan: ExportPlan):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    stream = BytesIO()
    font = pdf_font()
    base = ParagraphStyle('body', fontName=font, fontSize=10, leading=17, spaceAfter=5)
    title = ParagraphStyle('title', parent=base, fontSize=20, leading=29, spaceAfter=10)
    heading = ParagraphStyle('day', parent=base, fontSize=13, leading=20, spaceBefore=15, spaceAfter=8, keepWithNext=True)
    muted = ParagraphStyle('muted', parent=base, fontSize=9, leading=15, textColor=colors.HexColor('#64756a'))
    item = ParagraphStyle('item', parent=base, fontSize=11, leading=18, spaceBefore=7, spaceAfter=3)
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
                            topMargin=17*mm, bottomMargin=18*mm,
                            title=plan.name, author='旅行智规')
    date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    story = [Paragraph('旅行智规 / 最终行程', muted), Paragraph(safe_text(plan.name), title),
             Paragraph(safe_text(plan.summary), base), Paragraph(f'{len(plan.daily)} 天 / 导出日期 {date}', muted),
             HRFlowable(width='100%', thickness=.5, color=colors.HexColor('#bed0c3'))]
    if plan.workshop_changed:
        story.append(Paragraph('本行程已手动调整；原路线、住宿及交通推算未重新计算，出发前请核实。', muted))
    for index, day in enumerate(plan.daily):
        story.append(Paragraph(f'第 {index+1} 天', heading))
        if day.note:
            story.append(Paragraph(('备注参考：' if plan.workshop_changed else '备注：') + safe_text(day.note), muted))
        if not day.items:
            story.append(Paragraph('当天自由安排', base))
        for entry in day.items:
            story.append(Paragraph(safe_text(entry.time or '待安排') + ' / ' + safe_text(entry.spot or '未命名安排'), item))
            if entry.why:
                story.append(Paragraph(safe_text(entry.why), base))
            if entry.time_reason and not plan.workshop_changed:
                story.append(Paragraph(safe_text(entry.time_reason), muted))
        if not plan.workshop_changed and day.stay:
            story.append(Paragraph('住宿参考：' + safe_text(day.stay.area_label or day.stay.town) + ' ' + safe_text(day.stay.price), muted))
        if not plan.workshop_changed and day.next_transport:
            story.append(Paragraph('交通参考：前往 ' + safe_text(day.next_transport.to) + ' / ' + safe_text(day.next_transport.rail or day.next_transport.recommend), muted))
        if not plan.workshop_changed and day.foods and day.foods.dishes:
            story.append(Paragraph('餐饮参考：' + '、'.join(safe_text(dish.name) for dish in day.foods.dishes), muted))
        story.append(Spacer(1, 3*mm))
    if plan.tips and not plan.workshop_changed:
        story.append(Paragraph('出行参考提醒', heading))
        story.extend(Paragraph(safe_text(tip), base) for tip in plan.tips)
    story.append(Paragraph('以你确认的最终安排为准。历史评价、开放时间、预约和交通信息需出发前核实。', muted))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#64756a'))
        canvas.drawString(17*mm, 10*mm, '旅行智规 / 个人日程')
        canvas.drawRightString(A4[0]-17*mm, 10*mm, f'第 {document.page} 页')
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
