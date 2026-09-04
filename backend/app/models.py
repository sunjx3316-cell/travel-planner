# -*- coding: utf-8 -*-
"""API 响应模型。"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class CityOut(BaseModel):
    id: int
    name: str
    province: str
    lng: float
    lat: float
    spot_count: int = 0


class SpotOut(BaseModel):
    id: int
    city_id: int
    city_name: str
    name: str
    poi_rating: Optional[float] = None
    address: Optional[str] = None
    tags: List[str] = []
    grade: Optional[str] = None
    price: Optional[float] = None
    commercial: Optional[dict] = None
    data_source: Optional[str] = None
    source_updated_at: Optional[str] = None
    has_summary: bool = False


class AvoidPoint(BaseModel):
    point: str
    evidence: str = ""
    specificity: int = 0
    verifiable: int = 0
    consensus: bool = False
    mentions: int = 1


class SummaryCard(BaseModel):
    highlights: List[str] = []
    play_style: List[str] = []
    cost_range: str = ""
    ad_ratio: float = 0.0
    ad_signals: List[str] = []
    avoid_points: List[AvoidPoint] = []
    consensus_issues: List[str] = []
    trust_score: int = 0
    source: str = ""
    note_count: int = 0


class SpotDetailOut(BaseModel):
    id: int
    city_name: str
    name: str
    poi_rating: Optional[float] = None
    address: Optional[str] = None
    tags: List[str] = []
    grade: Optional[str] = None
    price: Optional[float] = None
    commercial: Optional[dict] = None
    data_source: Optional[str] = None
    source_updated_at: Optional[str] = None
    lng: Optional[float] = None
    lat: Optional[float] = None
    images: List[str] = []
    image_assets: List[dict] = []
    fact_sources: List[dict] = []
    notes: List[dict] = []
    summary: Optional[SummaryCard] = None
    alternatives: List[dict] = []


class CartItemOut(BaseModel):
    id: int
    spot_id: int
    name: str
    city_name: str
    added_at: str


class PlanGenerateRequest(BaseModel):
    city_id: int
    days: int = Field(3, ge=1, le=14)
    spot_ids: List[int] = Field(min_length=1)
    style: str = "轻松"


class RoadtripRequest(BaseModel):
    """自驾模式:多城市景点串联成路线。"""
    spot_ids: List[int] = Field(min_length=2)
    days: int = Field(5, ge=1, le=30)
    style: str = "轻松"
    close_loop: bool = True   # 环线闭环:终点返回起点
    start_city: str = ""      # 出发地城市(从哪出发,空则从首个景点出发)


class CityTourRequest(BaseModel):
    """城市模式:以城市为单位(1 个或多个相连),每日一城含景区/博物馆/美食/住宿。"""
    spot_ids: List[int] = Field(min_length=1)
    days: int = Field(3, ge=1, le=30)
    style: str = "轻松"
    close_loop: bool = False   # 城市模式默认不回程闭环(自驾模式才需要)
    start_city: str = ""
    city_days: Optional[dict] = None   # {城市: 天数},如 {"西安": 2, "兰州": 1}


class CityPlanRecommendRequest(BaseModel):
    """城市规划推荐:每城玩几天 + 从哪个城市开始(依据出发地便利)。"""
    spot_ids: List[int] = Field(min_length=1)
    total_days: int = Field(3, ge=1, le=30)
    start_city: str = ""


class PlanOut(BaseModel):
    id: int
    plan: dict


class StatusOut(BaseModel):
    llm_available: bool
    data_source: str
    version: str


class LoopOut(BaseModel):
    name: str
    desc: str = ""
    days: str = ""
    spots: List[dict] = []


class SpotMapOut(BaseModel):
    """省级地图上的景点散点(含分类)。"""
    id: int
    name: str
    city_name: str
    lng: float
    lat: float
    grade: Optional[str] = None
    tags: List[str] = []
    category: str = "综合"
    commercial: Optional[dict] = None
